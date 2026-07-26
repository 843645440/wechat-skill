#!/usr/bin/env python3
"""维护公众号流水线的账号级临时工作区。"""

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import secrets
import shlex
import shutil
import sys
from urllib.parse import urlparse


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Skill 根目录（scripts/ 的上一级），与 pipeline_runtime.py 的 command_roots()["pipeline"] 一致；
# 用绝对路径拼后续命令，弱模型不必自己算「向上三级」。
PIPELINE_ROOT = os.path.dirname(SCRIPT_DIR)

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
PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}|【(?:插入|待补|待填写)[^】]*】")
TOPIC_HISTORY_VERSION = 2
TOPIC_HISTORY_MAX_ENTRIES = 100
TOPIC_DEDUP_DAYS = 7

# 写作结构池（防同质/限流）：与 wechat-tech-insight-writer article-structures 对齐
STRUCTURE_IDS = (
    "felt_essay",
    "conflict",
    "myth_bust",
    "workflow_day",
    "judgment_first",
    "sting_list",
    "qa_drive",
    "quick_take",
    "event_read",
    "tech_explain",
    "company_compete",
    "industry_game",
    "tech_livelihood",
    "non_invest_finance",
)
OPENING_TYPES = (
    "emotion_sting",
    "contrast",
    "myth",
    "scene",
    "judgment_first",
    "date_announce",
)
ENDING_TYPES = (
    "duty_point",
    "unresolved",
    "actionable_question",
    "hook_return",
    "brief_approval",
)
TENSION_TYPES = (
    "efficiency_vs_duty",
    "demo_vs_deploy",
    "cheap_vs_trust",
    "speed_vs_safety",
    "access_vs_privacy",
    "hype_vs_adoption",
    "other",
)
BODY_BANDS = ("short", "mid", "long")
SHAPE_KEYS = (
    "structure_id",
    "opening_type",
    "ending_type",
    "felt_sense",
    "tension_type",
    "heading_count",
    "body_band",
)

# 谁负责把这个阶段往前推：agent 手动 stage 记账，还是 pipeline_runtime.py 自动设置。
# 供 init/topic/shape/stage/show 的 job_contract 直接展示，弱模型不必去 artifact-contract.md 查表。
STAGE_OWNERS = {
    "discover": "agent：topic 命令写入选题",
    "write": "pipeline_runtime.py begin（标记 running）/ prepare（标记 completed）",
    "humanize": "agent：stage --name humanize --status running → 改写 → --status completed",
    "illustrations": "agent：配图或用户图就绪后 stage --name illustrations --status completed/skipped",
    "format": "pipeline_runtime.py finish 自动固定主题并排版",
    "cover": "agent 生成/放置 cover/cover.png，pipeline_runtime.py finish 验收",
    "draft": "pipeline_runtime.py finish 自动创建公众号草稿",
}

# 写作正文字数硬门禁的展示副本；唯一数字来源是 pipeline_runtime.py 的 MIN/MAX_BODY_CHARS，
# 这里只用于 job_contract 里给账号档案摘要提供参考区间，两边改动需同步。
JOB_MIN_BODY_CHARS = 1500
JOB_MAX_BODY_CHARS = 4000

# 防御性脱敏：账号内容档案本不应包含凭证（AppID/AppSecret/token 存在 wechat-accounts.json，
# 且只存环境变量名），但仍递归剔除任何形似凭证的字段名，防止未来误加字段后被 init 打到 stdout。
CREDENTIAL_KEY_RE = re.compile(
    r"secret|token|app[_-]?id|access[_-]?token|api[_-]?key|apikey|password|passwd|media_id",
    re.IGNORECASE,
)


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


def record_topic_history(job, value, event_focus, selected_at=None, story=None):
    history = load_topic_history(job)
    selected_at = selected_at or now_iso()
    new_entry = {
        "topic": value,
        "event_focus": event_focus or value,
        "selected_at": selected_at,
        "run_id": job.get("run_id"),
    }
    story = story or {}
    for key in ("hook", "tension", "reader_stakes"):
        text = story.get(key)
        if isinstance(text, str) and text.strip():
            new_entry[key] = text.strip()
    for key in SHAPE_KEYS:
        if key in story and story[key] not in (None, ""):
            new_entry[key] = story[key]
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


