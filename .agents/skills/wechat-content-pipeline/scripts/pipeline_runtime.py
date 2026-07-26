#!/usr/bin/env python3
"""Run the deterministic half of the WeChat content pipeline.

The agent supplies topic judgment, article.md, optional Baoyu illustrations,
and AI-generated cover image (cover/cover.png). HTML cover rendering is retired.
This runner owns state transitions, theme selection, body rendering, cover accept,
a lightweight draft gate and optional draft creation.
"""

import argparse
import contextlib
import fcntl
import io
import json
import os
import re
import shlex
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


# wechat_publish.py 在失败时会往 stderr 打一行结论：draft_may_exist=true|false。
# false 表示远端一定没有草稿（取 token 被拒、图片上传失败、服务端对 draft/add
# 明确返回 errcode……），重跑安全；true 只出现在 draft/add 已发出但结果读不到
# 的情况（连接重置/超时/响应无法解析）。
DRAFT_MAY_EXIST_RE = re.compile(r"^draft_may_exist=(true|false)$", re.MULTILINE)

# 兜底：万一发布器是不带上述标记的旧版本，仍按这些本地配置错误判定可安全重跑。
# 新代码不应该继续往这里加错误码——语义判断属于 wechat_publish.py。
LEGACY_PREFLIGHT_RE = re.compile(
    r"未设置 App(?:ID|Secret) 环境变量"
    r"|配置中没有账号"
    r"|账号 .+ 缺少 (?:appid_env|secret_env)"
)


# 只在「远端可能已经有草稿」时出现。这段话是给人看的操作指引，不要精简成
# 一句「结果不确定」——真踩到的人需要知道下一步具体做什么。
UNCERTAIN_DRAFT_MESSAGE = (
    "上次 draft/add 结果不确定：请求已发出但没读到响应，微信侧可能已经建了草稿。\n"
    "  自动重发会产生双草稿，所以这里必须人工核对：\n"
    "  1. 打开公众号后台草稿箱，确认这篇是否已经存在。\n"
    "  2a. 已存在 → 不要重跑，直接以后台那篇为准；本次任务到此为止。\n"
    "  2b. 不存在 → 重置后重跑尾段（正文不用改）：\n"
    "      pipeline_job.py stage --job {job} --name draft --status pending\n"
    "      pipeline_runtime.py finish --job {job} --config <wechat-accounts.json>"
)


def draft_failure_is_retry_safe(message):
    """这次 draft 失败之后，能不能直接重跑而不会产生双草稿？

    优先读发布器给的结论标记；标记缺失时退回旧正则；两者都没有就保守判为
    「不确定」（False），让人先去草稿箱核对。
    """
    match = DRAFT_MAY_EXIST_RE.search(message or "")
    if match:
        return match.group(1) == "false"
    return bool(LEGACY_PREFLIGHT_RE.search(message or ""))


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
        # HTML 封面 skill 保留在 monorepo，但流水线不再调用
        "cover": skills_root / "wechat-html-cover",
        "project": SCRIPT_DIR.parents[3],
    }


def resolve_config(value, project_root):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(project_root) / path
    return path.resolve()


BAND_CHAR_HINTS = {
    "short": "约 1500—1900 字",
    "mid": "约 1900—2600 字",
    "long": "约 2600—4000 字",
}


def writing_contract(job):
    """把写作硬门禁压缩成一张机器可读的卡片，弱模型照抄执行，不必翻文档。"""
    shape = job.get("article_shape", {})
    band = shape.get("body_band")
    return {
        "output_file": "article.md",
        "title": "唯一一级标题 # ，≤32 字；刺点放前 16 字；禁周报体/通稿体",
        "body_chars": f"可读字符 {MIN_BODY_CHARS}—{MAX_BODY_CHARS}"
        + (f"（本篇目标 {BAND_CHAR_HINTS[band]}）" if band in BAND_CHAR_HINTS else ""),
        "voice": "第一人称「我」+ 强情感；情绪钉在机制/事实上；禁编造亲历、人物、数据",
        "faithful": "忠实用户 brief：不换题、不反转结论、must_avoid 禁区不碰、关键数字全保留",
        "shape": shape,
        "shape_note": "shape 只保证轮换合法，不懂题材。felt_sense / tension_type 与本题"
        "明显相悖时（判决、事故写成「振奋」这类），先跑 "
        "pipeline_job.py shape --auto --felt-sense <情绪> --tension-type <矛盾> 覆盖再写",
        "sections": f"用 {shape.get('heading_count', '3—5')} 个 ## 小节；"
        "每节结尾留一个未解勾子；全文至少 1 句可转发的判断句",
        "images": "正文图 0—3 张，路径必须在工作区内（imgs/xx）；有说明才写 alt",
        "digest": "另写一句 ≤50 字摘要到 digest.txt（分享卡副标题，补标题第二钩子，不复述标题）",
        "after_write": [
            "pipeline_runtime.py check --job <job.json>  # 写完先自检，错误按提示改",
            "pipeline_job.py stage --name humanize --status running → 一轮 strong 去 AI 味改写 → --status completed --detail intensity=strong",
            "配图/封面就位后：pipeline_runtime.py prepare → finish",
        ],
    }


