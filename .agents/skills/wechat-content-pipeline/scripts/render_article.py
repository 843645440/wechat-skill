#!/usr/bin/env python3
"""Deterministically render a Markdown article and native information modules."""

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path


THEMES = {
    "moyu-green": {
        "paper": "#FFFFFF", "ink": "#111827", "muted": "#4B5563",
        "accent": "#059669", "soft": "#F0FDF4", "line": "#A7F3D0",
        "radius": "14px", "shadow": "0 5px 16px rgba(5,150,105,0.10)",
    },
    "red-white": {
        "paper": "#FFFFFF", "ink": "#1C1917", "muted": "#57534E",
        "accent": "#DC2626", "soft": "#FFF7F7", "line": "#FECACA",
        "radius": "8px", "shadow": "0 4px 14px rgba(220,38,38,0.08)",
    },
    "graphite-minimal": {
        "paper": "#FFFFFF", "ink": "#27272A", "muted": "#71717A",
        "accent": "#52525B", "soft": "#FAFAFA", "line": "#D4D4D8",
        "radius": "6px", "shadow": "none",
    },
    "zen-whitespace": {
        "paper": "#FFFFFF", "ink": "#2B2B2B", "muted": "#737B76",
        "accent": "#4A5D52", "soft": "#FAFCFA", "line": "#B5C8BC",
        "radius": "4px", "shadow": "none",
    },
    "moyu-ticket": {
        "paper": "#FFFFFF", "ink": "#1A1A1A", "muted": "#555555",
        "accent": "#059669", "soft": "#FFFEF8", "line": "#A7F3D0",
        "radius": "2px", "shadow": "5px 5px 0 #1A1A1A",
    },
    "olive-journal": {
        "paper": "#FDFDF8", "ink": "#23251D", "muted": "#65675E",
        "accent": "#ED7B2F", "soft": "#EEEFE9", "line": "#D4C9B8",
        "radius": "5px", "shadow": "0 5px 18px rgba(35,37,29,0.09)",
    },
}
HEADING_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*$")
MARKUP_RE = re.compile(r"(\*\*|__|`|==)")


class RenderError(RuntimeError):
    pass


def normalized(value):
    return " ".join(value.split())


def plain_text(value):
    return MARKUP_RE.sub("", normalized(value))


def leaf(value, style=""):
    style_attr = f' style="{style}"' if style else ""
    return f'<span leaf=""{style_attr}>{html.escape(str(value), quote=True)}</span>'


def atomic_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def parse_article(source):
    title = None
    sections = [{"heading": None, "blocks": []}]
    paragraph = []
    bullets = []

    def flush_paragraph():
        if paragraph:
            sections[-1]["blocks"].append(
                {"kind": "paragraph", "text": plain_text(" ".join(paragraph))}
            )
            paragraph.clear()

    def flush_bullets():
        if bullets:
            sections[-1]["blocks"].append({"kind": "list", "items": bullets[:]})
            bullets.clear()

    for raw in source.splitlines():
        line = raw.strip()
        match = HEADING_RE.match(line)
        if match:
            flush_paragraph()
            flush_bullets()
            level, heading = len(match.group(1)), plain_text(match.group(2))
            if level == 1:
                if title is not None:
                    raise RenderError("article.md 只能包含一个一级标题")
                title = heading
            else:
                sections.append({"heading": heading, "blocks": []})
        elif not line:
            flush_paragraph()
            flush_bullets()
        elif line.startswith(("- ", "* ", "+ ")):
            flush_paragraph()
            bullets.append(plain_text(line[2:]))
        elif line.startswith("> "):
            flush_paragraph()
            flush_bullets()
            sections[-1]["blocks"].append(
                {"kind": "quote", "text": plain_text(line[2:])}
            )
        else:
            flush_bullets()
            paragraph.append(line)
    flush_paragraph()
    flush_bullets()
    sections = [item for item in sections if item["heading"] or item["blocks"]]
    if not title:
        raise RenderError("article.md 第一行必须是唯一一级标题")
    if not any(section["blocks"] for section in sections):
        raise RenderError("article.md 没有正文")
    return title, sections


def card_style(theme, extra=""):
    return (
        f"margin:22px 0;padding:18px;background:{theme['paper']};"
        f"border:1px solid {theme['line']};border-radius:{theme['radius']};"
        f"box-shadow:{theme['shadow']};{extra}"
    )