def compute_rotation_plan(entries):
    """根据近文历史给出禁用/告警结构，供 Agent 选题写作前阅读。"""
    timed = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            selected = parse_iso(entry.get("selected_at"))
        except (TypeError, ValueError):
            selected = None
        timed.append((selected or dt.datetime.min.replace(tzinfo=dt.timezone.utc), entry))
    timed.sort(key=lambda item: item[0], reverse=True)
    last7 = [e for _, e in timed[:7]]
    last5 = [e for _, e in timed[:5]]
    last3 = [e for _, e in timed[:3]]

    structure_counts = {}
    for entry in last7:
        sid = entry.get("structure_id")
        if sid:
            structure_counts[sid] = structure_counts.get(sid, 0) + 1
    blocked_structures = sorted(
        sid for sid, count in structure_counts.items() if count >= 2
    )
    recent_structures = [e.get("structure_id") for e in last3 if e.get("structure_id")]
    def rotation_block(values_5, values_3, pool):
        """近5篇不重复；若把整个池都堵死（如 ending 池恰好 5 种、近 5 篇各用一种），
        自动收缩到近3篇窗口，保证永远至少有一个合法选项，避免生产死锁。"""
        blocked = sorted({v for v in values_5 if v})
        if all(option in blocked for option in pool):
            blocked = sorted({v for v in values_3 if v})
        return blocked

    # opening 的可用池不含 date_announce（不推荐）：非 date 选项全被堵死时即视为耗尽
    blocked_openings = rotation_block(
        [e.get("opening_type") for e in last5],
        [e.get("opening_type") for e in last3],
        [o for o in OPENING_TYPES if o != "date_announce"],
    )
    blocked_endings = rotation_block(
        [e.get("ending_type") for e in last5],
        [e.get("ending_type") for e in last3],
        ENDING_TYPES,
    )
    tension_counts = {}
    for entry in last5:
        tid = entry.get("tension_type")
        if tid:
            tension_counts[tid] = tension_counts.get(tid, 0) + 1
    blocked_tensions = sorted(
        tid for tid, count in tension_counts.items() if count >= 2
    )
    recent_felt = [e.get("felt_sense") for e in last3 if e.get("felt_sense")]
    preferred_structures = [
        sid for sid in STRUCTURE_IDS
        if sid not in blocked_structures and sid not in recent_structures
    ]
    if not preferred_structures:
        preferred_structures = [
            sid for sid in STRUCTURE_IDS if sid not in blocked_structures
        ]
    preferred_openings = [
        o for o in OPENING_TYPES if o not in blocked_openings and o != "date_announce"
    ]
    if not preferred_openings:
        preferred_openings = ["date_announce"]
    preferred_endings = [e for e in ENDING_TYPES if e not in blocked_endings]
    return {
        "window": {
            "structure_lookback": 7,
            "opening_ending_lookback": 5,
            "recent_structure_lookback": 3,
        },
        "rules": {
            "structure_id": "近7篇同一 structure_id 最多2次；且尽量避开近3篇已用",
            "opening_type": "近5篇 opening_type 不得重复（池将耗尽时自动放宽为近3篇）；慎用 date_announce",
            "ending_type": "近5篇 ending_type 不得重复（池将耗尽时自动放宽为近3篇）",
            "tension_type": "近5篇同一 tension_type 最多2次",
            "felt_sense": "近3篇主情绪尽量不雷同",
            "heading_count": "2–5 轮换，禁止连三篇相同个数",
            "body_band": "short/mid/long 轮换",
        },
        "blocked_structures": blocked_structures,
        "recent_structures": recent_structures,
        "blocked_openings": blocked_openings,
        "blocked_endings": blocked_endings,
        "blocked_tensions": blocked_tensions,
        "recent_felt_senses": recent_felt,
        "preferred_structures": preferred_structures,
        "preferred_openings": preferred_openings or list(OPENING_TYPES),
        "preferred_endings": preferred_endings or list(ENDING_TYPES),
        "structure_counts_last7": structure_counts,
        "allowed_structure_ids": list(STRUCTURE_IDS),
        "allowed_opening_types": list(OPENING_TYPES),
        "allowed_ending_types": list(ENDING_TYPES),
        "allowed_tension_types": list(TENSION_TYPES),
        "allowed_body_bands": list(BODY_BANDS),
    }


