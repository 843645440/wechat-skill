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


class PlanError(RuntimeError):
    pass


def normalized(value):
    return " ".join(value.split())


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

    article_normalized = normalized(article)
    headings = {normalized(item) for item in HEADING_RE.findall(article)}
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
        if after_text not in article_normalized:
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
            if excerpt not in article_normalized:
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
                if value not in article_normalized:
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
        raw = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        result = validate_plan(raw, article, registered)
    except (OSError, json.JSONDecodeError, PlanError) as exc:
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
                        "status": "ok", "theme": args.fallback_theme,
                        "module_count": 0, "kinds": [], "degraded": True,
                        "degrade_reason": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", **result, "degraded": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
