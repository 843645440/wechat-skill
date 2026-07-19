#!/usr/bin/env python3
"""Deterministically render semantic Markdown with rich WeChat theme components."""

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
        "layout": "magazine", "name": "摸鱼绿", "paper": "#FFFFFF",
        "ink": "#111827", "body": "#374151", "muted": "#6B7280",
        "accent": "#059669", "soft": "#F0FDF4", "line": "#A7F3D0",
        "underline": "border-bottom:2px solid #A7F3D0;font-weight:600;",
        "radius": "14px", "shadow": "0 5px 16px rgba(5,150,105,0.10)",
    },
    "red-white": {
        "layout": "editorial", "name": "红白色系", "paper": "#FFFFFF",
        "ink": "#1C1917", "body": "#44403C", "muted": "#78716C",
        "accent": "#DC2626", "soft": "#FEF2F2", "line": "#FECACA",
        "underline": "border-bottom:2px solid #FECACA;font-weight:600;",
        "radius": "10px", "shadow": "0 4px 18px rgba(220,38,38,0.10)",
    },
    "graphite-minimal": {
        "layout": "graphite", "name": "石墨极简", "paper": "#FFFFFF",
        "ink": "#27272A", "body": "#52525B", "muted": "#A1A1AA",
        "accent": "#52525B", "soft": "#FAFAFA", "line": "#E4E4E7",
        "underline": "border-bottom:2px solid #52525B;font-weight:600;",
        "radius": "0", "shadow": "none",
    },
    "zen-whitespace": {
        "layout": "zen", "name": "留白禅意", "paper": "#FFFFFF",
        "ink": "#2B2B2B", "body": "#525252", "muted": "#A3A3A3",
        "accent": "#4A5D52", "soft": "#FAFCFA", "line": "#E8E8E8",
        "underline": "border-bottom:1.5px solid #B5C8BC;font-weight:500;",
        "radius": "0", "shadow": "none",
    },
    "moyu-ticket": {
        "layout": "ticket", "name": "摸鱼票据", "paper": "#FFFFFF",
        "ink": "#1A1A1A", "body": "#555555", "muted": "#888888",
        "accent": "#059669", "soft": "#FFFEF8", "line": "#A7F3D0",
        "underline": "border-bottom:2px solid #A7F3D0;font-weight:600;",
        "radius": "0", "shadow": "4px 4px 0 #1A1A1A",
    },
    "olive-journal": {
        "layout": "journal", "name": "橄榄手记", "paper": "#FDFDF8",
        "ink": "#23251D", "body": "#4D4F46", "muted": "#65675E",
        "accent": "#ED7B2F", "soft": "#EEEFE9", "line": "#BFC1B7",
        "underline": "border-bottom:2px solid #ED7B2F;font-weight:600;",
        "radius": "6px", "shadow": "0 5px 18px rgba(35,37,29,0.09)",
    },
}

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
INLINE_RE = re.compile(
    r"(`[^`\n]+`|\*\*.+?\*\*|==.+?==|\+\+.+?\+\+|<u>.+?</u>)"
)
TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
END_HEADING_RE = re.compile(r"结语|结论|总结|写在最后|最后的话|尾声")


class RenderError(RuntimeError):
    pass


def normalized(value):
    return " ".join(str(value).split())


def plain_text(value):
    value = re.sub(r"</?u>", "", str(value), flags=re.I)
    value = re.sub(r"(\*\*|__|`|==|\+\+)", "", value)
    return normalized(value)


def leaf(value, style=""):
    style_attr = f' style="{style}"' if style else ""
    return f'<span leaf=""{style_attr}>{html.escape(str(value), quote=True)}</span>'


