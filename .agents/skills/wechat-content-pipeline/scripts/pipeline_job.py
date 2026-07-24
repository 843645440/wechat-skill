#!/usr/bin/env python3
"""维护公众号流水线的账号级临时工作区。"""

import argparse
import datetime as dt
import json
import os
import re
import secrets
import shutil
import sys
from urllib.parse import urlparse


STAGES = (
    "discover",
    "write",
    "humanize",
    "illustrations",
    "format",
    "cover",
    "draft",
)
STATUSES = ("pending", "running", "completed", "failed", "skipped")
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
THEME_RE = re.compile(r"references/theme-([a-z0-9][a-z0-9-]*)\.md")
THEME_SECTION_RE = re.compile(
    r"^## 已注册主题\s*$\n(?P<body>.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
)
PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}|【(?:插入|待补|待填写)[^】]*】")
TOPIC_HISTORY_VERSION = 2
TOPIC_HISTORY_MAX_ENTRIES = 100
TOPIC_DEDUP_DAYS = 7


class JobError(RuntimeError):
    pass


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def stage_record(status="pending", timestamp=None, message="", details=None):
    completed = timestamp if status in ("completed", "failed", "skipped") else None
    return {
        "status": status,
        "started_at": timestamp if status != "pending" else None,
        "completed_at": completed,
        "duration_ms": 0 if completed else None,
        "updated_at": timestamp,
        "message": message,
        "details": details or {},
    }


def atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def topic_history_path(job):
    job_dir = os.path.realpath(os.path.abspath(job.get("job_dir", "")))
    account_dir = os.path.dirname(job_dir)
    if os.path.basename(job_dir) != "current" or os.path.basename(account_dir) != job["account"]:
        raise JobError("选题历史路径不安全")
    return os.path.join(account_dir, "topic-history.json")


def load_topic_history(job):
    path = topic_history_path(job)
    if not os.path.exists(path):
        return {"version": TOPIC_HISTORY_VERSION, "account": job["account"], "topics": []}
    try:
        with open(path, encoding="utf-8") as f:
            history = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise JobError(f"无法读取选题历史 {path}: {exc}") from exc
    if (
        history.get("version") not in (1, TOPIC_HISTORY_VERSION)
        or history.get("account") != job["account"]
        or not isinstance(history.get("topics"), list)
    ):
        raise JobError("选题历史格式不受支持")
    if history.get("version") == 1:
        for entry in history["topics"]:
            if isinstance(entry, dict) and not entry.get("event_focus"):
                entry["event_focus"] = entry.get("topic", "")
        history["version"] = TOPIC_HISTORY_VERSION
    return history


def recent_topic_entries(history, now=None):
    current = now or dt.datetime.now(dt.timezone.utc)
    cutoff = current.astimezone(dt.timezone.utc) - dt.timedelta(days=TOPIC_DEDUP_DAYS)
    recent = []
    for entry in history["topics"]:
        if not isinstance(entry, dict):
            continue
        try:
            selected = parse_iso(entry.get("selected_at"))
        except (TypeError, ValueError):
            continue
        if selected is not None and selected.astimezone(dt.timezone.utc) >= cutoff:
            recent.append(entry)
    return recent


def record_topic_history(job, value, event_focus, selected_at=None):
    history = load_topic_history(job)
    selected_at = selected_at or now_iso()
    new_entry = {
        "topic": value,
        "event_focus": event_focus,
        "selected_at": selected_at,
    }
    topics = history["topics"]
    if not any(
        isinstance(entry, dict)
        and entry.get("topic") == value
        and entry.get("selected_at") == selected_at
        for entry in topics
    ):
        topics.append(new_entry)
    history["topics"] = topics[-TOPIC_HISTORY_MAX_ENTRIES:]
    atomic_write(topic_history_path(job), history)