def validate_shape_against_history(entries, shape, *, enforce=True):
    plan = compute_rotation_plan(entries)
    errors = []
    sid = shape.get("structure_id")
    if sid in plan["blocked_structures"]:
        errors.append(f"structure_id={sid} 在近7篇已用满2次，必须换结构")
    if sid and sid in plan["recent_structures"] and len(plan["preferred_structures"]) > 0:
        # Soft block for last-3 if alternatives exist
        if sid in plan["recent_structures"]:
            errors.append(
                f"structure_id={sid} 出现在近3篇，请改用 preferred_structures 之一"
            )
    opening = shape.get("opening_type")
    if opening in plan["blocked_openings"]:
        errors.append(f"opening_type={opening} 在近5篇已出现，必须换开头类型")
    ending = shape.get("ending_type")
    if ending in plan["blocked_endings"]:
        errors.append(f"ending_type={ending} 在近5篇已出现，必须换结尾类型")
    tension = shape.get("tension_type")
    if tension in plan["blocked_tensions"]:
        errors.append(f"tension_type={tension} 在近5篇已用满2次，请换矛盾类型")
    # heading_count: no three identical in a row
    timed = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            selected = parse_iso(entry.get("selected_at"))
        except (TypeError, ValueError):
            selected = None
        timed.append((selected or dt.datetime.min.replace(tzinfo=dt.timezone.utc), entry))
    timed.sort(key=lambda item: item[0], reverse=True)
    last_heads = [
        e.get("heading_count") for _, e in timed[:3]
        if e.get("heading_count") is not None
    ]
    hc = shape.get("heading_count")
    if (
        hc is not None
        and len(last_heads) >= 2
        and last_heads[0] == last_heads[1] == hc
    ):
        errors.append(f"heading_count={hc} 已连续两篇相同，请换 2–5 中的其他个数")
    if enforce and errors:
        raise JobError("；".join(errors))
    return errors


# --auto 的候选主情绪池（与账号 allowed_emotions 气质兼容的通用短词）
FELT_SENSE_POOL = ("烦", "发紧", "不安", "无力", "讽刺", "谨慎的兴奋", "振奋", "欣慰")


def auto_shape_from_history(entries, run_id, overrides=None):
    """按轮换计划确定性生成一个合法 shape（弱模型免选型）。

    同一 run_id 结果稳定可复跑；显式传入的字段优先于自动选择。
    所有选择都来自 preferred/allowed 列表，构造即合法。
    """
    plan = compute_rotation_plan(entries)
    rng = random.Random(str(run_id))
    overrides = {k: v for k, v in (overrides or {}).items() if v}

    structures = plan["preferred_structures"] or [
        s for s in STRUCTURE_IDS if s not in plan["blocked_structures"]
    ] or list(STRUCTURE_IDS)
    openings = plan["preferred_openings"] or ["date_announce"]
    endings = plan["preferred_endings"] or list(ENDING_TYPES)
    tensions = [
        t for t in TENSION_TYPES if t not in plan["blocked_tensions"]
    ] or list(TENSION_TYPES)
    felts = [f for f in FELT_SENSE_POOL if f not in plan["recent_felt_senses"]] \
        or list(FELT_SENSE_POOL)

    timed = sorted(
        (e for e in entries if isinstance(e, dict)),
        key=lambda e: e.get("selected_at") or "",
        reverse=True,
    )
    last_heads = [
        e.get("heading_count") for e in timed[:2]
        if e.get("heading_count") is not None
    ]
    heads = [h for h in (3, 4, 5) if not (
        len(last_heads) >= 2 and last_heads[0] == last_heads[1] == h
    )]
    last_band = next(
        (e.get("body_band") for e in timed if e.get("body_band")), None
    )
    bands = [b for b in BODY_BANDS if b != last_band] or list(BODY_BANDS)

    shape = {
        "structure_id": rng.choice(structures),
        "opening_type": rng.choice(openings),
        "ending_type": rng.choice(endings),
        "felt_sense": rng.choice(felts),
        "tension_type": rng.choice(tensions),
        "heading_count": rng.choice(heads),
        "body_band": rng.choice(bands),
    }
    shape.update(overrides)
    return shape


def parse_shape_from_args(args):
    shape = {
        "structure_id": (args.structure_id or "").strip(),
        "opening_type": (args.opening_type or "").strip(),
        "ending_type": (args.ending_type or "").strip(),
        "felt_sense": (getattr(args, "felt_sense", None) or "").strip(),
        "tension_type": (getattr(args, "tension_type", None) or "").strip(),
        "body_band": (getattr(args, "body_band", None) or "").strip(),
    }
    if getattr(args, "heading_count", None) is not None:
        shape["heading_count"] = int(args.heading_count)
    if shape["structure_id"] not in STRUCTURE_IDS:
        raise JobError(
            f"structure_id 无效，可选：{', '.join(STRUCTURE_IDS)}"
        )
    if shape["opening_type"] not in OPENING_TYPES:
        raise JobError(
            f"opening_type 无效，可选：{', '.join(OPENING_TYPES)}"
        )
    if shape["ending_type"] not in ENDING_TYPES:
        raise JobError(
            f"ending_type 无效，可选：{', '.join(ENDING_TYPES)}"
        )
    if shape["tension_type"] and shape["tension_type"] not in TENSION_TYPES:
        raise JobError(
            f"tension_type 无效，可选：{', '.join(TENSION_TYPES)}"
        )
    if shape["body_band"] and shape["body_band"] not in BODY_BANDS:
        raise JobError(f"body_band 无效，可选：{', '.join(BODY_BANDS)}")
    if "heading_count" in shape and not 2 <= shape["heading_count"] <= 5:
        raise JobError("heading_count 必须在 2–5")
    if shape["opening_type"] == "date_announce":
        # allowed but discouraged — still valid enum
        pass
    # drop empty optionals
    return {k: v for k, v in shape.items() if v not in (None, "")}