def render_module(module, theme):
    kind = module["kind"]
    title = module["title"]
    module_style = card_style(
        theme, f"border-top:4px solid {theme['accent']};"
    )
    output = [
        f'<section style="{module_style}">',
        '<p style="margin:0 0 14px;font-size:12px;line-height:1.5;letter-spacing:1px;">',
        leaf("正文信息卡", f"color:{theme['accent']};font-weight:700;"),
        '</p><p style="margin:0 0 16px;font-size:18px;line-height:1.5;">',
        leaf(title, f"color:{theme['ink']};font-weight:700;"), "</p>",
    ]
    if kind == "insight":
        for item in module["items"]:
            output.extend([
                f'<section style="margin:10px 0;padding:12px;background:{theme["soft"]};border-radius:{theme["radius"]};">',
                '<p style="margin:0 0 5px;font-size:14px;line-height:1.5;">',
                leaf(item["label"], f"color:{theme['accent']};font-weight:700;"),
                '</p><p style="margin:0;font-size:15px;line-height:1.75;">',
                leaf(item["text"], f"color:{theme['ink']};"), "</p></section>",
            ])
    elif kind == "comparison":
        output.append('<section style="display:flex;flex-wrap:wrap;margin:0 -5px;">')
        for side in (module["left"], module["right"]):
            output.extend([
                '<section style="box-sizing:border-box;min-width:220px;flex:1;margin:5px;padding:13px;'
                f'background:{theme["soft"]};border-radius:{theme["radius"]};">',
                '<p style="margin:0 0 9px;font-size:15px;line-height:1.5;">',
                leaf(side["heading"], f"color:{theme['accent']};font-weight:700;"), "</p>",
            ])
            for item in side["items"]:
                output.extend([
                    '<p style="margin:7px 0;font-size:14px;line-height:1.7;">',
                    leaf("• ", f"color:{theme['accent']};font-weight:700;"),
                    leaf(item, f"color:{theme['ink']};"), "</p>",
                ])
            output.append("</section>")
        output.append("</section>")
    elif kind == "process":
        for index, item in enumerate(module["steps"], 1):
            output.extend([
                '<section style="display:flex;align-items:flex-start;margin:11px 0;">',
                f'<p style="flex:0 0 30px;margin:0 10px 0 0;padding:4px 0;text-align:center;background:{theme["accent"]};border-radius:15px;font-size:13px;line-height:22px;">',
                leaf(index, "color:#FFFFFF;font-weight:700;"),
                '</p><section style="flex:1;min-width:0;">',
                '<p style="margin:0 0 3px;font-size:14px;line-height:1.5;">',
                leaf(item["label"], f"color:{theme['accent']};font-weight:700;"),
                '</p><p style="margin:0;font-size:15px;line-height:1.7;">',
                leaf(item["text"], f"color:{theme['ink']};"), "</p></section></section>",
            ])
    elif kind == "metrics":
        output.append('<section style="display:flex;flex-wrap:wrap;margin:0 -5px;">')
        for item in module["metrics"]:
            output.extend([
                '<section style="box-sizing:border-box;min-width:135px;flex:1;margin:5px;padding:13px;'
                f'text-align:center;background:{theme["soft"]};border-radius:{theme["radius"]};">',
                '<p style="margin:0 0 4px;font-size:24px;line-height:1.3;">',
                leaf(item["value"], f"color:{theme['accent']};font-weight:800;"),
                '</p><p style="margin:0 0 4px;font-size:14px;line-height:1.5;">',
                leaf(item["label"], f"color:{theme['ink']};font-weight:700;"),
                '</p><p style="margin:0;font-size:12px;line-height:1.6;">',
                leaf(item["note"], f"color:{theme['muted']};"), "</p></section>",
            ])
        output.append("</section>")
    else:
        raise RenderError(f"不支持的信息模块类型：{kind}")
    output.append("</section>")
    return "".join(output)


