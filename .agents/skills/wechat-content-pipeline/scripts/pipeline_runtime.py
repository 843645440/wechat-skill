#!/usr/bin/env python3
"""Run the deterministic half of the WeChat content pipeline.

The agent supplies topic judgment, article.md and optional Baoyu illustrations.
This runner owns state transitions, theme selection, rendering, cover generation,
a lightweight draft gate and optional draft creation.
"""

import argparse
import contextlib
import fcntl
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
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
MARKDOWN_NOISE_RE = re.compile(r"[#>*_`~\[\]()!|\\\-]+")
TRANSIENT_RE = re.compile(
    r"TLS|EOF|connection reset|timed? out|timeout|HTTP\s+5\d\d|微信 API 请求失败",
    re.IGNORECASE,
)
MIN_BODY_CHARS = 1500
MAX_BODY_CHARS = 4000


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
    job_dir = Path(job_path).resolve().parent
    if Path(job["job_dir"]).resolve() != job_dir:
        raise RuntimeFailure("任务清单 job_dir 与当前账号工作区不一致")
    artifacts = {}
    for name, value in job["artifacts"].items():
        try:
            safe_path, _ = pipeline_job.artifact_path(str(job_path), value)
        except pipeline_job.JobError as exc:
            raise RuntimeFailure(str(exc)) from exc
        artifacts[name] = Path(safe_path)
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


def count_body_chars(article):
    """Count readable body characters after stripping title and light Markdown noise."""
    lines = []
    skipped_title = False
    for line in article.splitlines():
        if not skipped_title and TITLE_RE.match(line):
            skipped_title = True
            continue
        if line.lstrip().startswith("##"):
            line = re.sub(r"^#{2,6}\s*", "", line)
        lines.append(line)
    text = "\n".join(lines)
    text = FENCE_RE.sub("", text)
    text = MARKDOWN_NOISE_RE.sub("", text)
    return len(re.sub(r"\s+", "", text))


def require_content(artifacts, job=None):
    try:
        article = artifacts["article"].read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeFailure(f"缺少 article 产物：{exc}") from exc
    if not article:
        raise RuntimeFailure("article.md 不能为空")
    matches = TITLE_RE.findall(article)
    if len(matches) != 1:
        raise RuntimeFailure("article.md 必须包含且只包含一个一级标题")
    title = " ".join(matches[0].split())
    if len(title) > 32:
        raise RuntimeFailure(f"article.md 标题长度 {len(title)} 超过 32 字")
    body_chars = count_body_chars(article)
    if body_chars < MIN_BODY_CHARS or body_chars > MAX_BODY_CHARS:
        raise RuntimeFailure(
            f"article.md 正文字数 {body_chars} 不在 {MIN_BODY_CHARS}—{MAX_BODY_CHARS} 字范围内"
        )
    return title


def require_prepare_stages(job):
    if job["stages"]["humanize"]["status"] != "completed":
        raise RuntimeFailure("prepare 前必须完成阶段 humanize")
    if job["stages"]["illustrations"]["status"] not in ("completed", "skipped"):
        raise RuntimeFailure("prepare 前必须完成或跳过阶段 illustrations")


def require_illustrations(job, artifacts):
    article = artifacts["article"].read_text(encoding="utf-8")
    refs = MARKDOWN_IMAGE_RE.findall(article)
    if len(refs) > 3:
        raise RuntimeFailure("正文配图最多 3 张")
    job_dir = artifacts["article"].parent.resolve()
    missing = []
    for ref in refs:
        image_path = (job_dir / ref).resolve()
        if image_path != job_dir and job_dir not in image_path.parents:
            raise RuntimeFailure(f"正文配图路径越界：{ref}")
        if not image_path.is_file():
            missing.append(ref)
    for ref in missing:
        article = re.sub(
            rf"!\[[^\]]*\]\({re.escape(ref)}\)\s*",
            "",
            article,
        )
    if missing:
        artifacts["article"].write_text(article, encoding="utf-8")
    return len(refs) - len(missing)


def verified_draft_result(job, artifacts):
    stage = job["stages"]["draft"]
    if stage["status"] != "completed":
        return None
    if stage.get("details", {}).get("run_id") != job["run_id"]:
        raise RuntimeFailure("已完成草稿阶段的 run_id 与当前任务不一致")
    result = load_json(artifacts["draft_result"], "草稿结果")
    if (
        result.get("account") != job["account"]
        or result.get("action") != "draft"
        or result.get("run_id") != job["run_id"]
        or not result.get("draft_media_id")
    ):
        raise RuntimeFailure("已完成草稿的结果文件未通过 run_id、账号、动作或 media_id 校验")
    return result