def render_inline(value, theme):
    output = []
    for part in INLINE_RE.split(str(value)):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            output.append(
                f'<span style="{theme["underline"]}">{leaf(part[2:-2])}</span>'
            )
        elif part.startswith("==") and part.endswith("=="):
            output.append(
                f'<span style="background:{theme["line"]};color:{theme["ink"]};'
                f'padding:1px 3px;font-weight:600;">{leaf(part[2:-2])}</span>'
            )
        elif part.startswith("++") and part.endswith("++"):
            output.append(
                f'<span style="{theme["underline"]}">{leaf(part[2:-2])}</span>'
            )
        elif part.lower().startswith("<u>") and part.lower().endswith("</u>"):
            output.append(
                f'<span style="{theme["underline"]}">{leaf(part[3:-4])}</span>'
            )
        elif part.startswith("`") and part.endswith("`"):
            output.append(
                f'<span style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
                f'background:{theme["soft"]};color:{theme["accent"]};padding:1px 5px;'
                f'border-radius:3px;">{leaf(part[1:-1])}</span>'
            )
        else:
            output.append(leaf(part))
    return "".join(output)


def atomic_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def table_cells(line):
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return [cell.strip() for cell in value.split("|")]


def parse_article(source):
    title = None
    sections = [{"heading": None, "blocks": []}]
    paragraph = []
    bullets = []
    lines = source.splitlines()

    def flush_paragraph():
        if paragraph:
            raw = " ".join(paragraph)
            sections[-1]["blocks"].append(
                {"kind": "paragraph", "raw": raw, "text": plain_text(raw)}
            )
            paragraph.clear()

    def flush_bullets():
        if bullets:
            sections[-1]["blocks"].append({
                "kind": "list",
                "items": [plain_text(item) for item in bullets],
                "raw_items": bullets[:],
            })
            bullets.clear()

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        match = HEADING_RE.match(line)
        if match:
            flush_paragraph()
            flush_bullets()
            level, heading_raw = len(match.group(1)), match.group(2)
            heading = plain_text(heading_raw)
            if level == 1:
                if title is not None:
                    raise RenderError("article.md 只能包含一个一级标题")
                title = heading
            elif level == 2:
                sections.append({"heading": heading, "blocks": []})
            else:
                sections[-1]["blocks"].append(
                    {"kind": "subheading", "raw": heading_raw, "text": heading}
                )
        elif (
            line.startswith("|")
            and index + 1 < len(lines)
            and TABLE_SEPARATOR_RE.match(lines[index + 1].strip())
        ):
            flush_paragraph()
            flush_bullets()
            headers_raw = table_cells(line)
            index += 2
            rows_raw = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows_raw.append(table_cells(lines[index]))
                index += 1
            width = len(headers_raw)
            if width < 2 or any(len(row) != width for row in rows_raw):
                raise RenderError("Markdown 表格列数不一致")
            sections[-1]["blocks"].append({
                "kind": "table",
                "headers": [plain_text(item) for item in headers_raw],
                "raw_headers": headers_raw,
                "rows": [[plain_text(item) for item in row] for row in rows_raw],
                "raw_rows": rows_raw,
            })
            continue
        elif not line:
            flush_paragraph()
            flush_bullets()
        elif line.startswith(("- ", "* ", "+ ")):
            flush_paragraph()
            bullets.append(line[2:])
        elif line.startswith("> "):
            flush_paragraph()
            flush_bullets()
            raw = line[2:]
            sections[-1]["blocks"].append(
                {"kind": "quote", "raw": raw, "text": plain_text(raw)}
            )
        else:
            flush_bullets()
            paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_bullets()
    sections = [item for item in sections if item["heading"] or item["blocks"]]
    if not title:
        raise RenderError("article.md 第一行必须是唯一一级标题")
    if not any(section["blocks"] for section in sections):
        raise RenderError("article.md 没有正文")
    return title, sections


def first_paragraph(sections):
    for section in sections:
        for block in section["blocks"]:
            if block["kind"] == "paragraph":
                return block
    return None


