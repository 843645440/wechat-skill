#!/usr/bin/env python3
"""Validate native WeChat inline-visual plans against their source article."""

import argparse
import json
import os
import re
import sys
from pathlib import Path


THEME_RE = re.compile(r"references/theme-([a-z0-9][a-z0-9-]*)\.md")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
ID_RE = re.compile(r"^inline-[0-9]{2}$")
KINDS = {"insight", "comparison", "process", "metrics"}
INLINE_RE = re.compile(
    r"(`[^`\n]+`|\*\*\S(?:.*?\S)?\*\*|__\S(?:.*?\S)?__|"
    r"==\S(?:.*?\S)?==|\+\+\S(?:.*?\S)?\+\+|<u>.+?</u>)"
)


class PlanError(RuntimeError):
    pass


def normalized(value):
    return " ".join(value.split())


def plain_text(value):
    """仅移除成对的行内 Markdown 标记，保留字面运算符和标点。"""
    value = str(value)
    return normalized(INLINE_RE.sub(lambda match: re.sub(
        r"^(?:\*\*|__|==|\+\+|`|<u>)|(?:\*\*|__|==|\+\+|`|</u>)$",
        "",
        match.group(0),
        flags=re.I,
    ), value))


def text(value, field, maximum):
    if not isinstance(value, str) or not normalized(value):
        raise PlanError(f"{field} 必须是非空字符串")
    value = normalized(value)
    if len(value) > maximum:
        raise PlanError(f"{field} 超过 {maximum} 字")
    return value


def strict_keys(value, allowed, field):
    if not isinstance(value, dict):
        raise PlanError(f"{field} 必须是对象")
    unknown = sorted(set(value) - set(allowed))
    missing = sorted(set(allowed) - set(value))
    if unknown:
        raise PlanError(f"{field} 包含未知字段：{', '.join(unknown)}")
    if missing:
        raise PlanError(f"{field} 缺少字段：{', '.join(missing)}")


def object_items(value, field, minimum, maximum, item_fields):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise PlanError(f"{field} 必须包含 {minimum}—{maximum} 项")
    output = []
    for index, item in enumerate(value, 1):
        name = f"{field}[{index}]"
        strict_keys(item, item_fields, name)
        output.append(item)
    return output


def string_items(value, field, minimum=2, maximum=4):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise PlanError(f"{field} 必须包含 {minimum}—{maximum} 项")
    return [text(item, f"{field}[{index}]", 28) for index, item in enumerate(value, 1)]


def clamp_text(value, maximum):
    value = normalized(str(value))
    if not value:
        return value
    return value if len(value) <= maximum else value[:maximum]


def first_present(mapping, *keys):
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def coerce_label_text_list(items, label_max, text_max, label_aliases):
    if not isinstance(items, list):
        return items
    output = []
    for item in items:
        if isinstance(item, str):
            text_value = clamp_text(item, text_max)
            label_value = clamp_text(item, label_max)
            if text_value and label_value:
                output.append({"label": label_value, "text": text_value})
            continue
        if not isinstance(item, dict):
            continue
        label = first_present(item, "label", *label_aliases)
        body = first_present(item, "text", "desc", "description", "content", "detail")
        if label is None and body is None:
            continue
        if label is None:
            label = clamp_text(body, label_max)
        if body is None:
            body = clamp_text(label, text_max)
        output.append({
            "label": clamp_text(label, label_max),
            "text": clamp_text(body, text_max),
        })
    return output