def cmd_begin(args):
    job, _ = job_paths(args.job)
    if job["stages"]["discover"]["status"] != "completed":
        raise RuntimeFailure("必须先确定并记录选题")
    if job["stages"]["write"]["status"] not in ("running", "completed"):
        mark(args.job, "write", "running", "开始写作")
    return {
        "status": "ok",
        "next": "write-content",
        "job": str(args.job),
        "writing_contract": writing_contract(job),
    }


DEFAULT_PROFILES = "config/wechat-content-profiles.json"


def account_label(job):
    """账号显示名，用于封面眉标；读不到就退回账号别名。"""
    try:
        roots = command_roots(job)
        _, profiles = pipeline_job.load_profiles(str(roots["project"]), DEFAULT_PROFILES)
        label = (profiles.get(job["account"]) or {}).get("label")
    except Exception:
        label = None
    return label or job["account"]


def cover_fallback_command(job, artifacts, titles):
    """封面的推荐命令：一条命令跑完「用户图 → 生图 → 离线兜底」并自动记账。

    以前这里只给离线兜底那一档，等于默认「生图这条路 agent 自己想办法」——
    结果就是每次都要临场拼 prompt、调后端、再手动记账。现在整条降级链下沉到
    gen_cover_image.py，这里只负责把命令拼出来。
    """
    roots = command_roots(job)
    script = roots["pipeline"] / "scripts" / "gen_cover_image.py"
    return " ".join([
        "python3", shlex.quote(str(script)),
        "--job", shlex.quote(str(Path(job["job_dir"]) / "job.json")),
        "--record-stage",
    ])