def english_tag(heading):
    mapping = (
        ("成本", "COST & VALUE"), ("效率", "EFFICIENCY"),
        ("数据", "DATA CHECK"), ("企业", "BUSINESS"),
        ("员工", "PEOPLE"), ("技术", "TECHNOLOGY"),
        ("流程", "WORKFLOW"), ("影响", "IMPACT"),
        ("风险", "RISK"), ("结", "CONCLUSION"),
    )
    return next((tag for keyword, tag in mapping if keyword in heading), "KEY INSIGHT")


def render_hero(title, intro, theme):
    layout = theme["layout"]
    intro_html = render_inline(intro.get("raw", intro["text"]), theme) if intro else ""
    title_html = leaf(title)
    if layout == "magazine":
        return (
            '<section style="margin:0 0 30px;background:#FFFFFF;border:1.5px solid rgba(5,150,105,0.16);border-radius:20px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.06);">'
            '<section style="padding:26px 24px 22px;"><section style="display:flex;align-items:center;margin-bottom:20px;">'
            '<span style="width:7px;height:7px;background:#059669;border-radius:50%;display:inline-block;">'
            f'{leaf(" ")}</span><p style="margin:0 10px;font-size:10px;color:#059669;font-weight:700;letter-spacing:3px;">{leaf("TECH INSIGHT")}</p>'
            f'<section style="flex:1;height:1px;background:linear-gradient(to right,#A7F3D0,transparent);">{leaf(" ")}</section></section>'
            f'<p style="font-size:25px;font-weight:900;color:#111827;margin:0 0 14px;line-height:1.25;letter-spacing:-0.6px;">{title_html}</p>'
            f'<section style="width:52px;height:3px;background:linear-gradient(to right,#059669,#34D399);border-radius:2px;margin-bottom:13px;">{leaf(" ")}</section>'
            f'<p style="font-size:14px;color:#6B7280;margin:0;line-height:1.8;">{intro_html}</p></section>'
            '<section style="background:linear-gradient(135deg,#059669,#10B981);padding:10px 24px;display:flex;justify-content:space-between;">'
            f'<p style="margin:0;font-size:11px;color:#FFFFFF;font-weight:600;">{leaf("科技 · 产业 · 人")}</p>'
            f'<p style="margin:0;font-size:9px;color:#D1FAE5;letter-spacing:2px;">{leaf("深度观察")}</p></section></section>'
        )
    if layout == "ticket":
        return (
            '<section style="background:#FFFEF8;border:2px solid #1A1A1A;box-shadow:4px 4px 0 #1A1A1A;margin:0 4px 34px;">'
            '<section style="background:#059669;padding:10px 18px;display:flex;justify-content:space-between;">'
            f'<p style="margin:0;color:#FFFFFF;font-size:10px;letter-spacing:3px;font-weight:700;">{leaf("TECH FIELD NOTE")}</p>'
            f'<p style="margin:0;color:#FFFFFF;font-size:10px;letter-spacing:2px;">{leaf("★★★★★")}</p></section>'
            '<section style="display:flex;"><section style="flex:1;padding:22px 18px;border-right:2px dashed #A7F3D0;">'
            f'<p style="font-size:23px;font-weight:900;color:#1A1A1A;margin:0 0 12px;line-height:1.3;">{title_html}</p>'
            f'<p style="font-size:13px;color:#555555;line-height:1.8;margin:0;padding:12px;background:#F0FDF4;border:1px solid #A7F3D0;">{intro_html}</p></section>'
            '<section style="width:46px;padding:14px 3px;background:#F0FDF4;display:flex;flex-direction:column;align-items:center;justify-content:space-between;">'
            f'<p style="margin:0;font-size:8px;color:#888888;">{leaf("NO. 001")}</p>'
            f'<p style="margin:0;font-size:9px;color:#059669;writing-mode:vertical-rl;letter-spacing:3px;">{leaf("深度阅读")}</p>'
            f'<p style="margin:0;font-size:13px;color:#059669;font-weight:900;">{leaf("A")}</p></section></section>'
            f'<section style="padding:9px 18px;border-top:1px dashed #A7F3D0;text-align:center;"><p style="margin:0;font-size:9px;color:#888888;letter-spacing:2px;">{leaf("VALID FOR ONE READ · ADMIT ONE")}</p></section></section>'
        )
    if layout == "journal":
        return (
            '<section style="background:#FDFDF8;border:1px solid #BFC1B7;border-radius:6px;overflow:hidden;margin-bottom:30px;">'
            '<section style="padding:25px 22px 20px;"><section style="display:flex;align-items:center;margin-bottom:18px;">'
            f'<span style="width:8px;height:8px;background:#1E1F23;border-radius:50%;display:inline-block;">{leaf(" ")}</span>'
            f'<p style="margin:0 9px;font-size:9px;font-weight:700;letter-spacing:3px;color:#65675E;">{leaf("EDITORIAL NOTE")}</p>'
            f'<span style="height:1px;background:#BFC1B7;flex:1;display:inline-block;">{leaf(" ")}</span></section>'
            f'<p style="font-size:24px;font-weight:800;color:#23251D;margin:0 0 12px;line-height:1.25;">{title_html}</p>'
            f'<p style="font-size:13px;color:#65675E;margin:0;line-height:1.8;">{intro_html}</p></section>'
            f'<section style="background:#1E1F23;padding:10px 22px;"><p style="margin:0;font-size:11px;color:#FFFFFF;font-weight:600;">{leaf("技术进步，最终要落到真实工作与生活")}</p></section></section>'
        )
    if layout == "editorial":
        return (
            '<section style="margin:10px 10px 34px;background:#FFFFFF;border-radius:12px;box-shadow:0 4px 24px -4px rgba(220,38,38,0.15);padding:26px 22px;">'
            f'<p style="font-size:42px;color:#DC2626;font-weight:900;margin:0;line-height:0.65;">{leaf("“")}</p>'
            f'<p style="font-size:16px;font-weight:750;color:#1C1917;margin:12px 0 0;line-height:1.8;">{intro_html}</p></section>'
        )
    if layout == "graphite":
        return (
            '<section style="margin:10px 10px 40px;padding:30px 22px 24px;border-top:1px solid #E4E4E7;border-bottom:1px solid #E4E4E7;background:#FFFFFF;">'
            f'<p style="font-size:10px;color:#A1A1AA;letter-spacing:3px;margin:0 0 16px;">{leaf("QUOTE")}</p>'
            f'<p style="font-size:18px;font-weight:700;color:#27272A;margin:0;line-height:1.75;">{intro_html}</p></section>'
        )
    return (
        '<section style="margin:32px 16px 48px;padding:38px 22px;border-top:1px solid #E8E8E8;border-bottom:1px solid #E8E8E8;text-align:center;">'
        f'<p style="font-family:Georgia,\'Times New Roman\',serif;font-size:19px;font-weight:600;color:#2B2B2B;margin:0;line-height:1.9;letter-spacing:0.8px;">{intro_html}</p></section>'
    )