def render_block(block, theme, intro=False):
    if block["kind"] == "list":
        items = []
        for item in block["items"]:
            items.append(
                f'<li style="margin:8px 0;padding-left:3px;font-size:16px;line-height:1.85;color:{theme["ink"]};">'
                + leaf(item) + "</li>"
            )
        return f'<ul style="margin:14px 0;padding-left:22px;">{"".join(items)}</ul>'
    text = block["text"]
    if block["kind"] == "quote" or intro:
        quote_style = card_style(
            theme,
            f"background:{theme['soft']};border-left:4px solid {theme['accent']};box-shadow:none;",
        )
        return (
            f'<section style="{quote_style}">'
            f'<p style="margin:0;font-size:16px;line-height:1.9;color:{theme["ink"]};">'
            + leaf(text) + "</p></section>"
        )
    return (
        f'<p style="margin:16px 0;font-size:16px;line-height:1.9;letter-spacing:0.15px;color:{theme["ink"]};">'
        + leaf(text) + "</p>"
    )


def module_map(plan, sections):
    headings = {section["heading"] for section in sections if section["heading"]}
    anchors = {}
    for module in plan["modules"]:
        placement = module["placement"]
        heading = normalized(placement["after_heading"])
        anchor = normalized(placement["after_text"])
        if heading not in headings:
            raise RenderError(f"信息模块章节不存在：{heading}")
        match = None
        for section_index, section in enumerate(sections):
            if section["heading"] != heading:
                continue
            for block_index, block in enumerate(section["blocks"]):
                haystack = normalized(" ".join(block.get("items", [])) if block["kind"] == "list" else block["text"])
                if anchor in haystack:
                    match = (section_index, block_index)
                    break
        if match is None:
            raise RenderError(f"信息模块锚点不存在：{anchor}")
        if match in anchors:
            raise RenderError("两个信息模块不能使用同一插入位置")
        anchors[match] = module
    return anchors


def render_document(title, sections, plan, theme):
    anchors = module_map(plan, sections)
    output = [
        f'<section style="box-sizing:border-box;max-width:680px;margin:0 auto;padding:8px 17px 32px;background:{theme["paper"]};color:{theme["ink"]};font-family:-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;">'
    ]
    intro_used = False
    for section_index, section in enumerate(sections):
        if section["heading"]:
            output.extend([
                f'<section style="margin:34px 0 14px;padding:0 0 9px;border-bottom:2px solid {theme["line"]};">',
                '<p style="margin:0;font-size:21px;line-height:1.5;">',
                leaf(section["heading"], f"color:{theme['ink']};font-weight:750;"),
                "</p></section>",
            ])
        for block_index, block in enumerate(section["blocks"]):
            is_intro = not intro_used and block["kind"] == "paragraph"
            output.append(render_block(block, theme, is_intro))
            if is_intro:
                intro_used = True
            module = anchors.get((section_index, block_index))
            if module:
                output.append(render_module(module, theme))
    output.append("</section>")
    return "".join(output)


def validate_plan_shape(plan, theme):
    if not isinstance(plan, dict) or set(plan) != {"version", "theme", "modules"}:
        raise RenderError("inline-visuals.json 结构无效")
    if plan["version"] != 1 or plan["theme"] != theme or not isinstance(plan["modules"], list):
        raise RenderError("信息模块版本、主题或 modules 无效")
    if len(plan["modules"]) > 3:
        raise RenderError("信息模块不能超过 3 个")


def parse_args():
    parser = argparse.ArgumentParser(description="一次生成公众号正文排版和同主题信息模块")
    parser.add_argument("--article", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--theme", choices=tuple(THEMES), required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    started = time.monotonic()
    article_path, plan_path, output_path = map(Path, (args.article, args.plan, args.output))
    try:
        source = article_path.read_text(encoding="utf-8")
        title, sections = parse_article(source)
        degraded = False
        reason = ""
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            validate_plan_shape(plan, args.theme)
            rendered = render_document(title, sections, plan, THEMES[args.theme])
            module_count = len(plan["modules"])
            kinds = [item["kind"] for item in plan["modules"]]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, RenderError) as exc:
            degraded = True
            reason = str(exc)
            plan = {"version": 1, "theme": args.theme, "modules": []}
            atomic_json(plan_path, plan)
            rendered = render_document(title, sections, plan, THEMES[args.theme])
            module_count = 0
            kinds = []
        atomic_text(output_path, rendered + "\n")
    except (OSError, RenderError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    result = {
        "status": "ok", "title": title, "theme": args.theme,
        "module_count": module_count, "kinds": kinds, "degraded": degraded,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    if reason:
        result["degrade_reason"] = reason
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