def load_job(path):
    try:
        with open(path, encoding="utf-8") as f:
            job = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise JobError(f"无法读取任务清单 {path}: {exc}") from exc
    if job.get("schema_version") not in (4, 5) or not isinstance(job.get("stages"), dict):
        raise JobError("任务清单格式不受支持")
    for removed in ("fact-check", "validate"):
        job["stages"].pop(removed, None)
    for name in STAGES:
        job["stages"].setdefault(name, stage_record("pending"))
    for removed in ("sources", "preview"):
        job.get("artifacts", {}).pop(removed, None)
    if not job.get("run_id"):
        account = re.sub(r"[^a-zA-Z0-9_-]", "-", str(job.get("account", "unknown")))
        created = re.sub(r"[^a-zA-Z0-9_-]", "-", str(job.get("created_at", "unknown")))
        job["run_id"] = f"legacy-{account}-{created}"
    job["schema_version"] = 5
    return job


def save_job(path, job):
    job["updated_at"] = now_iso()
    atomic_write(path, job)


def summarize_state(job):
    stages = job["stages"]
    if any(item["status"] == "failed" for item in stages.values()):
        return "failed"
    if stages["draft"]["status"] == "completed":
        return "drafted"
    if stages["draft"]["status"] == "skipped":
        details = stages["draft"].get("details", {})
        if details.get("dry_run") == "true" and details.get("gate") == "passed":
            return "validated-dry-run"
        if details.get("gate") == "passed":
            return "validated"
    if any(item["status"] in ("running", "completed", "skipped") for item in stages.values()):
        return "running"
    return "initialized"


def resolve_work_dir(project_root, work_dir, account):
    base = work_dir if os.path.isabs(work_dir) else os.path.join(project_root, work_dir)
    base = os.path.realpath(os.path.abspath(base))
    job_dir = os.path.realpath(os.path.join(base, account, "current"))
    if os.path.commonpath((base, job_dir)) != base or job_dir == base:
        raise JobError("工作区路径不安全")
    return job_dir


def load_profiles(project_root, value):
    path = value if os.path.isabs(value) else os.path.join(project_root, value)
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise JobError(f"无法读取账号内容档案 {path}: {exc}") from exc
    profiles = config.get("profiles")
    if config.get("version") not in (4, 5) or not isinstance(profiles, dict):
        raise JobError("账号内容档案格式不受支持")
    return os.path.abspath(path), profiles


def cmd_init(args):
    if not ACCOUNT_RE.fullmatch(args.account):
        raise JobError("账号别名只能包含字母、数字、下划线和连字符")
    project_root = os.path.abspath(args.project_root)
    profiles_path, profiles = load_profiles(project_root, args.profiles)
    if args.account not in profiles:
        raise JobError(f"账号 {args.account} 未在内容档案中配置")
    profile = profiles[args.account]
    illustrations = profile.get("illustrations", {})
    cover = profile.get("cover", {})
    if (
        profile.get("theme_strategy") != "random"
        or illustrations.get("enabled") is not True
        or illustrations.get("skill") != "baoyu-article-illustrator"
        or illustrations.get("backend") != "image_generate"
        or type(illustrations.get("max_images")) is not int
        or not 1 <= illustrations["max_images"] <= 3
        or cover.get("enabled") is not True
        or cover.get("backend") != "html"
        or cover.get("aspect") != "2.35:1"
        or cover.get("theme") != "article"
        or cover.get("text") != "title-only"
        or profile.get("publishing", {}).get("target") != "draft"
        or not isinstance(profile.get("audience"), str)
        or not profile.get("audience", "").strip()
        or profile.get("topic_discovery", {}).get("max_age_hours") != 48
        or not profile.get("topic_discovery", {}).get("categories")
    ):
        raise JobError(
            "账号内容档案必须启用 Baoyu 正文配图、HTML 封面、随机主题，"
            "并以草稿箱为终点"
        )
    job_dir = resolve_work_dir(project_root, args.work_dir, args.account)
    if os.path.isdir(job_dir):
        current_job_path = os.path.join(job_dir, "job.json")
        if not args.force_new:
            if not os.path.isfile(current_job_path):
                raise JobError(
                    "现有工作区缺少 job.json，无法安全判定；"
                    "请先检查，确认丢弃后使用 --force-new"
                )
            try:
                current_job = load_job(current_job_path)
            except JobError as exc:
                raise JobError(
                    "现有工作区无法安全判定；请先检查，确认丢弃后使用 --force-new"
                ) from exc
            unresolved = [
                name for name, stage in current_job["stages"].items()
                if stage["status"] in ("running", "failed")
            ]
            if unresolved:
                raise JobError(
                    "现有工作区包含未解决阶段 " + ",".join(unresolved)
                    + "；请恢复现有任务，确认丢弃后使用 --force-new"
                )
        shutil.rmtree(job_dir)
    elif os.path.exists(job_dir):
        raise JobError(f"工作区路径不是目录：{job_dir}")
    os.makedirs(os.path.join(job_dir, "cover"))

    created = now_iso()
    has_topic = bool(args.topic and args.topic.strip())
    discover_status = "completed" if has_topic else "pending"
    job = {
        "schema_version": 5,
        "created_at": created,
        "updated_at": created,
        "project_root": project_root,
        "profiles_path": profiles_path,
        "job_dir": job_dir,
        "account": args.account,
        "run_id": secrets.token_hex(12),
        "topic": args.topic.strip() if has_topic else None,
        "topic_source": "provided" if has_topic else None,
        "state": "initialized",
        "artifacts": {
            "article": "article.md",
            "illustrations": "imgs",
            "cover": "cover/cover.png",
            "html": "article.html",
            "draft_result": "draft-result.json",
        },
        "stages": {
            name: stage_record(
                discover_status if name == "discover" else "pending",
                created if name == "discover" and has_topic else None,
                "使用触发请求提供的主题" if name == "discover" and has_topic else "",
                {"source": "provided"} if name == "discover" and has_topic else {},
            )
            for name in STAGES
        },
    }
    job["state"] = summarize_state(job)
    job_path = os.path.join(job_dir, "job.json")
    atomic_write(job_path, job)
    print(job_path)