def render_toc(headings, theme):
    items = headings[:3]
    if len(items) < 2:
        return ""
    layout = theme["layout"]
    label = "本文脉络" if layout == "zen" else "本文看点"
    cards = []
    for index, heading in enumerate(items, 1):
        if layout == "editorial":
            card = (
                f'<section style="flex:1;background:#FEF2F2;border:1px solid #FEE2E2;border-radius:9px;padding:14px 10px;text-align:center;">'
                f'<p style="display:inline-block;background:#DC2626;color:#FFFFFF;font-size:11px;font-weight:800;padding:2px 9px;border-radius:4px;margin:0 0 7px;">{leaf(f"{index:02d}")}</p>'
                f'<p style="font-size:12px;font-weight:700;color:#1C1917;margin:0;line-height:1.5;">{leaf(heading)}</p></section>'
            )
        elif layout in {"graphite", "zen"}:
            card = (
                f'<section style="flex:1;background:{theme["soft"]};border-top:1px solid {theme["line"]};padding:16px 10px;">'
                f'<p style="font-size:10px;color:{theme["accent"]};font-weight:600;margin:0 0 7px;letter-spacing:1px;">{leaf(f"{index:02d}")}</p>'
                f'<p style="font-size:12px;font-weight:650;color:{theme["ink"]};margin:0;line-height:1.5;">{leaf(heading)}</p></section>'
            )
        else:
            card = (
                f'<section style="flex:1;background:{theme["soft"]};border:1px solid {theme["line"]};border-radius:{theme["radius"]};padding:13px 10px;">'
                f'<p style="font-size:10px;color:{theme["accent"]};font-weight:800;margin:0 0 6px;">{leaf(f"PART {index:02d}")}</p>'
                f'<p style="font-size:12px;font-weight:700;color:{theme["ink"]};margin:0;line-height:1.5;">{leaf(heading)}</p></section>'
            )
        cards.append(card)
    return (
        f'<section style="margin:0 12px 38px;"><p style="font-size:11px;color:{theme["muted"]};margin:0 0 13px;letter-spacing:2px;">{leaf(label)}</p>'
        f'<section style="display:flex;gap:8px;">{"".join(cards)}</section></section>'
    )