def draft_resume_response(job, result):
    article_path = Path(job["job_dir"]) / job["artifacts"].get("article", "article.md")
    image_count = 0
    if article_path.is_file():
        image_count = len(MARKDOWN_IMAGE_RE.findall(article_path.read_text(encoding="utf-8")))
    return {
        "status": "ok", "state": "drafted", "account": job["account"],
        "topic": job["topic"],
        "theme": job["stages"]["format"].get("details", {}).get("theme"),
        "image_count": image_count,
        "cover": job["stages"]["cover"]["status"],
        "draft": result, "resumed": True,
        "stage_timings_ms": {
            name: item.get("duration_ms") for name, item in job["stages"].items()
        },
        "artifacts": job["artifacts"],
    }


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
        "project": SCRIPT_DIR.parents[3],
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
    if job["stages"]["write"]["status"] not in ("running", "completed"):
        mark(args.job, "write", "running", "开始写作")
    return {"status": "ok", "next": "write-content", "job": str(args.job)}


def cmd_prepare(args):
    try:
        return _cmd_prepare(args)
    except (RuntimeFailure, pipeline_job.JobError) as exc:
        try:
            mark(args.job, "format", "failed", f"prepare 失败：{exc}", {
                "phase": "prepare", "error": str(exc),
            })
        except Exception:
            pass
        raise


def _cmd_prepare(args):
    job, artifacts = job_paths(args.job)
    require_prepare_stages(job)
    title = require_content(artifacts, job)
    image_count = require_illustrations(job, artifacts)
    mark(
        args.job, "write", "completed", "正文已写入",
        artifacts={"article": artifacts["article"]},
    )
    theme = choose_theme(args.job)
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
        "status": "ok", "next": "finish", "title": title,
        "theme": theme, "template": load_json(artifacts["cover_spec"], "封面规格")["template"],
        "cover_spec": cover_spec["output"],
        "image_count": image_count,
        "body_chars": count_body_chars(artifacts["article"].read_text(encoding="utf-8")),
    }


def render_body(job_path, job, artifacts, roots):
    theme = job["stages"]["format"].get("details", {}).get("theme")
    if not theme:
        raise RuntimeFailure("prepare 尚未固定排版主题")
    mark(job_path, "format", "running", "开始确定性排版", {"theme": theme})
    try:
        render_result = run_json([
            sys.executable,
            str(roots["pipeline"] / "scripts" / "render_article.py"),
            "--article", str(artifacts["article"]),
            "--theme", theme,
            "--output", str(artifacts["html"]),
        ])
    except RuntimeFailure as exc:
        mark(job_path, "format", "failed", str(exc)[:180], {"theme": theme})
        raise
    mark(
        job_path, "format", "completed", "确定性正文排版完成",
        {
            "theme": theme,
            "renderer": "pipeline-runtime",
        },
        {"html": artifacts["html"]},
    )
    render_result["reused"] = False
    return render_result


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
            result["reused"] = False
            mark(
                job_path, "cover", "completed", "HTML 封面生成完成",
                {
                    "template": result["template"],
                    "visual_check": "not-required",
                },
                {"cover": artifacts["cover"]},
            )
            return result, True
        except RuntimeFailure as exc:
            message = str(exc)
            failures.append(message)
            if not TRANSIENT_RE.search(message):
                break
    has_default = default_thumb_available(config_path, job["account"])
    mark(
        job_path, "cover", "skipped", "HTML 封面失败，检查账号默认封面",
        {
            "default_thumb_media_id": "true" if has_default else "false",
            "reason": failures[-1][:180],
        },
    )
    return {"status": "skipped", "reason": failures[-1]}, False


def lightweight_gate(job_path):
    gate_args = pipeline_job.build_parser().parse_args(
        ["gate", "--job", str(job_path)]
    )
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline_job.cmd_gate(gate_args)


