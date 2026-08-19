#!/usr/bin/env python3
"""Persistent switch, reservation, and deduplication state for the archive series."""

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


class ArchiveStateError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat()


def project_root_from_script():
    return Path(__file__).resolve().parents[4]


def series_preset(config):
    preset = str((config or {}).get("preset") or "public-event").strip()
    if preset not in {"public-event", "tech-ai"}:
        raise ArchiveStateError("preset 只能是 public-event 或 tech-ai")
    return preset


def resolve_config_path(root):
    local = root / "config/local/public-event-archive.json"
    if local.is_file():
        return local
    return root / "config/public-event-archive.json"


def load_config(project_root):
    root = Path(project_root).expanduser().resolve()
    path = resolve_config_path(root)
    if not path.is_file():
        raise ArchiveStateError(f"缺少配置文件: {path}")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveStateError(f"配置文件不可读: {exc}") from exc
    validate_config(config)
    state_path = (root / config["state"]["path"]).resolve()
    if root not in state_path.parents:
        raise ArchiveStateError("state.path 必须位于项目目录内")
    return root, config, state_path


def validate_config(config):
    if config.get("version") != 1:
        raise ArchiveStateError("配置 version 必须为 1")
    if not isinstance(config.get("enabled"), bool):
        raise ArchiveStateError("enabled 必须为布尔值")
    if not str(config.get("account", "")).strip():
        raise ArchiveStateError("account 不能为空")
    if config.get("output_target") != "draft":
        raise ArchiveStateError("output_target 只允许 draft")
    state = config.get("state") or {}
    if not str(state.get("path", "")).strip():
        raise ArchiveStateError("state.path 不能为空")
    ttl = state.get("reservation_ttl_hours")
    if not isinstance(ttl, int) or not 1 <= ttl <= 168:
        raise ArchiveStateError("reservation_ttl_hours 必须在 1—168 之间")
    selection = config.get("selection") or {}
    min_sources = selection.get("min_source_count")
    if not isinstance(min_sources, int) or min_sources < 2:
        raise ArchiveStateError("min_source_count 不能小于 2")
    categories = selection.get("categories")
    if not isinstance(categories, list) or not categories or not all(
        isinstance(item, str) and item.strip() for item in categories
    ):
        raise ArchiveStateError("selection.categories 必须是非空字符串列表")
    preset = series_preset(config)
    if preset == "tech-ai":
        return
    for field in (
        "require_authority_source",
        "require_official_media_report",
        "person_crime_requires_effective_judgment",
        "event_requires_official_conclusion",
    ):
        if selection.get(field) is not True:
            raise ArchiveStateError(f"selection.{field} 必须保持 true")
    weights = selection.get("score_weights") or {}
    if not weights or not all(isinstance(value, int) for value in weights.values()):
        raise ArchiveStateError("score_weights 必须全部为整数")
    if sum(weights.values()) != 100:
        raise ArchiveStateError("score_weights 的整数权重之和必须为 100")
    themes = config.get("theme_allowlist")
    if not isinstance(themes, list) or not themes:
        raise ArchiveStateError("theme_allowlist 不能为空")
    if not set(themes).issubset({"solemn-gray", "news-wire", "formal-brief"}):
        raise ArchiveStateError("公共事件档案只能使用三套严肃主题")
    source_policy = config.get("source_policy") or {}
    for field in ("authority_domains", "official_media_domains"):
        domains = source_policy.get(field)
        if not isinstance(domains, list) or not domains or not all(
            isinstance(item, str) and item.strip() for item in domains
        ):
            raise ArchiveStateError(f"source_policy.{field} 必须是非空字符串列表")