def cmd_check(args):
    """写作后自检：一次列出全部问题与修法，不改任何状态（弱模型的早失败护栏）。"""
    job, artifacts = job_paths(args.job)
    problems = []
    hints = []
    article_path = artifacts["article"]
    if not article_path.is_file():
        return {
            "status": "fail",
            "problems": ["缺少 article.md：先按 begin 输出的 writing_contract 写正文"],
        }
    article = article_path.read_text(encoding="utf-8")
    titles = TITLE_RE.findall(article)
    if len(titles) != 1:
        problems.append(
            f"一级标题数量为 {len(titles)}，必须恰好 1 个（`# 标题` 开头，其余用 ##）"
        )
    else:
        title = " ".join(titles[0].split())
        if len(title) > 32:
            problems.append(
                f"标题 {len(title)} 字超过 32：压缩到 32 字内，保留前 16 字的刺点"
            )
    body_chars = count_body_chars(article)
    if body_chars < MIN_BODY_CHARS:
        problems.append(
            f"正文 {body_chars} 字 < {MIN_BODY_CHARS}：补真实机制/人群/成本细节，禁止注水"
        )
    elif body_chars > MAX_BODY_CHARS:
        problems.append(f"正文 {body_chars} 字 > {MAX_BODY_CHARS}：删冗余段落")
    refs = MARKDOWN_IMAGE_RE.findall(article)
    if len(refs) > 3:
        problems.append(f"正文图 {len(refs)} 张 > 3：删到 3 张以内")
    job_dir = article_path.parent.resolve()
    for ref in refs:
        image_path = (job_dir / ref).resolve()
        if image_path != job_dir and job_dir not in image_path.parents:
            problems.append(f"图片路径越界：{ref}（必须在工作区内，如 imgs/01.jpg）")
        elif not image_path.is_file():
            hints.append(f"图片引用未落盘：{ref}（prepare 会自动删除该引用）")
    placeholder = pipeline_job.PLACEHOLDER_RE.search(article)
    if placeholder:
        problems.append(f"存在未替换占位符：{placeholder.group(0)}")
    digest_path = article_path.parent / "digest.txt"
    if not digest_path.is_file():
        hints.append("建议补 digest.txt（一句 ≤50 字摘要，分享卡副标题）")
    else:
        digest = " ".join(digest_path.read_text(encoding="utf-8").split())
        if len(digest) > 64:
            hints.append(f"digest.txt {len(digest)} 字过长，将被截断到 64 字")
    if job["stages"]["humanize"]["status"] != "completed":
        hints.append(
            "humanize 未完成：改写前后用 stage --name humanize --status running/completed 记账"
        )
    if not _cover_file_usable(artifacts["cover"]):
        hints.append(
            "封面尚未就位（finish 硬门禁）。跑这一条就够了，它自己走"
            "「用户图 → 生图 → 离线兜底」并记账，无网络/无 API key 也能出图："
            + cover_fallback_command(job, artifacts, titles)
        )
    return {
        "status": "fail" if problems else "ok",
        "body_chars": body_chars,
        "image_refs": len(refs),
        "problems": problems,
        "hints": hints,
        "next": "修复 problems 后重跑 check；全部通过后走 humanize → prepare → finish"
        if problems else "humanize（若未做）→ prepare → finish",
    }


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
    return {
        "status": "ok", "next": "finish", "title": title,
        "theme": theme,
        "cover_backend": (job["stages"]["cover"].get("details") or {}).get(
            "backend", "image_generate"
        ),
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


def _cover_file_usable(path):
    """Accept PNG/JPEG/WebP generated by image APIs; minimal magic-byte check."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if len(data) < 32:
        return False
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def accept_cover(job_path, job, artifacts, config_path):
    """Use agent-generated cover image; do not call HTML cover renderer."""
    cover_path = artifacts["cover"]
    cover_stage = job["stages"].get("cover", {})
    if cover_stage.get("status") == "completed" and _cover_file_usable(cover_path):
        return {
            "status": "completed",
            "backend": "image_generate",
            "reused": True,
        }, True

    mark(job_path, "cover", "running", "验收生图封面")
    if _cover_file_usable(cover_path):
        mark(
            job_path, "cover", "completed", "生图封面已就绪",
            {
                "backend": "image_generate",
                # 不要求 Agent 视觉审图；人工在草稿箱核对
                "visual_check": "none",
            },
            {"cover": cover_path},
        )
        return {"status": "completed", "backend": "image_generate", "reused": False}, True

    has_default = default_thumb_available(config_path, job["account"])
    if has_default:
        mark(
            job_path, "cover", "skipped", "无可用生图封面，使用账号默认封面",
            {
                "default_thumb_media_id": "true",
                "backend": "image_generate",
            },
        )
        return {"status": "skipped", "reason": "default-thumb"}, False

    mark(
        job_path, "cover", "failed",
        "缺少 cover/cover.png 生图封面，且无默认 thumb_media_id",
        {"backend": "image_generate"},
    )
    raise RuntimeFailure(
        "封面未生成：请用生图 API 写入 cover/cover.png，"
        "或配置账号 default_thumb_media_id"
    )


def lightweight_gate(job_path):
    gate_args = pipeline_job.build_parser().parse_args(
        ["gate", "--job", str(job_path)]
    )
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline_job.cmd_gate(gate_args)


def read_digest(artifacts):
    """可选摘要：工作区 digest.txt 的第一段非空文本，截断到微信上限 64 字。

    摘要显示在分享卡片与部分列表页，是标题之外的第二打开钩子；
    缺失时微信自动截取正文开头，允许无摘要继续，不作门禁。
    """
    digest_path = artifacts["article"].parent / "digest.txt"
    if not digest_path.is_file():
        return ""
    text = " ".join(digest_path.read_text(encoding="utf-8").split())
    return text[:64]


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
    digest = read_digest(artifacts)
    if digest:
        command.extend(("--digest", digest))
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
        safe_to_retry = draft_failure_is_retry_safe(str(exc)) or args.dry_run
        details = {
            "attempts": "1",
            "run_id": job["run_id"],
            "outcome": "preflight-failed" if safe_to_retry else "uncertain",
            "retry_safe": "true" if safe_to_retry else "false",
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
            # outcome/retry_safe 必须显式覆盖：mark 是合并写入，不覆盖的话
            # running 阶段留下的 outcome=pending / retry_safe=false 会一直挂在
            # 一个已经成功的任务上，事后排查时看起来像是失败过。
            {
                "attempts": "1", "run_id": job["run_id"],
                "outcome": "succeeded", "retry_safe": "n/a",
            },
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
        raise RuntimeFailure(UNCERTAIN_DRAFT_MESSAGE.format(job=args.job))
    if (
        draft_stage["status"] == "failed"
        and draft_details.get("outcome") == "uncertain"
    ):
        raise RuntimeFailure(UNCERTAIN_DRAFT_MESSAGE.format(job=args.job))
    existing_draft = verified_draft_result(job, artifacts)
    if existing_draft:
        return draft_resume_response(job, existing_draft)
    render_result = render_body(args.job, job, artifacts, roots)
    job, artifacts = job_paths(args.job)
    # HTML 封面已停用：只验收 Agent 生图产物 cover/cover.png
    cover_result, generated_cover = accept_cover(
        args.job, job, artifacts, config_path
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
    begin = sub.add_parser("begin", help="在 Agent 写作前启动计时并输出写作契约卡")
    begin.add_argument("--job", required=True)
    check = sub.add_parser("check", help="写作后自检：列出全部问题与修法，不改状态")
    check.add_argument("--job", required=True)
    prepare = sub.add_parser("prepare", help="核验正文、固定主题并等待唯一信息计划")
    prepare.add_argument("--job", required=True)
    finish = sub.add_parser("finish", help="一次完成排版、验收生图封面、校验和草稿")
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
            "check": cmd_check,
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
