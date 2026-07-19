#!/usr/bin/env python3
"""Run the deterministic half of the WeChat content pipeline.

The agent supplies topic judgment, article.md, sources.md and one inline plan.
This runner owns state transitions, theme selection, rendering, cover generation,
validation, preview creation, the draft gate and optional draft creation.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pipeline_job


TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
TRANSIENT_RE = re.compile(
    r"TLS|EOF|connection reset|timed? out|timeout|HTTP\s+5\d\d|微信 API 请求失败",
    re.IGNORECASE,
)


class RuntimeFailure(RuntimeError):
    pass


def load_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeFailure(f"无法读取{label}：{exc}") from exc


def run_json(command):
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeFailure(detail or f"命令失败：{' '.join(command[:2])}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeFailure(f"命令没有返回合法 JSON：{result.stdout[:200]}") from exc


def run_plain(command):
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeFailure(detail or f"命令失败：{' '.join(command[:2])}")
    return result.stdout


def job_paths(job_path):
    job = pipeline_job.load_job(job_path)
    job_dir = Path(job["job_dir"])
    artifacts = {
        name: job_dir / value for name, value in job["artifacts"].items()
    }
    artifacts["cover_spec"] = job_dir / "cover" / "cover.spec.json"
    artifacts["cover_html"] = job_dir / "cover" / "cover.html"
    return job, artifacts


def mark(job_path, name, status, message=None, details=None, artifacts=None):
    argv = [
        "stage", "--job", str(job_path), "--name", name, "--status", status,
    ]
    if message is not None:
        argv.extend(("--message", message))
    for key, value in (details or {}).items():
        argv.extend(("--detail", f"{key}={value}"))
    for key, value in (artifacts or {}).items():
        argv.extend(("--artifact", f"{key}={value}"))
    args = pipeline_job.build_parser().parse_args(argv)
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline_job.cmd_stage(args)


def choose_theme(job_path):
    args = pipeline_job.build_parser().parse_args(
        ["choose-theme", "--job", str(job_path)]
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        pipeline_job.cmd_choose_theme(args)
    return output.getvalue().strip()


def require_content(artifacts):
    for name in ("article", "sources"):
        path = artifacts[name]
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeFailure(f"缺少 {name} 产物：{exc}") from exc
        if not value:
            raise RuntimeFailure(f"{path.name} 不能为空")
    article = artifacts["article"].read_text(encoding="utf-8")
    matches = TITLE_RE.findall(article)
    if len(matches) != 1:
        raise RuntimeFailure("article.md 必须包含且只包含一个一级标题")
    return " ".join(matches[0].split())


def validator(project_root):
    path = Path(project_root) / "scripts" / "validate_gzh_html.py"
    spec = importlib.util.spec_from_file_location("pipeline_html_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeFailure("无法加载 HTML 校验器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_html(project_root, html_path):
    try:
        value = html_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeFailure(f"无法读取 article.html：{exc}") from exc
    errors, warnings, leaf_count = validator(project_root).validate(value, str(html_path))
    if errors or warnings:
        raise RuntimeFailure("HTML 严格校验失败：" + "；".join(errors + warnings))
    return leaf_count


def default_thumb_available(config_path, account_alias):
    config = load_json(config_path, "公众号账号配置")
    account = config.get("accounts", {}).get(account_alias, {})
    env_name = account.get("default_thumb_media_id_env", "")
    return bool(account.get("default_thumb_media_id") or (env_name and os.environ.get(env_name)))


def command_roots(job):
    pipeline_root = SCRIPT_DIR.parent
    skills_root = pipeline_root.parent
    return {
        "pipeline": pipeline_root,
        "inline": skills_root / "wechat-inline-visuals",
        "cover": skills_root / "wechat-html-cover",
        "project": Path(job["project_root"]),
    }


def resolve_config(value, project_root):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(project_root) / path
    return path.resolve()


def cmd_begin(args):
    job, _ = job_paths(args.job)
    if job["stages"]["discover"]["status"] != "completed":
        raise RuntimeFailure("必须先确定并记录选题")
    for name in ("write", "fact-check"):
        mark(args.job, name, "running", "开始写作与同步事实核验")
    return {"status": "ok", "next": "write-content", "job": str(args.job)}


def cmd_prepare(args):
    job, artifacts = job_paths(args.job)
    title = require_content(artifacts)
    mark(
        args.job, "write", "completed", "正文已写入",
        artifacts={"article": artifacts["article"]},
    )
    mark(
        args.job, "fact-check", "completed", "来源记录已写入",
        artifacts={"sources": artifacts["sources"]},
    )
    theme = choose_theme(args.job)
    mark(args.job, "format", "running", "开始确定性排版", {"theme": theme})
    mark(args.job, "inline-visuals", "running", "等待唯一一次信息模块计划")
    roots = command_roots(job)
    cover_spec = run_json([
        sys.executable,
        str(roots["cover"] / "scripts" / "build_cover_spec.py"),
        "--article", str(artifacts["article"]),
        "--theme", theme,
        "--template", "auto",
        "--output", str(artifacts["cover_spec"]),
    ])
    return {
        "status": "ok", "next": "write-inline-plan", "title": title,
        "theme": theme, "template": load_json(artifacts["cover_spec"], "封面规格")["template"],
        "plan": str(artifacts["inline_visuals"]), "cover_spec": cover_spec["output"],
    }


def render_body(job_path, job, artifacts, roots):
    theme = job["stages"]["format"].get("details", {}).get("theme")
    if not theme:
        raise RuntimeFailure("prepare 尚未固定排版主题")
    plan_result = run_json([
        sys.executable,
        str(roots["inline"] / "scripts" / "validate_plan.py"),
        "--plan", str(artifacts["inline_visuals"]),
        "--article", str(artifacts["article"]),
        "--theme-index", str(roots["project"] / "references" / "theme-index.md"),
        "--degrade-on-error", "--fallback-theme", theme,
    ])
    render_result = run_json([
        sys.executable,
        str(roots["pipeline"] / "scripts" / "render_article.py"),
        "--article", str(artifacts["article"]),
        "--plan", str(artifacts["inline_visuals"]),
        "--theme", theme,
        "--output", str(artifacts["html"]),
    ])
    degraded = bool(plan_result.get("degraded") or render_result.get("degraded"))
    reason = plan_result.get("degrade_reason") or render_result.get("degrade_reason") or ""
    mark(
        job_path, "format", "completed", "确定性正文排版完成",
        {"theme": theme, "renderer": "pipeline-runtime"},
        {"html": artifacts["html"]},
    )
    inline_status = "skipped" if degraded else "completed"
    details = {
        "mode": "native-html",
        "module_count": str(render_result["module_count"]),
        "kinds": ",".join(render_result.get("kinds", [])) or "none",
        "degraded": "true" if degraded else "false",
    }
    if reason:
        details["reason"] = reason[:180]
    mark(
        job_path, "inline-visuals", inline_status,
        "信息模块已降级为空计划" if degraded else "信息模块处理完成",
        details, {"inline_visuals": artifacts["inline_visuals"]},
    )
    return render_result, degraded


def render_cover(job_path, job, artifacts, roots, config_path):
    mark(job_path, "cover", "running", "开始 HTML 封面渲染")
    command = [
        sys.executable,
        str(roots["cover"] / "scripts" / "render_cover.py"),
        "--spec", str(artifacts["cover_spec"]),
        "--html-output", str(artifacts["cover_html"]),
        "--output", str(artifacts["cover"]),
        "--timeout", "45",
    ]
    failures = []
    for _ in range(2):
        try:
            result = run_json(command)
            mark(
                job_path, "cover", "completed", "HTML 封面生成完成",
                {"template": result["template"], "visual_check": "not-required"},
                {"cover": artifacts["cover"]},
            )
            return result, True
        except RuntimeFailure as exc:
            failures.append(str(exc))
    has_default = default_thumb_available(config_path, job["account"])
    mark(
        job_path, "cover", "skipped", "HTML 封面失败，检查账号默认封面",
        {
            "default_thumb_media_id": "true" if has_default else "false",
            "reason": failures[-1][:180],
        },
    )
    return {"status": "skipped", "reason": failures[-1]}, False


def validate_and_preview(job_path, job, artifacts, roots):
    mark(job_path, "validate", "running", "开始严格 HTML 校验")
    try:
        leaf_count = validate_html(job["project_root"], artifacts["html"])
        run_plain([
            sys.executable,
            str(roots["project"] / "scripts" / "wrap_preview.py"),
            str(artifacts["html"]), str(artifacts["preview"]),
        ])
    except RuntimeFailure as exc:
        mark(job_path, "validate", "failed", str(exc)[:180])
        raise
    mark(
        job_path, "validate", "completed", "HTML 与预览校验完成",
        {"leaf_count": str(leaf_count), "errors": "0", "warnings": "0"},
        {"preview": artifacts["preview"]},
    )
    gate_args = pipeline_job.build_parser().parse_args(
        ["gate", "--job", str(job_path)]
    )
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline_job.cmd_gate(gate_args)
    return leaf_count


def publish_draft(args, job, artifacts, roots, generated_cover, config_path):
    command = [
        sys.executable,
        str(roots["project"] / "scripts" / "wechat_publish.py"),
        "--config", str(config_path), "send",
        "--account", job["account"],
        "--html", str(artifacts["html"]),
        "--title", require_content(artifacts),
        "--action", "draft", "--strict",
        "--result-file", str(artifacts["draft_result"]),
    ]
    if generated_cover:
        command.extend(("--cover", str(artifacts["cover"])))
    if args.dry_run:
        command.append("--dry-run")
    if args.skip_draft:
        mark(
            args.job, "draft", "skipped", "按参数跳过草稿 API",
            {"dry_run": "false", "gate": "passed"},
        )
        return {"status": "skipped"}
    mark(args.job, "draft", "running", "开始创建公众号草稿")
    attempts = 0
    while True:
        attempts += 1
        try:
            result = run_json(command)
            break
        except RuntimeFailure as exc:
            if attempts >= 2 or not TRANSIENT_RE.search(str(exc)):
                mark(args.job, "draft", "failed", str(exc)[:180], {"attempts": str(attempts)})
                raise
    if args.dry_run:
        mark(
            args.job, "draft", "skipped", "草稿输入 dry-run 校验通过",
            {"dry_run": "true", "attempts": str(attempts), "gate": "passed"},
            {"draft_result": artifacts["draft_result"]},
        )
    else:
        if (
            result.get("account") != job["account"]
            or result.get("action") != "draft"
            or not result.get("draft_media_id")
        ):
            mark(args.job, "draft", "failed", "草稿结果字段不完整")
            raise RuntimeFailure("草稿结果未通过账号、动作或 media_id 校验")
        mark(
            args.job, "draft", "completed", "公众号草稿创建成功",
            {"attempts": str(attempts)}, {"draft_result": artifacts["draft_result"]},
        )
    return result


def cmd_finish(args):
    job, artifacts = job_paths(args.job)
    roots = command_roots(job)
    config_path = resolve_config(args.config, job["project_root"])
    render_result, degraded = render_body(args.job, job, artifacts, roots)
    job, artifacts = job_paths(args.job)
    cover_result, generated_cover = render_cover(
        args.job, job, artifacts, roots, config_path
    )
    job, artifacts = job_paths(args.job)
    leaf_count = validate_and_preview(args.job, job, artifacts, roots)
    job, artifacts = job_paths(args.job)
    draft_result = publish_draft(
        args, job, artifacts, roots, generated_cover, config_path
    )
    final_job = pipeline_job.load_job(args.job)
    reported_state = final_job["state"]
    if args.dry_run:
        reported_state = "validated-dry-run"
    elif args.skip_draft:
        reported_state = "ready-for-draft"
    return {
        "status": "ok", "state": reported_state, "account": final_job["account"],
        "topic": final_job["topic"],
        "theme": final_job["stages"]["format"]["details"]["theme"],
        "module_count": render_result["module_count"], "degraded": degraded,
        "cover": cover_result.get("status"), "leaf_count": leaf_count,
        "draft": draft_result,
        "stage_timings_ms": {
            name: item.get("duration_ms") for name, item in final_job["stages"].items()
        },
        "artifacts": final_job["artifacts"],
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="公众号流水线固定运行器；禁止用临时脚本替代"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("begin", help="在 Agent 写作前启动计时")
    begin.add_argument("--job", required=True)
    prepare = sub.add_parser("prepare", help="核验正文、固定主题并等待唯一信息计划")
    prepare.add_argument("--job", required=True)
    finish = sub.add_parser("finish", help="一次完成排版、封面、校验和草稿")
    finish.add_argument("--job", required=True)
    finish.add_argument("--config", default="wechat-accounts.json")
    finish.add_argument("--dry-run", action="store_true", help="校验草稿输入但不连接微信 API")
    finish.add_argument("--skip-draft", action="store_true", help="通过门禁后停止；不得用于定时生产")
    return parser


def main():
    args = build_parser().parse_args()
    try:
        result = {
            "begin": cmd_begin,
            "prepare": cmd_prepare,
            "finish": cmd_finish,
        }[args.command](args)
    except (RuntimeFailure, pipeline_job.JobError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