def artifact_path(job_path, value):
    job_dir = os.path.dirname(os.path.realpath(os.path.abspath(job_path)))
    candidate = value if os.path.isabs(value) else os.path.join(job_dir, value)
    candidate = os.path.realpath(os.path.abspath(candidate))
    if os.path.commonpath((job_dir, candidate)) != job_dir:
        raise JobError("产物路径必须位于当前账号工作区内")
    return candidate, os.path.relpath(candidate, job_dir)


def parse_pairs(items, label, path_mode=False, job_path=None):
    parsed = {}
    for item in items or []:
        if "=" not in item:
            raise JobError(f"{label} 使用 key=value 格式")
        key, value = item.split("=", 1)
        if not key or not value:
            raise JobError(f"{label} 使用非空 key=value 格式")
        if path_mode:
            _, value = artifact_path(job_path, value)
        parsed[key] = value
    return parsed


def validate_auto_hotspot_metadata(job, now=None, details=None):
    """Validate the selected hotspot once, before it is persisted."""
    details = details or job.get("stages", {}).get("discover", {}).get("details", {})
    project_root = os.path.realpath(os.path.abspath(job.get("project_root", "")))
    profile_path = os.path.realpath(os.path.abspath(job.get("profiles_path", "")))
    if not project_root or os.path.commonpath((project_root, profile_path)) != project_root:
        raise JobError("热点元数据引用的账号档案路径不安全")
    try:
        with open(profile_path, encoding="utf-8") as f:
            discovery = json.load(f)["profiles"][job["account"]]["topic_discovery"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise JobError(f"热点元数据无法读取账号档案：{exc}") from exc

    category = details.get("category")
    event_focus = details.get("event_focus")
    published_text = details.get("published_at")
    if category not in discovery.get("categories", []):
        raise JobError("自动热点类别不属于当前账号类别")
    if not isinstance(event_focus, str) or not event_focus.strip():
        raise JobError("自动热点必须提供简短事件重点 event_focus")
    try:
        published = parse_iso(published_text)
    except (TypeError, ValueError) as exc:
        raise JobError(f"热点发布时间不合法：{published_text}") from exc
    if published is None or published.tzinfo is None:
        raise JobError("热点发布时间必须包含时区")
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise JobError("热点校验时间必须包含时区")
    age_hours = (
        current.astimezone(dt.timezone.utc) - published.astimezone(dt.timezone.utc)
    ).total_seconds() / 3600
    if not 0 <= age_hours <= discovery.get("max_age_hours", 48):
        raise JobError("自动热点必须位于最近 48 小时内")


def cmd_topic(args):
    value = args.value.strip()
    if not value:
        raise JobError("选题不能为空")
    job = load_job(args.job)
    details = {"source": args.source}
    if args.source == "auto-hotspot":
        details.update({
            "category": (args.category or "").strip(),
            "published_at": (args.published_at or "").strip(),
            "event_focus": (args.event_focus or "").strip(),
        })
        validate_auto_hotspot_metadata(job, details=details)

    job["topic"] = value
    job["topic_source"] = args.source
    finished = now_iso()
    current = job["stages"]["discover"]
    started = current.get("started_at") or finished
    duration = max(0, round((parse_iso(finished) - parse_iso(started)).total_seconds() * 1000))
    job["stages"]["discover"] = stage_record(
        "completed", started, "已确定本轮选题", details
    )
    job["stages"]["discover"].update(
        {"completed_at": finished, "duration_ms": duration, "updated_at": finished}
    )
    job["state"] = summarize_state(job)
    save_job(args.job, job)
    if args.source == "auto-hotspot":
        record_topic_history(job, value, details["event_focus"], selected_at=finished)
    print(value)


def cmd_history(args):
    job = load_job(args.job)
    history = load_topic_history(job)
    entries = recent_topic_entries(history)
    if args.days != TOPIC_DEDUP_DAYS:
        current = dt.datetime.now(dt.timezone.utc)
        cutoff = current - dt.timedelta(days=args.days)
        entries = [
            entry for entry in history["topics"]
            if isinstance(entry, dict)
            and parse_iso(entry.get("selected_at"))
            and parse_iso(entry["selected_at"]).astimezone(dt.timezone.utc) >= cutoff
        ]
    print(json.dumps(entries, ensure_ascii=False, indent=2))


def cmd_choose_theme(args):
    job = load_job(args.job)
    current = job["stages"]["format"].get("details", {}).get("theme")
    if current:
        print(current)
        return
    index_value = args.theme_index or os.path.join(
        job["project_root"], "references", "theme-index.md"
    )
    index_path = index_value if os.path.isabs(index_value) else os.path.join(
        job["project_root"], index_value
    )
    try:
        with open(index_path, encoding="utf-8") as f:
            index_text = f.read()
    except OSError as exc:
        raise JobError(f"无法读取主题索引 {index_path}: {exc}") from exc
    section = THEME_SECTION_RE.search(index_text)
    if not section:
        raise JobError("主题索引缺少“已注册主题”章节")
    registered = list(dict.fromkeys(THEME_RE.findall(section.group("body"))))
    if not registered:
        raise JobError("主题索引中没有已注册主题")
    requested = list(dict.fromkeys(item.strip() for item in args.theme if item.strip()))
    unknown = sorted(set(requested) - set(registered))
    if unknown:
        raise JobError(f"主题未在索引中注册：{', '.join(unknown)}")
    themes = requested or registered
    selected = secrets.choice(themes)
    stage = job["stages"]["format"]
    stage.setdefault("details", {})["theme"] = selected
    stage["updated_at"] = now_iso()
    save_job(args.job, job)
    print(selected)


def cmd_stage(args):
    job = load_job(args.job)
    item = job["stages"][args.name]
    timestamp = now_iso()
    if (
        args.name in ("humanize", "illustrations")
        and args.status == "completed"
        and item.get("status") == "pending"
    ):
        raise JobError(f"阶段 {args.name} 完成前必须先标记 running")
    if args.status == "pending":
        item.update(
            {
                "status": "pending", "started_at": None, "completed_at": None,
                "duration_ms": None, "updated_at": timestamp, "details": {},
            }
        )
    elif args.status == "running":
        if item.get("status") != "running" or not item.get("started_at"):
            item["started_at"] = timestamp
            item["details"] = {}
        item.update(
            {
                "status": "running", "completed_at": None,
                "duration_ms": None, "updated_at": timestamp,
            }
        )
    else:
        started = item.get("started_at") or timestamp
        item.update(
            {
                "status": args.status, "started_at": started,
                "completed_at": timestamp,
                "duration_ms": max(
                    0,
                    round((parse_iso(timestamp) - parse_iso(started)).total_seconds() * 1000),
                ),
                "updated_at": timestamp,
            }
        )
    if args.message is not None:
        item["message"] = args.message
    item.setdefault("details", {}).update(
        parse_pairs(args.detail, "--detail")
    )
    job["artifacts"].update(
        parse_pairs(args.artifact, "--artifact", True, args.job)
    )
    job["state"] = summarize_state(job)
    save_job(args.job, job)
    print(json.dumps({"stage": args.name, "status": args.status, "state": job["state"]}, ensure_ascii=False))


def validate_ready_html(job_path, job):
    html_value = job["artifacts"].get("html", "article.html")
    html_path, _ = artifact_path(job_path, html_value)
    try:
        with open(html_path, encoding="utf-8") as f:
            html = f.read()
    except OSError as exc:
        raise JobError(f"无法读取排版产物：{exc}") from exc
    match = PLACEHOLDER_RE.search(html)
    if match:
        raise JobError(f"排版产物仍包含占位内容：{match.group(0)}")


def validate_illustration_stage(job):
    status = job["stages"]["illustrations"]["status"]
    if status not in ("completed", "skipped"):
        raise JobError("阶段 illustrations 尚未完成或降级")


def cmd_gate(args):
    job = load_job(args.job)
    for stage_name in ("discover", "write", "humanize", "format"):
        if job["stages"][stage_name]["status"] != "completed":
            raise JobError(f"阶段 {stage_name} 尚未完成")
    validate_illustration_stage(job)
    validate_ready_html(args.job, job)
    cover_stage = job["stages"]["cover"]
    has_generated_cover = cover_stage["status"] == "completed"
    has_default_cover = (
        cover_stage["status"] == "skipped"
        and cover_stage.get("details", {}).get("default_thumb_media_id") == "true"
    )
    if not (has_generated_cover or has_default_cover):
        raise JobError("封面尚未生成，且未确认账号默认封面素材可用")
    print(json.dumps({"allowed": True, "action": "draft", "account": job["account"]}, ensure_ascii=False))


def cmd_show(args):
    print(json.dumps(load_job(args.job), ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description="公众号内容流水线账号工作区工具")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="重建指定账号的 current 工作区")
    init.add_argument("--project-root", default=".")
    init.add_argument("--work-dir", default="work")
    init.add_argument("--profiles", default="config/wechat-content-profiles.json")
    init.add_argument("--account", required=True)
    init.add_argument("--topic")
    init.add_argument(
        "--force-new", action="store_true",
        help="明确丢弃现有 running/failed 工作区并新建任务",
    )

    topic = sub.add_parser("topic", help="记录自动发现或外部提供的选题")
    topic.add_argument("--job", required=True)
    topic.add_argument("--value", required=True)
    topic.add_argument("--source", choices=("provided", "auto-hotspot"), required=True)
    topic.add_argument("--category")
    topic.add_argument("--published-at")
    topic.add_argument("--event-focus")

    history = sub.add_parser("history", help="输出近期选题重点供 Agent 做语义去重")
    history.add_argument("--job", required=True)
    history.add_argument("--days", type=int, default=7)

    choose = sub.add_parser("choose-theme", help="从已注册主题中随机选择并固定本轮主题")
    choose.add_argument("--job", required=True)
    choose.add_argument("--theme", action="append", default=[])
    choose.add_argument("--theme-index")

    stage = sub.add_parser("stage", help="更新阶段状态和产物")
    stage.add_argument("--job", required=True)
    stage.add_argument("--name", choices=STAGES, required=True)
    stage.add_argument("--status", choices=STATUSES, required=True)
    stage.add_argument("--message")
    stage.add_argument("--artifact", action="append", default=[])
    stage.add_argument("--detail", action="append", default=[])

    gate = sub.add_parser("gate", help="检查自动创建草稿的确定性门禁")
    gate.add_argument("--job", required=True)

    show = sub.add_parser("show", aliases=("status",), help="输出当前账号任务清单")
    show.add_argument("--job", required=True)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        {
            "init": cmd_init,
            "topic": cmd_topic,
            "history": cmd_history,
            "choose-theme": cmd_choose_theme,
            "stage": cmd_stage,
            "gate": cmd_gate,
            "show": cmd_show,
            "status": cmd_show,
        }[args.command](args)
    except JobError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