def merge_shape_into_history(job, shape):
    history = load_topic_history(job)
    topics = history["topics"]
    run_id = job.get("run_id")
    updated = False
    for entry in reversed(topics):
        if not isinstance(entry, dict):
            continue
        if run_id and entry.get("run_id") == run_id:
            entry.update(shape)
            updated = True
            break
        if (
            not updated
            and entry.get("topic") == job.get("topic")
            and not entry.get("structure_id")
        ):
            entry.update(shape)
            if run_id:
                entry["run_id"] = run_id
            updated = True
            break
    if not updated and job.get("topic"):
        topics.append({
            "topic": job["topic"],
            "event_focus": job.get("event_focus") or job["topic"],
            "selected_at": now_iso(),
            "run_id": run_id,
            **shape,
        })
        history["topics"] = topics[-TOPIC_HISTORY_MAX_ENTRIES:]
        updated = True
    if updated:
        atomic_write(topic_history_path(job), history)
    return updated


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
    if config.get("version") not in (4, 5, 6) or not isinstance(profiles, dict):
        raise JobError("账号内容档案格式不受支持")
    return os.path.abspath(path), profiles


def _scrub_credentials(value):
    """递归剔除任何形似凭证的字段，值一律替换为 ***redacted***，键名不变。"""
    if isinstance(value, dict):
        return {
            key: ("***redacted***" if isinstance(key, str) and CREDENTIAL_KEY_RE.search(key)
                  else _scrub_credentials(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_credentials(item) for item in value]
    return value


def safe_profile_summary(profile):
    """账号内容偏好摘要：只白名单摘录内容类字段（声口/受众/配图封面偏好），
    供 init 直接打印，agent 不必再读 references/account-profiles.md。

    账号内容档案（config/wechat-content-profiles.json）本身按约定不存凭证——
    AppID/AppSecret/token 只存在 wechat-accounts.json 且只存环境变量名——
    这里仍白名单 + 二次脱敏，防止未来误加字段。字段缺失时静默跳过，不抛异常。
    """
    profile = profile or {}
    illustrations = profile.get("illustrations") or {}
    cover = profile.get("cover") or {}
    topic_discovery = profile.get("topic_discovery") or {}
    voice = profile.get("voice") or {}
    voice_summary = {
        key: voice[key]
        for key in (
            "tone", "emotion_level", "narrator", "title_style",
            "allowed_emotions", "banned_title_patterns", "signature_moves",
        )
        if key in voice
    }
    summary = {
        "label": profile.get("label") or "",
        "audience": profile.get("audience") or "",
        "input_mode": profile.get("input_mode") or "",
        "writer_instructions": profile.get("writer_instructions") or "",
        "voice": voice_summary,
        "body_chars_range": f"{JOB_MIN_BODY_CHARS}-{JOB_MAX_BODY_CHARS}",
        "illustrations": {
            "enabled": illustrations.get("enabled", False),
            "backend": illustrations.get("backend", ""),
            "max_images": illustrations.get("max_images", 0),
        },
        "cover": {
            "backend": cover.get("backend", ""),
            "aspect": cover.get("aspect", ""),
        },
        "auto_topic_discovery_enabled": topic_discovery.get("enabled", False),
        "publishing_target": (profile.get("publishing") or {}).get("target", ""),
    }
    if not summary["writer_instructions"]:
        summary["hint"] = "账号档案缺少 writer_instructions；写作前仍需人工确认声口偏好"
    if not voice_summary:
        summary.setdefault("hint", "账号档案缺少 voice 细则；按 writer_instructions 与安全默认声口写作")
    return _scrub_credentials(summary)


def _script_command(job_path, script_name, subcommand, *extra):
    """拼出可直接复制执行的固定入口命令，job_path 用绝对路径，弱模型不必自己拼路径。"""
    parts = [
        "python3",
        shlex.quote(os.path.join(PIPELINE_ROOT, "scripts", script_name)),
        subcommand,
        "--job",
        shlex.quote(os.path.abspath(str(job_path))),
    ]
    parts.extend(shlex.quote(str(item)) for item in extra)
    return " ".join(parts)


def job_script_command(job_path, subcommand, *extra):
    return _script_command(job_path, "pipeline_job.py", subcommand, *extra)


def inline_images_command(job, job_path):
    """正文配图的唯一入口：一条命令跑完「用户图优先 → 生图 → 生不出就不配图」，
    并顺手把 illustrations 阶段记账完（running → completed/skipped）。

    退出码恒为 0，stdout 一行 JSON 给出 status/backend。agent 不需要自己分析文章、
    挑插图位、构造 prompt，也不需要再补 stage 命令——漏标 running 曾是这一环最常
    见的失败方式。
    """
    # 注意键名是 job_dir，不是 work_dir——后者只是 job_contract 对外展示时用的名字。
    job_dir = os.path.abspath(job["job_dir"])
    artifacts = job.get("artifacts", {})
    return " ".join([
        "python3",
        shlex.quote(os.path.join(PIPELINE_ROOT, "scripts", "gen_inline_images.py")),
        "--article",
        shlex.quote(os.path.join(job_dir, artifacts.get("article", "article.md"))),
        "--imgs-dir",
        shlex.quote(os.path.join(job_dir, artifacts.get("illustrations", "imgs"))),
        "--seed", shlex.quote(str(job.get("run_id", ""))),
        "--job", shlex.quote(os.path.abspath(str(job_path))),
        "--record-stage",
    ])


def cover_command(job, job_path):
    """封面的唯一入口：用户图优先 → 生图 → 离线兜底，并记账 cover 阶段。

    封面是 finish 的硬门禁（正文图可以没有，封面不能），所以这条命令的降级链
    一直走到能出图为止，不给 agent 留「这一步能不能跳过」的判断空间。
    """
    return " ".join([
        "python3",
        shlex.quote(os.path.join(PIPELINE_ROOT, "scripts", "gen_cover_image.py")),
        "--job", shlex.quote(os.path.abspath(str(job_path))),
        "--record-stage",
    ])


def runtime_script_command(job_path, subcommand, *extra):
    return _script_command(job_path, "pipeline_runtime.py", subcommand, *extra)


def suggest_next_command(job, job_path):
    """给出下一条该跑的完整命令：init 之后每个子命令的 stdout 都靠它形成不读文档的命令链。

    只依据 job.json 已记录的状态推断，和 pipeline_runtime.py 里 begin → check → humanize
    → illustrations → prepare → finish 的固定顺序一致；agent 手动记账的阶段只有
    humanize 和 illustrations，其余阶段由 pipeline_runtime.py 自动设置（见 STAGE_OWNERS）。
    """
    stages = job["stages"]
    draft = stages["draft"]
    if draft["status"] == "completed":
        return "本轮已完成：draft 已 completed，用 show 核对 draft-result.json 后结束本轮"
    if draft["status"] == "failed":
        if draft.get("details", {}).get("outcome") == "uncertain":
            return (
                "draft 结果不确定：先人工核对微信公众号草稿箱，确认后把 draft 阶段"
                "重置为 pending，再重跑 finish；禁止自动重发"
            )
        return runtime_script_command(job_path, "finish") + "  # 上次 finish 失败，处理报错原因后重试"
    # init 已经把 --topic 写进 job["topic"]，所以不能只看 topic 有没有值，否则整个
    # topic 步骤会被跳过、event_focus 永远为空。以 event_focus 是否落定为准。
    if not job.get("event_focus"):
        brief_path = os.path.join(os.path.abspath(job["job_dir"]), "user-brief.md")
        prefix = ""
        if not os.path.exists(brief_path):
            prefix = (
                f"先把用户 brief 落盘到 {brief_path}"
                "（主题 + 大致思路，格式见 references/user-brief.md），再跑："
            )
        return prefix + job_script_command(
            job_path, "topic",
            "--value", str(job.get("topic") or "<用户主题，原样填入>"),
            "--source", "provided",
            "--event-focus", "<一句话核心，从 brief 提炼>",
        )
    if not job.get("article_shape"):
        return job_script_command(job_path, "shape", "--auto")
    write_status = stages["write"]["status"]
    if write_status == "pending":
        return runtime_script_command(job_path, "begin")
    if write_status == "completed":
        return runtime_script_command(job_path, "finish")
    # write == running：按 humanize → illustrations → prepare 的固定顺序推进
    if stages["humanize"]["status"] == "pending":
        return (
            runtime_script_command(job_path, "check")
            + "  # 写完先自检；通过后 stage --name humanize --status running"
        )
    if stages["humanize"]["status"] == "running":
        return job_script_command(
            job_path, "stage", "--name", "humanize", "--status", "completed",
            "--detail", "intensity=strong",
        )
    if stages["illustrations"]["status"] == "pending":
        return (
            inline_images_command(job, job_path)
            + "  # 退出码恒为 0，自己记账 running→completed/skipped，跑完直接看下一条 next_command"
        )
    if stages["illustrations"]["status"] == "running":
        # 只有手工标过 running 才会走到这里；--record-stage 路径不经过这一支。
        return job_script_command(
            job_path, "stage", "--name", "illustrations", "--status", "completed",
            "--detail", "backend=<user_provided|image_generate>",
        )
    # 封面是 finish 的硬门禁，必须排在 prepare 之前显式给出——漏掉这一步会一路
    # 走到 finish 才因为「封面缺失」失败，那时再回头补是最贵的。
    if stages["cover"]["status"] in ("pending", "running"):
        return (
            cover_command(job, job_path)
            + "  # 退出码恒为 0，自己记账；用户图优先→生图→离线兜底，保证有封面"
        )
    return runtime_script_command(job_path, "prepare")


def build_job_contract(job, job_path, profile, rebuilt_existing):
    """把 init 之后 agent 原本要读 artifact-contract.md + account-profiles.md 才知道的
    结构性事实压成一张机器可读卡片：绝对路径、阶段清单、账号偏好、下一条命令。
    风格与 pipeline_runtime.py 的 writing_contract 一致：字段值本身就是可执行指令或说明。
    """
    job_dir = job["job_dir"]
    artifacts = job["artifacts"]

    def _p(rel):
        return os.path.join(job_dir, rel)

    stage_roster = [
        {
            "stage": name,
            "status": job["stages"][name]["status"],
            "advanced_by": STAGE_OWNERS.get(name, "agent"),
        }
        for name in STAGES
    ]
    return {
        "run_id": job["run_id"],
        "account": job["account"],
        "topic": job.get("topic"),
        "state": job["state"],
        "paths": {
            "work_dir": job_dir,
            "job_path": os.path.abspath(str(job_path)),
            "article_path": _p(artifacts.get("article", "article.md")),
            "digest_path": _p("digest.txt"),
            "imgs_dir": _p(artifacts.get("illustrations", "imgs")),
            "cover_path": _p(artifacts.get("cover", "cover/cover.png")),
            "html_path": _p(artifacts.get("html", "article.html")),
            "draft_result_path": _p(artifacts.get("draft_result", "draft-result.json")),
        },
        "stages": stage_roster,
        "account_profile": safe_profile_summary(profile),
        "workspace_reset": {
            "rebuilt_existing_workspace": rebuilt_existing,
            "warning": "本次 init 已清空重建 work/<account>/current/；若工作区此前已存在，"
            "其正文、配图、封面均已被清空，不会残留误用。",
        },
        "user_brief_order_warning": (
            "user-brief.md 必须在本次 init 之后写入 " + _p("user-brief.md")
            + "；写在 init 之前会被本次清空重建覆盖掉（已知陷阱，顺序反了会丢文件）。"
        ),
        "next_command": suggest_next_command(job, job_path),
    }


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
        # 正文配图已收敛为 gen_inline_images.py 一条命令；旧档案里的
        # baoyu-article-illustrator 仍然接受（已归档到 archive/），避免存量账号 init 失败。
        or illustrations.get("skill") not in (
            "gen_inline_images", "baoyu-article-illustrator"
        )
        or illustrations.get("backend") != "image_generate"
        or type(illustrations.get("max_images")) is not int
        or not 1 <= illustrations["max_images"] <= 3
        or cover.get("enabled") is not True
        or cover.get("backend") != "image_generate"
        or cover.get("aspect") not in ("16:9", "2.35:1", "20:9", "3:2")
        or profile.get("publishing", {}).get("target") != "draft"
        or not isinstance(profile.get("audience"), str)
        or not profile.get("audience", "").strip()
        or profile.get("topic_discovery", {}).get("max_age_hours") != 48
        or not profile.get("topic_discovery", {}).get("categories")
    ):
        raise JobError(
            "账号内容档案必须启用 Baoyu 正文配图、生图 API 封面、随机主题，"
            "并以草稿箱为终点"
        )
    job_dir = resolve_work_dir(project_root, args.work_dir, args.account)
    existed_before = os.path.isdir(job_dir)
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
    # stdout 只放合法 JSON，和 topic/shape/stage 等所有其他子命令保持一致，
    # 这样 `... init ... | jq` 或 json.load(stdin) 都能直接用。
    # 早先这里会先打一行纯 job_path 做「向后兼容」，代价是整段 stdout 不是合法
    # JSON——解析器一上来就报 Expecting value，而 job_path 本来就在
    # job_contract.paths.job_path 里，那一行没有信息增量。路径改走 stderr，
    # 人肉 cat 时照样看得见，管道解析不受影响。
    print(job_path, file=sys.stderr)
    print(json.dumps(
        {"job_contract": build_job_contract(job, job_path, profile, existed_before)},
        ensure_ascii=False, indent=2,
    ))


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
    for key, label in (
        ("hook", "点击钩子 hook"),
        ("tension", "核心矛盾 tension"),
        ("reader_stakes", "读者代价 reader_stakes"),
    ):
        text = details.get(key)
        if not isinstance(text, str) or not text.strip():
            raise JobError(f"自动热点必须提供{label}，禁止无故事核的说明书选题")
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


def topic_discovery_enabled(job):
    """Auto hotspot is off unless profile explicitly sets topic_discovery.enabled=true."""
    try:
        with open(job["profiles_path"], encoding="utf-8") as f:
            profile = json.load(f)["profiles"][job["account"]]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return False
    discovery = profile.get("topic_discovery") or {}
    if profile.get("input_mode") == "user_brief_only":
        return False
    return discovery.get("enabled") is True


def cmd_topic(args):
    value = args.value.strip()
    if not value:
        raise JobError("选题不能为空")
    job = load_job(args.job)
    details = {"source": args.source}
    if args.source == "auto-hotspot":
        if not topic_discovery_enabled(job):
            raise JobError(
                "当前账号已关闭自动选题（input_mode=user_brief_only 或 "
                "topic_discovery.enabled!=true）。请使用 --source provided，"
                "并由用户提供主题与思路；见 references/user-brief.md"
            )
        details.update({
            "category": (args.category or "").strip(),
            "published_at": (args.published_at or "").strip(),
            "event_focus": (args.event_focus or "").strip(),
            "hook": (args.hook or "").strip(),
            "tension": (args.tension or "").strip(),
            "reader_stakes": (args.reader_stakes or "").strip(),
        })
        validate_auto_hotspot_metadata(job, details=details)
    else:
        # User brief / externally provided topic: no 48h gate.
        for key, attr in (
            ("hook", "hook"),
            ("tension", "tension"),
            ("reader_stakes", "reader_stakes"),
            ("event_focus", "event_focus"),
        ):
            text = (getattr(args, attr, None) or "").strip()
            if text:
                details[key] = text

    job["topic"] = value
    job["topic_source"] = args.source
    for key in ("hook", "tension", "reader_stakes", "event_focus"):
        if details.get(key):
            job[key] = details[key]
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
    # 所有选题都进账号历史，供事件去重与结构轮换
    event_focus = details.get("event_focus") or value
    if args.source != "auto-hotspot" and not details.get("event_focus"):
        job["event_focus"] = event_focus
        save_job(args.job, job)
    record_topic_history(
        job,
        value,
        event_focus,
        selected_at=finished,
        story={
            "hook": details.get("hook"),
            "tension": details.get("tension"),
            "reader_stakes": details.get("reader_stakes"),
        },
    )
    print(json.dumps(
        {
            "topic": value,
            "source": args.source,
            "event_focus": event_focus,
            "state": job["state"],
            "next_command": suggest_next_command(job, args.job),
        },
        ensure_ascii=False, indent=2,
    ))


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
    payload = {"entries": entries}
    if getattr(args, "rotation", False):
        # 轮换窗口与 cmd_shape 一致：排除本 run 已写入但尚未带 shape 的占位条目，
        # 否则 preview 推荐的 opening/ending 会在 shape 校验时被拒（窗口错位）。
        rotation_entries = [
            entry for entry in entries
            if not (job.get("run_id") and entry.get("run_id") == job.get("run_id"))
        ]
        payload["rotation"] = compute_rotation_plan(rotation_entries)
    payload["next_command"] = suggest_next_command(job, args.job)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_shape(args):
    """锁定本轮文章结构形状，并写入 job + topic-history（防同质轮换）。

    --auto：按轮换计划自动生成合法 shape，显式字段可局部覆盖；
    弱模型/自动化路径推荐 --auto，免去阅读轮换 JSON 手工选型。
    """
    job = load_job(args.job)
    if not job.get("topic"):
        raise JobError("请先完成选题再锁定文章结构 shape")
    history = load_topic_history(job)
    # 校验时排除本 run 已写入但尚未带 shape 的占位，以及本 run 旧 shape
    entries = [
        entry for entry in recent_topic_entries(history)
        if not (job.get("run_id") and entry.get("run_id") == job.get("run_id"))
    ]
    if getattr(args, "auto", False):
        overrides = {
            "structure_id": (args.structure_id or "").strip(),
            "opening_type": (args.opening_type or "").strip(),
            "ending_type": (args.ending_type or "").strip(),
            "felt_sense": (getattr(args, "felt_sense", None) or "").strip(),
            "tension_type": (getattr(args, "tension_type", None) or "").strip(),
            "body_band": (getattr(args, "body_band", None) or "").strip(),
        }
        if getattr(args, "heading_count", None) is not None:
            overrides["heading_count"] = int(args.heading_count)
        shape = auto_shape_from_history(entries, job.get("run_id"), overrides)
    else:
        shape = parse_shape_from_args(args)
    enforce = not getattr(args, "force", False)
    validate_shape_against_history(entries, shape, enforce=enforce)
    job["article_shape"] = shape
    save_job(args.job, job)
    merge_shape_into_history(job, shape)
    # 打印用的是 shape 的浅拷贝：next_command 只进 stdout，不得混进持久化的
    # job.article_shape / topic-history 条目。
    output = dict(shape)
    output["next_command"] = suggest_next_command(job, args.job)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def registered_themes():
    """已注册主题的**单一真相源**：render_article.py 的 THEMES。

    历史实现靠扫描 `references/theme-*.md` 的文件名来发现主题，于是主题在
    Markdown 组件库和渲染脚本里各存一份，两边会漂（曾出现脚本里有 6 套、
    索引里只登记 4 套）。组件库已归档到 archive/themes-v2/，现在只认脚本。
    """
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    try:
        from render_article import THEMES
    except ImportError as exc:  # pragma: no cover - 安装损坏才会发生
        raise JobError(f"无法从 render_article.py 读取主题表：{exc}") from exc
    return list(THEMES)


def cmd_choose_theme(args):
    job = load_job(args.job)
    current = job["stages"]["format"].get("details", {}).get("theme")
    if current:
        print(current)
        return
    registered = registered_themes()
    if not registered:
        raise JobError("render_article.py 的 THEMES 为空，没有可用主题")
    requested = list(dict.fromkeys(item.strip() for item in args.theme if item.strip()))
    unknown = sorted(set(requested) - set(registered))
    if unknown:
        raise JobError(
            f"主题未注册：{', '.join(unknown)}；可用：{', '.join(registered)}"
        )
    themes = requested or registered
    # 由 run_id 派生，而非 secrets.choice：跨文章仍然轮换（run_id 每次都不同），
    # 但同一个 run 重跑必然选到同一套主题，恢复场景下不会换皮。
    digest = hashlib.sha256(str(job.get("run_id", "")).encode("utf-8")).digest()
    selected = themes[int.from_bytes(digest[:8], "big") % len(themes)]
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
    print(json.dumps(
        {
            "stage": args.name, "status": args.status, "state": job["state"],
            "next_command": suggest_next_command(job, args.job),
        },
        ensure_ascii=False,
    ))


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
    job = load_job(args.job)
    # 只加进这次打印的副本；cmd_show 从不写回 job.json，next_command 不会被持久化。
    output = dict(job)
    output["next_command"] = suggest_next_command(job, args.job)
    print(json.dumps(output, ensure_ascii=False, indent=2))


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
    topic.add_argument("--hook", help="点击钩子：读者为什么要点开")
    topic.add_argument("--tension", help="核心矛盾/故事核")
    topic.add_argument(
        "--reader-stakes",
        dest="reader_stakes",
        help="目标读者的切身代价、压力或误判风险",
    )

    history = sub.add_parser("history", help="输出近期选题重点供 Agent 做语义去重")
    history.add_argument("--job", required=True)
    history.add_argument("--days", type=int, default=7)
    history.add_argument(
        "--rotation",
        action="store_true",
        help="同时输出结构轮换计划（blocked/preferred structure/opening/ending）",
    )

    shape = sub.add_parser(
        "shape",
        help="锁定本轮文章结构形状并写入历史（structure/opening/ending 轮换）",
    )
    shape.add_argument("--job", required=True)
    shape.add_argument(
        "--auto",
        action="store_true",
        help="按轮换计划自动生成合法 shape（推荐；显式字段可局部覆盖）",
    )
    shape.add_argument("--structure-id", dest="structure_id")
    shape.add_argument("--opening-type", dest="opening_type")
    shape.add_argument("--ending-type", dest="ending_type")
    shape.add_argument("--felt-sense", dest="felt_sense")
    shape.add_argument("--tension-type", dest="tension_type")
    shape.add_argument("--heading-count", type=int, dest="heading_count")
    shape.add_argument("--body-band", dest="body_band", choices=BODY_BANDS)
    shape.add_argument(
        "--force",
        action="store_true",
        help="跳过轮换硬校验（仅人工排障时使用）",
    )

    choose = sub.add_parser(
        "choose-theme", help="从 render_article.py 的 THEMES 中按 run_id 派生并固定本轮主题"
    )
    choose.add_argument("--job", required=True)
    choose.add_argument("--theme", action="append", default=[])
    choose.add_argument(
        "--theme-index",
        help="已废弃：主题现由 render_article.py 的 THEMES 决定，此参数被忽略",
    )

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
            "shape": cmd_shape,
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