def publish_draft(args, job, artifacts, roots, generated_cover, config_path):
    command = [
        sys.executable,
        str(roots["project"] / "scripts" / "wechat_publish.py"),
        "--config", str(config_path), "send",
        "--account", job["account"],
        "--html", str(artifacts["html"]),
        "--title", require_content(artifacts, job),
        "--action", "draft",
        "--run-id", job["run_id"],
        "--result-file", str(artifacts["draft_result"]),
    ]
    if generated_cover:
        command.extend(("--cover", str(artifacts["cover"])))
    if args.dry_run:
        command.append("--dry-run")
    if args.skip_draft:
        mark(
            args.job, "draft", "skipped", "按参数跳过草稿 API",
            {"dry_run": "false", "gate": "passed", "run_id": job["run_id"]},
        )
        return {"status": "skipped"}
    mark(
        args.job, "draft", "running", "开始创建公众号草稿", {
            "attempts": "1", "run_id": job["run_id"],
            "outcome": "pending", "retry_safe": "false",
        },
    )
    try:
        result = run_json(command)
    except RuntimeFailure as exc:
        deterministic_preflight = bool(re.search(
            r"未设置 App(?:ID|Secret) 环境变量"
            r"|配置中没有账号"
            r"|账号 .+ 缺少 (?:appid_env|secret_env)",
            str(exc),
        ))
        details = {
            "attempts": "1",
            "run_id": job["run_id"],
            "outcome": (
                "preflight-failed"
                if args.dry_run or deterministic_preflight
                else "uncertain"
            ),
            "retry_safe": (
                "true" if args.dry_run or deterministic_preflight else "false"
            ),
        }
        mark(args.job, "draft", "failed", str(exc)[:180], details)
        raise
    if args.dry_run:
        mark(
            args.job, "draft", "skipped", "草稿输入 dry-run 校验通过",
            {
                "dry_run": "true", "attempts": "1", "gate": "passed",
                "run_id": job["run_id"],
            },
            {"draft_result": artifacts["draft_result"]},
        )
    else:
        if (
            result.get("account") != job["account"]
            or result.get("action") != "draft"
            or result.get("run_id") != job["run_id"]
            or not result.get("draft_media_id")
        ):
            mark(args.job, "draft", "failed", "草稿结果字段不完整", {
                "attempts": "1", "run_id": job["run_id"],
                "outcome": "uncertain", "retry_safe": "false",
            })
            raise RuntimeFailure("草稿结果未通过账号、动作或 media_id 校验")
        mark(
            args.job, "draft", "completed", "公众号草稿创建成功",
            {"attempts": "1", "run_id": job["run_id"]},
            {"draft_result": artifacts["draft_result"]},
        )
    return result


def cmd_finish(args):
    lock_path = Path(args.job).resolve().parent / ".finish.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return _cmd_finish(args)


def _cmd_finish(args):
    job, artifacts = job_paths(args.job)
    roots = command_roots(job)
    config_path = resolve_config(args.config, roots["project"])
    draft_stage = job["stages"]["draft"]
    draft_details = draft_stage.get("details", {})
    if draft_stage["status"] == "running":
        interrupted_details = {
            "attempts": draft_details.get("attempts", "1"),
            "run_id": draft_details.get("run_id", job["run_id"]),
            "outcome": "uncertain", "retry_safe": "false",
        }
        mark(
            args.job, "draft", "failed",
            "draft/add 进程中断，远端结果不确定", interrupted_details,
        )
        raise RuntimeFailure(
            "上次 draft/add 结果不确定；请先人工核对微信草稿箱，再将 draft 阶段重置为 pending"
        )
    if (
        draft_stage["status"] == "failed"
        and draft_details.get("outcome") == "uncertain"
    ):
        raise RuntimeFailure(
            "上次 draft/add 结果不确定；请先人工核对微信草稿箱，再将 draft 阶段重置为 pending"
        )
    existing_draft = verified_draft_result(job, artifacts)
    if existing_draft:
        return draft_resume_response(job, existing_draft)
    render_result = render_body(args.job, job, artifacts, roots)
    job, artifacts = job_paths(args.job)
    cover_result, generated_cover = render_cover(
        args.job, job, artifacts, roots, config_path
    )
    job, artifacts = job_paths(args.job)
    lightweight_gate(args.job)
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
        "image_count": len(MARKDOWN_IMAGE_RE.findall(
            artifacts["article"].read_text(encoding="utf-8")
        )),
        "cover": cover_result.get("status"),
        "draft": draft_result, "resumed": False,
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
    finish_mode = finish.add_mutually_exclusive_group()
    finish_mode.add_argument(
        "--dry-run", action="store_true", help="校验草稿输入但不连接微信 API"
    )
    finish_mode.add_argument(
        "--skip-draft", action="store_true", help="通过门禁后停止；不得用于定时生产"
    )
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