def coerce_module(module, index):
    """Normalize one module: aliases, ids, length clamps; rewrite to canonical keys."""
    if not isinstance(module, dict):
        return module
    out = dict(module)

    kind = out.get("kind") or out.get("type") or out.get("module_type")
    if isinstance(kind, str):
        kind = kind.strip().lower().replace("_", "-")
        aliases = {
            "insights": "insight",
            "point": "insight",
            "points": "insight",
            "compare": "comparison",
            "contrast": "comparison",
            "flow": "process",
            "steps": "process",
            "pipeline": "process",
            "metric": "metrics",
            "stats": "metrics",
            "numbers": "metrics",
        }
        kind = aliases.get(kind, kind)
    out["kind"] = kind

    module_id = out.get("id")
    if not isinstance(module_id, str) or not ID_RE.fullmatch(module_id.strip()):
        out["id"] = f"inline-{index:02d}"
    else:
        out["id"] = module_id.strip()

    title = first_present(out, "title", "name", "heading", "module_title")
    if title is not None:
        out["title"] = clamp_text(title, 24)

    placement = out.get("placement") or out.get("position") or out.get("anchor")
    if isinstance(placement, dict):
        place = {}
        heading = first_present(
            placement, "after_heading", "afterHeading", "heading", "section", "chapter"
        )
        after = first_present(
            placement, "after_text", "afterText", "text", "anchor", "anchor_text", "quote"
        )
        if heading is not None:
            place["after_heading"] = clamp_text(heading, 40)
        if after is not None:
            place["after_text"] = clamp_text(after, 120)
        out["placement"] = place

    evidence = out.get("evidence") or out.get("proofs") or out.get("quotes")
    if isinstance(evidence, str):
        evidence = [evidence]
    if isinstance(evidence, list):
        cleaned = []
        for item in evidence[:4]:
            if isinstance(item, str) and normalized(item):
                cleaned.append(clamp_text(item, 160))
        out["evidence"] = cleaned

    if kind == "insight":
        items = out.get("items") or out.get("points") or out.get("bullets")
        out["items"] = coerce_label_text_list(
            items, 10, 42, ("name", "title", "heading", "role", "who")
        )
    elif kind == "process":
        steps = out.get("steps") or out.get("flow") or out.get("process")
        out["steps"] = coerce_label_text_list(
            steps, 10, 28, ("name", "title", "heading", "step", "stage")
        )
    elif kind == "comparison":
        for side_key, aliases in (
            ("left", ("left", "before", "a", "from")),
            ("right", ("right", "after", "b", "to")),
        ):
            side = out.get(side_key)
            if side is None:
                for alt in aliases[1:]:
                    if alt in out:
                        side = out.get(alt)
                        break
            if not isinstance(side, dict):
                continue
            heading = first_present(side, "heading", "title", "name", "label")
            items = side.get("items") or side.get("points") or side.get("bullets")
            if isinstance(items, list):
                items = [
                    clamp_text(x, 28) if isinstance(x, str) else x
                    for x in items
                ]
            rebuilt = {}
            if heading is not None:
                rebuilt["heading"] = clamp_text(heading, 12)
            if items is not None:
                rebuilt["items"] = items
            out[side_key] = rebuilt
    elif kind == "metrics":
        metrics = out.get("metrics") or out.get("stats") or out.get("numbers")
        if isinstance(metrics, list):
            cleaned = []
            for item in metrics:
                if not isinstance(item, dict):
                    continue
                value = first_present(item, "value", "number", "num", "metric")
                label = first_present(item, "label", "name", "title", "heading")
                note = first_present(item, "note", "desc", "description", "text", "detail")
                row = {}
                if value is not None:
                    row["value"] = clamp_text(value, 12)
                if label is not None:
                    row["label"] = clamp_text(label, 12)
                if note is not None:
                    row["note"] = clamp_text(note, 28)
                cleaned.append(row)
            out["metrics"] = cleaned

    common = {"id", "kind", "title", "placement", "evidence"}
    kind_fields = {
        "insight": ("items",),
        "comparison": ("left", "right"),
        "process": ("steps",),
        "metrics": ("metrics",),
    }
    if kind not in kind_fields:
        return out
    canonical = {key: out[key] for key in common if key in out}
    for key in kind_fields[kind]:
        if key in out:
            canonical[key] = out[key]
    return canonical


def coerce_plan(raw, fallback_theme=None):
    """Normalize shell + common agent field aliases; keep modules whenever possible."""
    if not isinstance(raw, dict):
        return raw
    out = dict(raw)
    version = out.get("version", 1)
    if version in (None, "", "1", 1, 1.0):
        out["version"] = 1
    if not out.get("theme") and fallback_theme:
        out["theme"] = fallback_theme
    modules = out.get("modules")
    if modules is None:
        modules = out.get("blocks") or out.get("visuals") or []
    if not isinstance(modules, list):
        modules = []
    coerced_modules = []
    for index, module in enumerate(modules[:3], 1):
        coerced_modules.append(coerce_module(module, index))
    return {
        "version": out.get("version", 1),
        "theme": out.get("theme"),
        "modules": coerced_modules,
    }