def connect(state_path):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(state_path), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            case_key TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            category TEXT NOT NULL,
            state TEXT NOT NULL,
            reservation_id TEXT,
            reserved_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            run_id TEXT,
            draft_id TEXT,
            source_urls TEXT NOT NULL,
            reason TEXT
        )
        """
    )
    return db


def require_public_event_curator(config):
    if series_preset(config) != "public-event":
        raise ArchiveStateError("当前配置是科技AI系列，公共事件档案策展未启用")


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def state_counts(db):
    return {
        row["state"]: row["count"]
        for row in db.execute(
            "SELECT state, COUNT(*) AS count FROM records GROUP BY state ORDER BY state"
        )
    }


def cmd_check(args):
    root, config, state_path = load_config(args.project_root)
    preset = series_preset(config)
    curator = "public-event" if preset == "public-event" else "none"
    allowed = bool(config["enabled"] and curator == "public-event")
    if not config["enabled"]:
        reason = "disabled_by_config"
    elif curator != "public-event":
        reason = "tech_ai_series_skips_public_event_curator"
    else:
        reason = "enabled"
    with connect(state_path) as db:
        counts = state_counts(db)
    emit({
        "allowed": allowed,
        "preset": preset,
        "curator": curator,
        "config_path": str(resolve_config_path(root)),
        "reason": reason,
        "project_root": str(root),
        "account": config["account"],
        "output_target": config["output_target"],
        "state_path": str(state_path),
        "theme_allowlist": config.get("theme_allowlist") or [],
        "min_source_count": config["selection"]["min_source_count"],
        "categories": config["selection"]["categories"],
        "counts": counts,
    })


def validate_source_urls(urls, minimum):
    unique = list(dict.fromkeys(url.strip() for url in urls if url.strip()))
    if len(unique) < minimum:
        raise ArchiveStateError(f"至少需要 {minimum} 条不同的官方来源 URL")
    for url in unique:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ArchiveStateError(f"来源 URL 无效: {url}")
    return unique


def host_matches(host, domains):
    normalized = host.lower().split(":", 1)[0].strip(".")
    return any(
        normalized == domain.lower().strip(".")
        or normalized.endswith("." + domain.lower().strip("."))
        for domain in domains
    )


def validate_source_policy(urls, config):
    hosts = [urlparse(url).netloc for url in urls]
    policy = config["source_policy"]
    selection = config["selection"]
    authority_count = sum(
        host_matches(host, policy["authority_domains"]) for host in hosts
    )
    media_count = sum(
        host_matches(host, policy["official_media_domains"]) for host in hosts
    )
    if selection.get("require_authority_source", True) and not authority_count:
        raise ArchiveStateError("来源中必须至少有一条权威机关材料")
    if selection.get("require_official_media_report", True) and not media_count:
        raise ArchiveStateError("来源中必须至少有一条中国官方媒体报道")
    return {"authority": authority_count, "official_media": media_count}


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def cmd_reserve(args):
    _, config, state_path = load_config(args.project_root)
    require_public_event_curator(config)
    if not config["enabled"]:
        emit({"reserved": False, "reason": "disabled_by_config", "case_key": args.key})
        return
    if args.category not in config["selection"]["categories"]:
        raise ArchiveStateError(f"类别不在允许列表中: {args.category}")
    key = args.key.strip()
    subject = args.subject.strip()
    if not key or len(key) > 240:
        raise ArchiveStateError("case_key 不能为空且不能超过 240 字符")
    if not subject:
        raise ArchiveStateError("subject 不能为空")
    urls = validate_source_urls(args.source_url, config["selection"]["min_source_count"])
    source_counts = validate_source_policy(urls, config)
    reservation_id = uuid.uuid4().hex
    now = utc_now()
    stale_before = now - timedelta(hours=config["state"]["reservation_ttl_hours"])
    with connect(state_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM records WHERE case_key = ?", (key,)).fetchone()
        if row:
            if row["state"] == "completed":
                db.rollback()
                emit({"reserved": False, "reason": "already_completed", "case_key": key})
                return
            if row["state"] == "rejected":
                db.rollback()
                emit({"reserved": False, "reason": "previously_rejected", "case_key": key})
                return
            if row["state"] == "uncertain":
                db.rollback()
                emit({"reserved": False, "reason": "draft_outcome_uncertain", "case_key": key})
                return
            if row["state"] == "reserved" and parse_time(row["reserved_at"]) >= stale_before:
                db.rollback()
                emit({"reserved": False, "reason": "already_reserved", "case_key": key})
                return
        timestamp = now.isoformat()
        db.execute(
            """
            INSERT INTO records (
                case_key, subject, category, state, reservation_id, reserved_at,
                completed_at, updated_at, run_id, draft_id, source_urls, reason
            ) VALUES (?, ?, ?, 'reserved', ?, ?, NULL, ?, NULL, NULL, ?, NULL)
            ON CONFLICT(case_key) DO UPDATE SET
                subject=excluded.subject,
                category=excluded.category,
                state='reserved',
                reservation_id=excluded.reservation_id,
                reserved_at=excluded.reserved_at,
                completed_at=NULL,
                updated_at=excluded.updated_at,
                run_id=NULL,
                draft_id=NULL,
                source_urls=excluded.source_urls,
                reason=NULL
            """,
            (key, subject, args.category, reservation_id, timestamp, timestamp,
             json.dumps(urls, ensure_ascii=False)),
        )
        db.commit()
    emit({
        "reserved": True,
        "case_key": key,
        "reservation_id": reservation_id,
        "state": "reserved",
        "source_count": len(urls),
        "source_types": source_counts,
    })


def require_reservation(db, key, reservation_id, allowed_states=("reserved",)):
    row = db.execute("SELECT * FROM records WHERE case_key = ?", (key,)).fetchone()
    if not row:
        raise ArchiveStateError("找不到该 case_key")
    if row["state"] not in allowed_states:
        raise ArchiveStateError(
            f"当前状态不在允许列表 {','.join(allowed_states)}: {row['state']}"
        )
    if row["reservation_id"] != reservation_id:
        raise ArchiveStateError("reservation_id 不匹配")
    return row


def cmd_complete(args):
    _, config, state_path = load_config(args.project_root)
    require_public_event_curator(config)
    if not args.run_id.strip():
        raise ArchiveStateError("run_id 不能为空")
    with connect(state_path) as db:
        db.execute("BEGIN IMMEDIATE")
        require_reservation(db, args.key, args.reservation_id, ("reserved", "uncertain"))
        timestamp = iso_now()
        db.execute(
            """
            UPDATE records SET state='completed', completed_at=?, updated_at=?,
                run_id=?, draft_id=?, reason=NULL WHERE case_key=?
            """,
            (timestamp, timestamp, args.run_id.strip(), (args.draft_id or "").strip(), args.key),
        )
        db.commit()
    emit({"completed": True, "case_key": args.key, "state": "completed"})


def transition_from_reservation(args, new_state, allowed_states=("reserved",), clear_id=True):
    _, config, state_path = load_config(args.project_root)
    require_public_event_curator(config)
    reason = args.reason.strip()
    if not reason:
        raise ArchiveStateError("reason 不能为空")
    with connect(state_path) as db:
        db.execute("BEGIN IMMEDIATE")
        require_reservation(db, args.key, args.reservation_id, allowed_states)
        db.execute(
            """
            UPDATE records SET state=?, updated_at=?, reason=?,
                reservation_id=CASE WHEN ? THEN NULL ELSE reservation_id END
            WHERE case_key=?
            """,
            (new_state, iso_now(), reason, int(clear_id), args.key),
        )
        db.commit()
    emit({"updated": True, "case_key": args.key, "state": new_state, "reason": reason})


def cmd_release(args):
    transition_from_reservation(args, "released", ("reserved", "uncertain"))


def cmd_reject(args):
    transition_from_reservation(args, "rejected")


def cmd_uncertain(args):
    transition_from_reservation(args, "uncertain", ("reserved",), clear_id=False)


def cmd_list(args):
    _, _, state_path = load_config(args.project_root)
    with connect(state_path) as db:
        rows = db.execute(
            """
            SELECT case_key, subject, category, state, reserved_at, completed_at,
                   updated_at, run_id, reason
            FROM records ORDER BY updated_at DESC LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
    emit({"records": [dict(row) for row in rows], "count": len(rows)})