def render_heading(heading, index, total, theme):
    number = "∞" if index == total and END_HEADING_RE.search(heading) else f"{index:02d}"
    tag = "THE END" if number == "∞" else english_tag(heading)
    layout = theme["layout"]
    if layout == "editorial":
        return (
            '<section style="margin:48px 10px 25px;display:flex;align-items:center;padding-bottom:13px;border-bottom:3px solid #DC2626;">'
            f'<p style="background:#DC2626;color:#FFFFFF;font-size:17px;font-weight:900;padding:4px 13px;border-radius:6px;margin:0 13px 0 0;">{leaf(number)}</p>'
            f'<section><p style="font-size:9px;color:#DC2626;font-weight:700;letter-spacing:3px;margin:0 0 2px;">{leaf(tag)}</p>'
            f'<p style="font-size:18px;font-weight:800;color:#1C1917;margin:0;line-height:1.45;">{leaf(heading)}</p></section></section>'
        )
    if layout == "graphite":
        return (
            '<section style="margin:54px 10px 25px;padding-bottom:18px;border-bottom:1px solid #E4E4E7;">'
            f'<p style="font-size:42px;font-weight:900;color:#E4E4E7;margin:0;line-height:0.9;letter-spacing:-2px;">{leaf(number)}</p>'
            f'<p style="font-size:9px;color:#A1A1AA;letter-spacing:3px;margin:10px 0 4px;">{leaf(tag)}</p>'
            f'<p style="font-size:19px;font-weight:800;color:#27272A;margin:0;line-height:1.45;">{leaf(heading)}</p></section>'
        )
    if layout == "zen":
        return (
            '<section style="margin:60px 16px 30px;">'
            f'<p style="font-size:9px;color:#4A5D52;font-weight:600;letter-spacing:4px;margin:0 0 10px;">{leaf(f"{number} · {tag}")}</p>'
            f'<p style="font-family:Georgia,\'Times New Roman\',serif;font-size:22px;font-weight:700;color:#2B2B2B;margin:0 0 15px;line-height:1.45;">{leaf(heading)}</p>'
            f'<section style="width:40px;height:2px;background:#4A5D52;">{leaf(" ")}</section></section>'
        )
    if layout == "ticket":
        return (
            '<section style="margin:44px 20px 24px;display:flex;align-items:center;padding-bottom:12px;border-bottom:2px solid #1A1A1A;">'
            f'<p style="background:#059669;color:#FFFFFF;font-size:11px;font-weight:800;padding:6px 11px;letter-spacing:2px;margin:0 11px 0 0;">{leaf(number)}</p>'
            f'<p style="font-size:18px;font-weight:800;color:#1A1A1A;margin:0;line-height:1.4;">{leaf(heading)}</p></section>'
        )
    if layout == "journal":
        return (
            '<section style="margin:38px 8px 22px;display:flex;align-items:center;gap:13px;">'
            f'<section style="text-align:center;"><p style="margin:0;font-size:24px;font-weight:800;color:#23251D;line-height:1;letter-spacing:-2px;">{leaf(number)}</p>'
            f'<p style="margin:2px 0 0;font-size:7px;font-weight:700;color:#9EA096;letter-spacing:2px;">{leaf("PART")}</p></section>'
            f'<span style="width:1px;height:36px;background:#BFC1B7;display:inline-block;">{leaf(" ")}</span>'
            f'<section><p style="margin:0 0 2px;font-size:17px;font-weight:800;color:#23251D;">{leaf(heading)}</p>'
            f'<p style="margin:0;font-size:9px;color:#65675E;letter-spacing:1.5px;">{leaf(tag)}</p></section></section>'
        )
    return (
        '<section style="margin:44px 20px 24px;display:flex;align-items:center;gap:11px;">'
        f'<p style="margin:0;background:#059669;color:#FFFFFF;font-size:11px;font-weight:800;padding:6px 10px;border-radius:5px;">{leaf(number)}</p>'
        f'<section><p style="margin:0 0 2px;font-size:9px;color:#059669;letter-spacing:2px;font-weight:700;">{leaf(tag)}</p>'
        f'<p style="margin:0;font-size:18px;font-weight:800;color:#111827;line-height:1.45;">{leaf(heading)}</p></section></section>'
    )