def salvage_plan(raw, article, registered_themes, fallback_theme=None):
    """Keep individually valid modules when the full plan fails.

    Returns (plan_dict, dropped_reasons).
    """
    theme = None
    if isinstance(raw, dict):
        theme = raw.get("theme")
    if not theme or theme not in registered_themes:
        theme = fallback_theme
    if not theme or theme not in registered_themes:
        raise PlanError("salvage 需要已注册 theme")

    modules = raw.get("modules") if isinstance(raw, dict) else []
    if not isinstance(modules, list):
        modules = []

    kept = []
    dropped = []
    for index, module in enumerate(modules, 1):
        one = coerce_module(module, len(kept) + 1)
        if isinstance(one, dict):
            one["id"] = f"inline-{len(kept) + 1:02d}"
        trial = {"version": 1, "theme": theme, "modules": kept + [one]}
        try:
            validate_plan(trial, article, registered_themes)
            kept = trial["modules"]
        except PlanError as exc:
            dropped.append(f"modules[{index}]: {exc}")

    return {"version": 1, "theme": theme, "modules": kept}, dropped


def validate_plan(raw, article, registered_themes):
    strict_keys(raw, {"version", "theme", "modules"}, "plan")
    if raw["version"] != 1:
        raise PlanError("version 必须为 1")
    theme = text(raw["theme"], "theme", 64)
    if theme not in registered_themes:
        raise PlanError(f"主题未注册：{theme}")
    modules = raw["modules"]
    if not isinstance(modules, list) or len(modules) > 3:
        raise PlanError("modules 必须包含 0—3 项")

    article_plain = plain_text(article)
    headings = {plain_text(item) for item in HEADING_RE.findall(article)}
    seen_ids = set()
    seen_kinds = set()
    seen_placements = set()

    common = {"id", "kind", "title", "placement", "evidence"}
    kind_fields = {
        "insight": {"items"},
        "comparison": {"left", "right"},
        "process": {"steps"},
        "metrics": {"metrics"},
    }

    for index, module in enumerate(modules, 1):
        field = f"modules[{index}]"
        if not isinstance(module, dict):
            raise PlanError(f"{field} 必须是对象")
        kind = module.get("kind")
        if kind not in KINDS:
            raise PlanError(f"{field}.kind 必须是：{', '.join(sorted(KINDS))}")
        strict_keys(module, common | kind_fields[kind], field)

        module_id = text(module["id"], f"{field}.id", 9)
        if not ID_RE.fullmatch(module_id) or module_id in seen_ids:
            raise PlanError(f"{field}.id 必须是唯一的 inline-NN")
        seen_ids.add(module_id)
        if kind in seen_kinds:
            raise PlanError(f"同篇文章不得重复模块类型：{kind}")
        seen_kinds.add(kind)
        text(module["title"], f"{field}.title", 24)

        placement = module["placement"]
        strict_keys(placement, {"after_heading", "after_text"}, f"{field}.placement")
        after_heading = text(placement["after_heading"], f"{field}.placement.after_heading", 40)
        after_text = text(placement["after_text"], f"{field}.placement.after_text", 120)
        if after_heading not in headings:
            raise PlanError(f"插入章节不存在：{after_heading}")
        if after_text not in article_plain:
            raise PlanError(f"插入锚点不是文章原文：{after_text}")
        placement_key = (after_heading, after_text)
        if placement_key in seen_placements:
            raise PlanError("两个模块不得使用同一插入位置")
        seen_placements.add(placement_key)

        evidence = module["evidence"]
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 4:
            raise PlanError(f"{field}.evidence 必须包含 1—4 项")
        for evidence_index, item in enumerate(evidence, 1):
            excerpt = text(item, f"{field}.evidence[{evidence_index}]", 160)
            if excerpt not in article_plain:
                raise PlanError(f"证据不是文章原文：{excerpt}")

        if kind == "insight":
            items = object_items(module["items"], f"{field}.items", 2, 4, {"label", "text"})
            for item_index, item in enumerate(items, 1):
                text(item["label"], f"{field}.items[{item_index}].label", 10)
                text(item["text"], f"{field}.items[{item_index}].text", 42)
        elif kind == "comparison":
            for side in ("left", "right"):
                value = module[side]
                strict_keys(value, {"heading", "items"}, f"{field}.{side}")
                text(value["heading"], f"{field}.{side}.heading", 12)
                string_items(value["items"], f"{field}.{side}.items")
        elif kind == "process":
            steps = object_items(module["steps"], f"{field}.steps", 3, 5, {"label", "text"})
            for step_index, item in enumerate(steps, 1):
                text(item["label"], f"{field}.steps[{step_index}].label", 10)
                text(item["text"], f"{field}.steps[{step_index}].text", 28)
        else:
            metrics = object_items(module["metrics"], f"{field}.metrics", 2, 4, {"value", "label", "note"})
            for metric_index, item in enumerate(metrics, 1):
                value = text(item["value"], f"{field}.metrics[{metric_index}].value", 12)
                if value not in article_plain:
                    raise PlanError(f"指标值不是文章原文：{value}")
                text(item["label"], f"{field}.metrics[{metric_index}].label", 12)
                text(item["note"], f"{field}.metrics[{metric_index}].note", 28)

    return {"theme": theme, "module_count": len(modules), "kinds": [item["kind"] for item in modules]}