def require_text(mapping, field, context="dossier"):
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ArchiveStateError(f"{context}.{field} 必须是非空字符串")
    return value.strip()


def cmd_validate_dossier(args):
    _, config, state_path = load_config(args.project_root)
    require_public_event_curator(config)
    path = Path(args.file).expanduser().resolve()
    if not path.is_file():
        raise ArchiveStateError(f"dossier 不存在: {path}")
    try:
        dossier = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveStateError(f"dossier 不可读: {exc}") from exc
    if not isinstance(dossier, dict) or dossier.get("schema_version") != 1:
        raise ArchiveStateError("dossier.schema_version 必须为 1")
    case_key = require_text(dossier, "case_key")
    require_text(dossier, "subject")
    category = require_text(dossier, "category")
    if category not in config["selection"]["categories"]:
        raise ArchiveStateError(f"dossier.category 不在允许列表中: {category}")
    conclusion = dossier.get("conclusion")
    if not isinstance(conclusion, dict):
        raise ArchiveStateError("dossier.conclusion 必须是对象")
    conclusion_type = require_text(conclusion, "type", "dossier.conclusion")
    conclusion_status = require_text(conclusion, "status", "dossier.conclusion")
    require_text(conclusion, "authority", "dossier.conclusion")
    conclusion_date = require_text(conclusion, "date", "dossier.conclusion")
    if parse_time(conclusion_date) == datetime.min.replace(tzinfo=timezone.utc):
        raise ArchiveStateError("dossier.conclusion.date 不是有效 ISO 日期")
    if case_key.startswith("person:"):
        if conclusion_type != "effective_judgment" or conclusion_status != "effective":
            raise ArchiveStateError("人物犯罪稿必须标记 effective_judgment/effective")
    elif case_key.startswith("event:"):
        allowed_types = {
            "official_investigation",
            "official_conclusion",
            "responsibility_determination",
        }
        if conclusion_type not in allowed_types or conclusion_status != "final":
            raise ArchiveStateError("重大事件稿必须有 final 的官方调查、结论或责任认定")
    else:
        raise ArchiveStateError("case_key 必须以 person: 或 event: 开头")

    sources = dossier.get("sources")
    if not isinstance(sources, list):
        raise ArchiveStateError("dossier.sources 必须是列表")
    source_urls = []
    source_ids = set()
    authority_sources = 0
    media_sources = 0
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise ArchiveStateError(f"sources[{index}] 必须是对象")
        source_id = require_text(source, "id", f"sources[{index}]")
        if source_id in source_ids:
            raise ArchiveStateError(f"重复 source id: {source_id}")
        source_ids.add(source_id)
        require_text(source, "publisher", f"sources[{index}]")
        url = require_text(source, "url", f"sources[{index}]")
        published_at = require_text(source, "published_at", f"sources[{index}]")
        if parse_time(published_at) == datetime.min.replace(tzinfo=timezone.utc):
            raise ArchiveStateError(f"sources[{index}].published_at 不是有效 ISO 日期")
        source_type = require_text(source, "source_type", f"sources[{index}]")
        host = urlparse(url).netloc
        if source_type == "authority":
            if not host_matches(host, config["source_policy"]["authority_domains"]):
                raise ArchiveStateError(f"authority 来源域名不在白名单: {url}")
            authority_sources += 1
        elif source_type == "official_media":
            if not host_matches(host, config["source_policy"]["official_media_domains"]):
                raise ArchiveStateError(f"official_media 来源域名不在白名单: {url}")
            media_sources += 1
        else:
            raise ArchiveStateError("source_type 只允许 authority 或 official_media")
        source_urls.append(url)
    validate_source_urls(source_urls, config["selection"]["min_source_count"])
    validate_source_policy(source_urls, config)

    claims = dossier.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ArchiveStateError("dossier.claims 必须是非空列表")
    claim_ids = set()
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            raise ArchiveStateError(f"claims[{index}] 必须是对象")
        claim_id = require_text(claim, "id", f"claims[{index}]")
        if claim_id in claim_ids:
            raise ArchiveStateError(f"重复 claim id: {claim_id}")
        claim_ids.add(claim_id)
        require_text(claim, "text", f"claims[{index}]")
        refs = claim.get("source_ids")
        if not isinstance(refs, list) or not refs:
            raise ArchiveStateError(f"claims[{index}].source_ids 不能为空")
        missing = [source_id for source_id in refs if source_id not in source_ids]
        if missing:
            raise ArchiveStateError(f"claims[{index}] 引用了不存在的来源: {missing}")

    privacy_flags = dossier.get("privacy_flags")
    if not isinstance(privacy_flags, list):
        raise ArchiveStateError("dossier.privacy_flags 必须是列表")
    if privacy_flags:
        raise ArchiveStateError("privacy_flags 非空，候选必须人工处理或淘汰")
    if not isinstance(dossier.get("open_questions"), list):
        raise ArchiveStateError("dossier.open_questions 必须是列表")
    verified_at = require_text(dossier, "verified_at")
    if parse_time(verified_at) == datetime.min.replace(tzinfo=timezone.utc):
        raise ArchiveStateError("dossier.verified_at 不是有效 ISO 时间")

    with connect(state_path) as db:
        row = require_reservation(db, case_key, args.reservation_id)
        if row["subject"] != dossier["subject"].strip() or row["category"] != category:
            raise ArchiveStateError("dossier 与已抢占选题的 subject/category 不一致")
        reserved_urls = set(json.loads(row["source_urls"]))
        if not reserved_urls.issubset(set(source_urls)):
            raise ArchiveStateError("dossier 缺少 reserve 时采用的来源 URL")
    emit({
        "valid": True,
        "case_key": case_key,
        "category": category,
        "claim_count": len(claims),
        "source_count": len(sources),
        "source_types": {
            "authority": authority_sources,
            "official_media": media_sources,
        },
    })


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="验证开关、配置和状态库")
    check.add_argument("--project-root", default=str(project_root_from_script()))
    check.set_defaults(func=cmd_check)

    reserve = sub.add_parser("reserve", help="原子抢占一个未写选题")
    reserve.add_argument("--project-root", default=str(project_root_from_script()))
    reserve.add_argument("--key", required=True)
    reserve.add_argument("--subject", required=True)
    reserve.add_argument("--category", required=True)
    reserve.add_argument("--source-url", action="append", default=[], required=True)
    reserve.set_defaults(func=cmd_reserve)

    complete = sub.add_parser("complete", help="草稿成功后完成记录")
    complete.add_argument("--project-root", default=str(project_root_from_script()))
    complete.add_argument("--key", required=True)
    complete.add_argument("--reservation-id", required=True)
    complete.add_argument("--run-id", required=True)
    complete.add_argument("--draft-id")
    complete.set_defaults(func=cmd_complete)

    for name, func, help_text in (
        ("release", cmd_release, "明确未创建草稿时释放抢占"),
        ("reject", cmd_reject, "候选不合格时永久拒绝"),
        ("uncertain", cmd_uncertain, "draft/add 结果不确定时冻结抢占"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--project-root", default=str(project_root_from_script()))
        command.add_argument("--key", required=True)
        command.add_argument("--reservation-id", required=True)
        command.add_argument("--reason", required=True)
        command.set_defaults(func=func)

    listing = sub.add_parser("list", help="列出最近状态用于去重")
    listing.add_argument("--project-root", default=str(project_root_from_script()))
    listing.add_argument("--limit", type=int, default=100, choices=range(1, 501))
    listing.set_defaults(func=cmd_list)

    dossier = sub.add_parser("validate-dossier", help="校验事实卡、结论状态和来源映射")
    dossier.add_argument("--project-root", default=str(project_root_from_script()))
    dossier.add_argument("--file", required=True)
    dossier.add_argument("--reservation-id", required=True)
    dossier.set_defaults(func=cmd_validate_dossier)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ArchiveStateError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