def card_style(theme, extra=""):
    border = "2px solid #1A1A1A" if theme["layout"] == "ticket" else f"1px solid {theme['line']}"
    return (
        f"margin:24px 12px;padding:18px;background:{theme['paper']};border:{border};"
        f"border-radius:{theme['radius']};box-shadow:{theme['shadow']};{extra}"
    )


def render_module(module, theme):
    kind = module["kind"]
    labels = {
        "insight": "KEY INSIGHTS", "comparison": "SIDE BY SIDE",
        "process": "WORKFLOW", "metrics": "DATA POINTS",
    }
    extra = f"border-top:4px solid {theme['accent']};"
    if theme["layout"] == "ticket":
        extra = f"border-left:8px solid {theme['accent']};"
    output = [
        f'<section style="{card_style(theme, extra)}">',
        f'<p style="margin:0 0 9px;font-size:9px;line-height:1.5;letter-spacing:2px;color:{theme["accent"]};font-weight:800;">',
        leaf(labels[kind]),
        f'</p><p style="margin:0 0 16px;font-size:18px;line-height:1.5;color:{theme["ink"]};font-weight:800;">',
        leaf(module["title"]), "</p>",
    ]
    if kind == "insight":
        for item in module["items"]:
            output.extend([
                f'<section style="margin:9px 0;padding:12px;background:{theme["soft"]};border-left:3px solid {theme["accent"]};">',
                f'<p style="margin:0 0 4px;font-size:13px;color:{theme["accent"]};font-weight:750;">{leaf(item["label"])}</p>',
                f'<p style="margin:0;font-size:14px;line-height:1.75;color:{theme["body"]};">{leaf(item["text"])}</p></section>',
            ])
    elif kind == "comparison":
        output.append('<section style="display:flex;gap:9px;">')
        for side in (module["left"], module["right"]):
            output.extend([
                f'<section style="flex:1;min-width:0;padding:13px;background:{theme["soft"]};border-top:2px solid {theme["accent"]};">',
                f'<p style="margin:0 0 9px;font-size:14px;color:{theme["accent"]};font-weight:800;">{leaf(side["heading"])}</p>',
            ])
            for item in side["items"]:
                output.append(
                    f'<p style="margin:7px 0;font-size:13px;line-height:1.65;color:{theme["body"]};">{leaf("• ")}{leaf(item)}</p>'
                )
            output.append("</section>")
        output.append("</section>")
    elif kind == "process":
        for index, item in enumerate(module["steps"], 1):
            output.extend([
                '<section style="display:flex;align-items:flex-start;margin:11px 0;">',
                f'<p style="flex:0 0 28px;margin:0 10px 0 0;padding:3px 0;text-align:center;background:{theme["accent"]};color:#FFFFFF;font-size:12px;line-height:22px;">{leaf(index)}</p>',
                f'<section style="flex:1;min-width:0;"><p style="margin:0 0 2px;font-size:13px;color:{theme["accent"]};font-weight:800;">{leaf(item["label"])}</p>',
                f'<p style="margin:0;font-size:14px;line-height:1.7;color:{theme["body"]};">{leaf(item["text"])}</p></section></section>',
            ])
    elif kind == "metrics":
        output.append('<section style="display:flex;gap:9px;flex-wrap:wrap;">')
        for item in module["metrics"]:
            output.extend([
                f'<section style="flex:1;min-width:125px;padding:13px;text-align:center;background:{theme["soft"]};border-bottom:3px solid {theme["accent"]};">',
                f'<p style="margin:0 0 3px;font-size:24px;color:{theme["accent"]};font-weight:850;line-height:1.25;">{leaf(item["value"])}</p>',
                f'<p style="margin:0 0 3px;font-size:13px;color:{theme["ink"]};font-weight:750;">{leaf(item["label"])}</p>',
                f'<p style="margin:0;font-size:11px;color:{theme["muted"]};line-height:1.55;">{leaf(item["note"])}</p></section>',
            ])
        output.append("</section>")
    output.append("</section>")
    return "".join(output)