def parse_args():
    parser = argparse.ArgumentParser(description="校验公众号原生信息模块计划")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--article", required=True)
    parser.add_argument("--theme-index", required=True)
    parser.add_argument("--degrade-on-error", action="store_true")
    parser.add_argument("--fallback-theme")
    return parser.parse_args()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main():
    args = parse_args()
    try:
        article = Path(args.article).read_text(encoding="utf-8")
        theme_index = Path(args.theme_index).read_text(encoding="utf-8")
        registered = set(THEME_RE.findall(theme_index))
    except OSError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    try:
        loaded = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if args.degrade_on_error:
            if not args.fallback_theme or args.fallback_theme not in registered:
                print(
                    json.dumps(
                        {"status": "error", "error": "降级需要已注册的 --fallback-theme"},
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                return 1
            empty = {"version": 1, "theme": args.fallback_theme, "modules": []}
            try:
                atomic_json(Path(args.plan), empty)
            except OSError as write_exc:
                print(json.dumps({"status": "error", "error": str(write_exc)}, ensure_ascii=False), file=sys.stderr)
                return 1
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "theme": args.fallback_theme,
                        "module_count": 0,
                        "kinds": [],
                        "degraded": True,
                        "degrade_reason": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    raw = coerce_plan(loaded, args.fallback_theme)
    try:
        result = validate_plan(raw, article, registered)
        try:
            atomic_json(Path(args.plan), {
                "version": raw["version"],
                "theme": raw["theme"],
                "modules": raw["modules"],
            })
        except OSError:
            pass
        print(json.dumps({"status": "ok", **result, "degraded": False}, ensure_ascii=False))
        return 0
    except PlanError as full_exc:
        if not args.degrade_on_error:
            print(json.dumps({"status": "error", "error": str(full_exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        if not args.fallback_theme or args.fallback_theme not in registered:
            print(
                json.dumps(
                    {"status": "error", "error": "降级需要已注册的 --fallback-theme"},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1

        # Prefer keeping any salvageable modules over wiping the whole plan.
        try:
            salvaged, dropped = salvage_plan(
                raw, article, registered, fallback_theme=args.fallback_theme
            )
        except PlanError:
            salvaged, dropped = (
                {"version": 1, "theme": args.fallback_theme, "modules": []},
                [str(full_exc)],
            )

        try:
            atomic_json(Path(args.plan), salvaged)
        except OSError as write_exc:
            print(json.dumps({"status": "error", "error": str(write_exc)}, ensure_ascii=False), file=sys.stderr)
            return 1

        module_count = len(salvaged["modules"])
        kinds = [item["kind"] for item in salvaged["modules"]]
        if module_count:
            reason = (
                f"full_plan_failed: {full_exc}; kept {module_count}; dropped: "
                + ("; ".join(dropped) if dropped else "none")
            )
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "theme": salvaged["theme"],
                        "module_count": module_count,
                        "kinds": kinds,
                        "degraded": True,
                        "partial": True,
                        "degrade_reason": reason,
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        print(
            json.dumps(
                {
                    "status": "ok",
                    "theme": args.fallback_theme,
                    "module_count": 0,
                    "kinds": [],
                    "degraded": True,
                    "degrade_reason": str(full_exc),
                },
                ensure_ascii=False,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