def render_table(block, theme):
    rows = []
    for row_index, row in enumerate(block["raw_rows"]):
        cells = []
        for cell in row:
            cells.append(
                f'<td style="padding:10px 8px;border:1px solid {theme["line"]};font-size:12px;line-height:1.6;color:{theme["body"]};vertical-align:top;">{render_inline(cell, theme)}</td>'
            )
        background = theme["soft"] if row_index % 2 else theme["paper"]
        rows.append(f'<tr style="background:{background};">{"".join(cells)}</tr>')
    headers = "".join(
        f'<th style="padding:10px 8px;border:1px solid {theme["line"]};background:{theme["accent"]};font-size:12px;line-height:1.5;color:#FFFFFF;text-align:left;">{render_inline(item, theme)}</th>'
        for item in block["raw_headers"]
    )
    return (
        f'<section style="margin:24px 12px;overflow-x:auto;border-radius:{theme["radius"]};">'
        f'<table style="width:100%;border-collapse:collapse;table-layout:fixed;"><thead><tr>{headers}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></section>'
    )


def render_block(block, theme):
    kind = block["kind"]
    if kind == "paragraph":
        side = "16px" if theme["layout"] == "zen" else "14px"
        size = "14px" if theme["layout"] in {"magazine", "ticket"} else "15px"
        return (
            f'<p style="margin:0 {side} 21px;font-size:{size};line-height:1.9;letter-spacing:0.15px;text-align:justify;color:{theme["body"]};">'
            f'{render_inline(block.get("raw", block["text"]), theme)}</p>'
        )
    if kind == "subheading":
        return (
            f'<section style="margin:28px 14px 15px;display:flex;align-items:center;gap:8px;">'
            f'<span style="width:4px;height:17px;background:{theme["accent"]};display:inline-block;">{leaf(" ")}</span>'
            f'<p style="margin:0;font-size:16px;font-weight:800;color:{theme["ink"]};">{render_inline(block.get("raw", block["text"]), theme)}</p></section>'
        )
    if kind == "list":
        items = "".join(
            f'<section style="display:flex;align-items:flex-start;margin:9px 0;">'
            f'<p style="margin:0 9px 0 0;color:{theme["accent"]};font-weight:900;">{leaf(f"{index:02d}")}</p>'
            f'<p style="margin:0;flex:1;font-size:14px;line-height:1.75;color:{theme["body"]};">{render_inline(raw, theme)}</p></section>'
            for index, raw in enumerate(block.get("raw_items", block["items"]), 1)
        )
        style = card_style(theme, f"background:{theme['soft']};")
        return f'<section style="{style}">{items}</section>'
    if kind == "quote":
        style = card_style(
            theme,
            f"background:{theme['soft']};border-left:4px solid {theme['accent']};box-shadow:none;",
        )
        return (
            f'<section style="{style}">'
            f'<p style="margin:0;font-size:15px;line-height:1.85;color:{theme["ink"]};font-weight:650;">{render_inline(block.get("raw", block["text"]), theme)}</p></section>'
        )
    if kind == "table":
        return render_table(block, theme)
    raise RenderError(f"不支持的正文块：{kind}")


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
                if block["kind"] == "table":
                    values = block["headers"] + [cell for row in block["rows"] for cell in row]
                    haystack = normalized(" ".join(values))
                elif block["kind"] == "list":
                    haystack = normalized(" ".join(block["items"]))
                else:
                    haystack = normalized(block["text"])
                if anchor in haystack:
                    match = (section_index, block_index)
                    break
        if match is None:
            raise RenderError(f"信息模块锚点不存在：{anchor}")
        if match in anchors:
            raise RenderError("两个信息模块不能使用同一插入位置")
        anchors[match] = module
    return anchors


def render_end(theme):
    layout = theme["layout"]
    if layout == "ticket":
        return (
            '<section style="margin:42px 20px 12px;text-align:center;border-top:2px solid #1A1A1A;padding-top:16px;">'
            f'<p style="margin:0;font-size:10px;color:#888888;letter-spacing:3px;">{leaf("END OF TICKET")}</p></section>'
        )
    if layout == "journal":
        return (
            '<section style="margin:44px 8px 8px;background:#1E1F23;padding:13px 18px;display:flex;justify-content:space-between;">'
            f'<p style="margin:0;color:#FFFFFF;font-size:10px;letter-spacing:2px;">{leaf("END NOTE")}</p>'
            f'<p style="margin:0;color:#BFC1B7;font-size:10px;">{leaf("保持观察")}</p></section>'
        )
    return (
        f'<section style="margin:48px 14px 8px;text-align:center;"><section style="height:1px;background:{theme["line"]};margin-bottom:14px;">{leaf(" ")}</section>'
        f'<p style="margin:0;font-size:9px;color:{theme["muted"]};letter-spacing:4px;">{leaf("END")}</p></section>'
    )


def render_document(title, sections, plan, theme):
    anchors = module_map(plan, sections)
    font = "-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif"
    output = [
        f'<section style="box-sizing:border-box;max-width:677px;margin:0 auto;padding:8px 0 30px;background:{theme["paper"]};color:{theme["body"]};font-family:{font};overflow-x:hidden;">'
    ]
    intro = first_paragraph(sections)
    output.append(render_hero(title, intro, theme))
    headings = [section["heading"] for section in sections if section["heading"]]
    output.append(render_toc(headings, theme))
    intro_consumed = False
    heading_index = 0
    for section_index, section in enumerate(sections):
        if section["heading"]:
            heading_index += 1
            output.append(render_heading(section["heading"], heading_index, len(headings), theme))
        for block_index, block in enumerate(section["blocks"]):
            if block is intro and not intro_consumed:
                intro_consumed = True
            else:
                output.append(render_block(block, theme))
            module = anchors.get((section_index, block_index))
            if module:
                output.append(render_module(module, theme))
    output.append(render_end(theme))
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
    parser = argparse.ArgumentParser(description="一次生成丰富主题正文与同主题信息模块")
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
