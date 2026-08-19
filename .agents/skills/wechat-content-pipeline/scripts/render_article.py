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


DEFAULT_FONT = (
    "-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,"
    "Hiragino Sans GB,Microsoft YaHei,sans-serif"
)
SERIF_FONT = "Songti SC,SimSun,Georgia,Times New Roman,serif"
MONO_FONT = "SF Mono,Consolas,Monaco,monospace"

# 主题字典是**主题的唯一真相源**（Markdown 组件库已归档到 archive/themes-v2/）。
# 必需键：layout / name / paper / ink / body / muted / accent / soft / line /
#         underline / radius / shadow。可选键：font（默认无衬线）、以及各
#         layout 自己用的附加色（dark / darkink / block / blockink / num）。
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
    "moyu-ticket": {
        "layout": "ticket", "name": "摸鱼票据", "paper": "#FFFFFF",
        # muted 原为 #888888，对白底只有 3.54:1，小字号标签不达标，提到 4.81:1。
        "ink": "#1A1A1A", "body": "#555555", "muted": "#727272",
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
    # ── 以下 4 套为「低噪音 / 强母题」组，装饰集中在 hero、章节标题和目录，
    #    正文区一律浅底 + 高行高，长文不累眼。────────────────────────────
    "plain-white": {
        "layout": "plain", "name": "素白", "paper": "#FFFFFF",
        # muted 是 plain 布局里 hero 引言的正文色，必须过 4.5:1，
        # 不能为了「更淡」压到 #9A9A9A 那种 2.8:1 的水平。
        "ink": "#1A1A1A", "body": "#3D3D3D", "muted": "#7D746B",
        "accent": "#8C8378", "soft": "#FAFAF9", "line": "#EAEAE8",
        "underline": "border-bottom:2px solid #D8D4CE;font-weight:600;",
        "radius": "0", "shadow": "none",
        "num": "#E8E6E3",          # 章节大号数字的浅色
    },
    "ink-rule": {
        "layout": "serif-rule", "name": "墨线", "paper": "#FFFFFF",
        "ink": "#111111", "body": "#333333", "muted": "#767676",
        "accent": "#111111", "soft": "#F6F6F6", "line": "#CFCFCF",
        "underline": "border-bottom:1.5px solid #111111;font-weight:600;",
        "radius": "0", "shadow": "none",
        "font": SERIF_FONT,
        "rule": "#111111",         # 分节黑线；line 留给表格等通用边框
    },
    "deep-pool": {
        "layout": "darkhero", "name": "深潭", "paper": "#FFFFFF",
        "ink": "#16202B", "body": "#3C4A57", "muted": "#66747F",
        "accent": "#2E7D8C", "soft": "#F2F6F7", "line": "#DDE6E9",
        "underline": "border-bottom:2px solid #A8CDD4;font-weight:600;",
        "radius": "8px", "shadow": "0 4px 16px rgba(22,32,43,0.08)",
        # onDark 是深色 hero 上的强调色：accent 本身压在 dark 上只有 3.47:1，
        # 10px 的 kicker 不够用，所以另备一个提亮版。
        "dark": "#16202B", "darkink": "#F2F6F7", "darkbody": "#9FB2BF",
        "ondark": "#6FBCC9",
    },
    "color-block": {
        "layout": "colorblock", "name": "色块", "paper": "#FFFFFF",
        "ink": "#14283C", "body": "#3D4E5E", "muted": "#66747F",
        "accent": "#1B5E8C", "soft": "#EDF3F8", "line": "#D3E0EA",
        "underline": "border-bottom:2px solid #A9CBE2;font-weight:600;",
        "radius": "0", "shadow": "none",
        "block": "#1B5E8C", "blockink": "#FFFFFF",
    },
    # ── 新闻 / 正式报道组：不用渐变、投影和营销式 CTA。三套分别承担
    #    快讯长文、沉重事件、专题报告，不能只靠换色冒充不同风格。────────
    "news-wire": {
        "layout": "newswire", "name": "新闻线",
        "paper": "#FFFFFF", "ink": "#111827", "body": "#303844",
        "muted": "#5F6873", "accent": "#273746", "soft": "#F5F6F7",
        "line": "#D8DCE1",
        "underline": "border-bottom:1.5px solid #7B8793;font-weight:650;",
        "radius": "0", "shadow": "none",
    },
    "solemn-gray": {
        "layout": "solemn", "name": "沉静灰",
        "paper": "#FDFCFA", "ink": "#1C1B1A", "body": "#3B3835",
        "muted": "#6A645F", "accent": "#712F38", "soft": "#F3F0ED",
        "line": "#D7D1CC",
        "underline": "border-bottom:1.5px solid #9F7F83;font-weight:650;",
        "radius": "2px", "shadow": "none", "font": SERIF_FONT,
    },
    "formal-brief": {
        "layout": "briefing", "name": "正式简报",
        "paper": "#FFFFFF", "ink": "#152334", "body": "#354455",
        "muted": "#627184", "accent": "#234E70", "soft": "#F2F5F8",
        "line": "#CFD8E2",
        "underline": "border-bottom:2px solid #AFC2D4;font-weight:650;",
        "radius": "4px", "shadow": "none",
    },
}

SOBER_LAYOUTS = {"newswire", "solemn", "briefing"}

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
INLINE_RE = re.compile(
    r"(`[^`\n]+`|\*\*\S(?:.*?\S)?\*\*|__\S(?:.*?\S)?__|"
    r"==\S(?:.*?\S)?==|\+\+\S(?:.*?\S)?\+\+|<u>.+?</u>)"
)
TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
END_HEADING_RE = re.compile(r"结语|结论|总结|写在最后|最后的话|尾声")
IMAGE_RE = re.compile(r"^!\[([^\]\n]*)\]\(([^()\s]+)(?:\s+\"[^\"]*\")?\)$")


class RenderError(RuntimeError):
    pass


def normalized(value):
    return " ".join(str(value).split())


def plain_text(value):
    value = str(value)
    return normalized(INLINE_RE.sub(lambda match: re.sub(
        r"^(?:\*\*|__|==|\+\+|`|<u>)|(?:\*\*|__|==|\+\+|`|</u>)$",
        "",
        match.group(0),
        flags=re.I,
    ), value))


def leaf(value, style=""):
    style_attr = f' style="{style}"' if style else ""
    return f'<span leaf=""{style_attr}>{html.escape(str(value), quote=True)}</span>'


def code_leaf(value):
    """Escape one code line and lock in significant whitespace as &nbsp;.

    WeChat's paste pipeline collapses runs of literal spaces, which would
    destroy indentation and column alignment in code blocks. Leading spaces
    and any interior run of 2+ spaces are converted to non-breaking spaces
    (real, non-collapsible characters) after escaping so entities like
    ``&nbsp;`` are not themselves re-escaped. Single interior spaces are left
    alone so long lines can still wrap at a word boundary.
    """
    escaped = html.escape(str(value), quote=True)
    escaped = re.sub(r"^ +", lambda match: "&nbsp;" * len(match.group(0)), escaped)
    escaped = re.sub(r"  +", lambda match: "&nbsp;" * len(match.group(0)), escaped)
    if not escaped:
        escaped = "&nbsp;"
    return f'<span leaf="">{escaped}</span>'


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
        elif line.startswith("```"):
            flush_paragraph()
            flush_bullets()
            lang = line[3:].strip()
            index += 1
            code_lines = []
            while index < len(lines) and lines[index].strip() != "```":
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1  # skip the closing fence
            # Unclosed fence: falls through with index == len(lines), i.e. the
            # rest of the file is treated as the code block's content — no
            # exception, no infinite loop.
            sections[-1]["blocks"].append({
                "kind": "code", "lang": lang, "code": "\n".join(code_lines),
            })
            continue
        elif image := IMAGE_RE.match(line):
            flush_paragraph()
            flush_bullets()
            sections[-1]["blocks"].append({
                "kind": "image", "alt": image.group(1), "src": image.group(2),
            })
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
    if layout == "newswire":
        # 新闻线：报纸栏线 + 明确的报道属性，不用卡片、渐变或投影。
        return (
            f'<section style="margin:0 14px 36px;border-top:4px solid {theme["accent"]};padding-top:17px;">'
            f'<section style="display:flex;align-items:center;margin-bottom:16px;">'
            f'<p style="margin:0 12px 0 0;font-size:10px;font-weight:800;letter-spacing:2.5px;'
            f'color:{theme["accent"]};">{leaf("NEWS DESK · 事实报道")}</p>'
            f'<section style="flex:1;height:1px;background:{theme["line"]};line-height:0;">{leaf(" ")}</section></section>'
            f'<p style="margin:0 0 16px;font-size:26px;font-weight:850;line-height:1.38;'
            f'letter-spacing:-0.35px;color:{theme["ink"]};">{title_html}</p>'
            f'<p style="margin:0;padding:14px 0;border-top:1px solid {theme["line"]};'
            f'border-bottom:1px solid {theme["line"]};font-size:14px;line-height:1.9;'
            f'color:{theme["body"]};">{intro_html}</p>'
            f'<p style="margin:10px 0 0;font-size:10px;letter-spacing:2px;color:{theme["muted"]};">'
            f'{leaf("事实 · 进展 · 边界")}</p></section>'
        )
    if layout == "solemn":
        # 沉静灰：暖灰纸面、宋体与细酒红线。视觉重量来自留白，不来自大黑块。
        return (
            f'<section style="margin:0 8px 38px;background:{theme["soft"]};'
            f'border-top:6px solid {theme["ink"]};padding:26px 20px 24px;">'
            f'<p style="margin:0 0 16px;font-size:10px;font-weight:700;letter-spacing:2.5px;'
            f'color:{theme["accent"]};">{leaf("SPECIAL REPORT · 重大事件")}</p>'
            f'<p style="margin:0 0 17px;font-size:25px;font-weight:700;line-height:1.48;'
            f'color:{theme["ink"]};">{title_html}</p>'
            f'<section style="width:44px;height:1px;background:{theme["accent"]};'
            f'line-height:0;margin-bottom:15px;">{leaf(" ")}</section>'
            f'<p style="margin:0;font-size:14px;line-height:2;color:{theme["body"]};">{intro_html}</p>'
            f'</section>'
        )
    if layout == "briefing":
        # 正式简报：文档页眉 + 摘要区，适合政策、机构和专题进展说明。
        return (
            f'<section style="margin:0 10px 36px;border:1px solid {theme["line"]};">'
            f'<section style="background:{theme["accent"]};padding:10px 18px;display:flex;'
            f'align-items:center;justify-content:space-between;">'
            f'<p style="margin:0;font-size:10px;font-weight:800;letter-spacing:2.5px;color:#FFFFFF;">'
            f'{leaf("BRIEFING · 专题简报")}</p>'
            f'<p style="margin:0;font-size:9px;letter-spacing:1.5px;color:#FFFFFF;">'
            f'{leaf("FACT / CONTEXT / FINDING")}</p></section>'
            f'<section style="padding:24px 20px 22px;">'
            f'<p style="margin:0 0 15px;font-size:25px;font-weight:800;line-height:1.42;'
            f'color:{theme["ink"]};letter-spacing:-0.25px;">{title_html}</p>'
            f'<p style="margin:0;padding:13px 14px;background:{theme["soft"]};'
            f'border-left:3px solid {theme["accent"]};font-size:14px;line-height:1.9;'
            f'color:{theme["body"]};">{intro_html}</p></section></section>'
        )
    if layout == "plain":
        # 素白：唯一装饰是一条极浅分隔线，靠字号与留白分层。
        return (
            f'<section style="margin:0 14px 34px;padding-bottom:22px;border-bottom:1px solid {theme["line"]};">'
            f'<p style="margin:0 0 14px;font-size:23px;font-weight:700;line-height:1.42;'
            f'color:{theme["ink"]};letter-spacing:-0.2px;">{title_html}</p>'
            f'<p style="margin:0;font-size:14px;line-height:1.9;color:{theme["muted"]};">{intro_html}</p></section>'
        )
    if layout == "serif-rule":
        # 墨线：上下两根黑线夹住标题，像纸质书内页。
        rule = theme.get("rule", theme["ink"])
        return (
            f'<section style="margin:0 14px 36px;">'
            f'<section style="height:2px;background:{rule};line-height:0;margin-bottom:20px;">{leaf(" ")}</section>'
            f'<p style="margin:0 0 16px;font-size:25px;font-weight:700;line-height:1.4;color:{theme["ink"]};">{title_html}</p>'
            f'<p style="margin:0 0 18px;font-size:14px;line-height:1.95;color:{theme["body"]};">{intro_html}</p>'
            f'<section style="height:1px;background:{theme["line"]};line-height:0;">{leaf(" ")}</section></section>'
        )
    if layout == "darkhero":
        # 深潭：深色卡片只用在开头，正文回浅底，整篇不压。
        dark, darkink = theme.get("dark", theme["ink"]), theme.get("darkink", "#FFFFFF")
        return (
            f'<section style="margin:0 0 34px;padding:32px 22px 28px;background:{dark};">'
            f'<p style="margin:0 0 15px;font-size:10px;font-weight:700;letter-spacing:3px;'
            f'color:{theme.get("ondark", theme["accent"])};">{leaf("DEEP DIVE")}</p>'
            f'<p style="margin:0 0 15px;font-size:24px;font-weight:750;line-height:1.45;color:{darkink};">{title_html}</p>'
            f'<p style="margin:0;font-size:14px;line-height:1.95;'
            f'color:{theme.get("darkbody", theme["muted"])};">{intro_html}</p></section>'
        )
    if layout == "colorblock":
        # 色块：整块主色反白，底部一道压深的窄条收口。
        block, blockink = theme.get("block", theme["accent"]), theme.get("blockink", "#FFFFFF")
        return (
            f'<section style="margin:0 0 30px;background:{block};padding:34px 22px 0;">'
            f'<p style="margin:0 0 16px;font-size:10px;font-weight:800;letter-spacing:3.5px;'
            f'color:#FFFFFFB3;">{leaf("DEEP DIVE")}</p>'
            f'<p style="margin:0 0 16px;font-size:25px;font-weight:800;line-height:1.42;'
            f'color:{blockink};letter-spacing:-0.3px;">{title_html}</p>'
            f'<p style="margin:0 0 26px;font-size:14px;line-height:1.95;color:#FFFFFFD9;">{intro_html}</p>'
            f'<section style="height:10px;background:#00000026;margin:0 -22px;line-height:0;">{leaf(" ")}</section>'
            f'</section>'
        )
    # editorial（也是未知 layout 的防御性兜底；argparse 已限定 THEMES 内取值）
    return (
        '<section style="margin:10px 10px 34px;background:#FFFFFF;border-radius:12px;box-shadow:0 4px 24px -4px rgba(220,38,38,0.15);padding:26px 22px;">'
        f'<p style="font-size:42px;color:#DC2626;font-weight:900;margin:0;line-height:0.65;">{leaf("“")}</p>'
        f'<p style="font-size:16px;font-weight:750;color:#1C1917;margin:12px 0 0;line-height:1.8;">{intro_html}</p></section>'
    )


def render_toc(headings, theme):
    items = headings[:3]
    if len(items) < 2:
        return ""
    layout = theme["layout"]
    label = "本文看点"
    if layout in SOBER_LAYOUTS:
        labels = {
            "newswire": "报道提要",
            "solemn": "事件脉络",
            "briefing": "报告目录",
        }
        rows = []
        for index, heading in enumerate(items, 1):
            if layout == "solemn":
                row = (
                    f'<section style="display:flex;align-items:flex-start;padding:11px 0;'
                    f'border-bottom:1px solid {theme["line"]};">'
                    f'<span style="display:inline-block;margin:1px 11px 0 0;padding:2px 6px;'
                    f'border:1px solid {theme["accent"]};font-size:10px;font-weight:700;'
                    f'color:{theme["accent"]};">{leaf(f"{index:02d}")}</span>'
                    f'<span style="font-size:14px;font-weight:650;line-height:1.55;'
                    f'color:{theme["ink"]};">{leaf(heading)}</span></section>'
                )
            elif layout == "briefing":
                row = (
                    f'<section style="display:flex;align-items:center;margin-bottom:6px;'
                    f'background:{theme["soft"]};border-left:3px solid {theme["accent"]};'
                    f'padding:10px 12px;">'
                    f'<span style="width:29px;font-size:10px;font-weight:800;letter-spacing:1px;'
                    f'color:{theme["accent"]};">{leaf(f"{index:02d}")}</span>'
                    f'<span style="font-size:13.5px;font-weight:700;line-height:1.5;'
                    f'color:{theme["ink"]};">{leaf(heading)}</span></section>'
                )
            else:
                row = (
                    f'<section style="display:flex;align-items:flex-start;padding:10px 0;'
                    f'border-bottom:1px solid {theme["line"]};">'
                    f'<span style="width:31px;font-size:10px;font-weight:800;letter-spacing:1px;'
                    f'color:{theme["accent"]};">{leaf(f"{index:02d}")}</span>'
                    f'<span style="font-size:13.5px;font-weight:700;line-height:1.55;'
                    f'color:{theme["ink"]};">{leaf(heading)}</span></section>'
                )
            rows.append(row)
        return (
            f'<section style="margin:0 14px 38px;">'
            f'<p style="margin:0 0 8px;font-size:10px;font-weight:700;letter-spacing:2px;'
            f'color:{theme["muted"]};">{leaf(labels[layout])}</p>'
            f'<section style="border-top:1px solid {theme["line"]};">{"".join(rows)}</section>'
            f'</section>'
        )
    if layout in {"plain", "serif-rule"}:
        # 极简两套不用卡片：编号 + 标题竖排成一份目录，靠细线分隔。
        rows = "".join(
            f'<section style="padding:9px 0;border-bottom:1px solid {theme["line"]};">'
            f'<span style="font-size:11px;font-weight:800;color:{theme["accent"]};'
            f'letter-spacing:1px;margin-right:10px;">{leaf(f"{index:02d}")}</span>'
            f'<span style="font-size:13.5px;font-weight:600;color:{theme["ink"]};">{leaf(heading)}</span>'
            f'</section>'
            for index, heading in enumerate(items, 1)
        )
        return (
            f'<section style="margin:0 14px 36px;">'
            f'<p style="font-size:11px;color:{theme["muted"]};margin:0 0 6px;letter-spacing:2px;">{leaf(label)}</p>'
            f'<section style="border-top:1px solid {theme["line"]};">{rows}</section></section>'
        )
    if layout == "colorblock":
        # 色块：目录做成一列浅底条，左侧一道主色粗边，与章节色条呼应。
        rows = "".join(
            f'<section style="background:{theme["soft"]};border-left:5px solid {theme.get("block", theme["accent"])};'
            f'padding:10px 12px;margin-bottom:6px;">'
            f'<span style="font-size:11px;font-weight:800;color:{theme.get("block", theme["accent"])};'
            f'margin-right:9px;">{leaf(f"{index:02d}")}</span>'
            f'<span style="font-size:13px;font-weight:700;color:{theme["ink"]};">{leaf(heading)}</span>'
            f'</section>'
            for index, heading in enumerate(items, 1)
        )
        return (
            f'<section style="margin:0 14px 36px;">'
            f'<p style="font-size:11px;color:{theme["muted"]};margin:0 0 10px;letter-spacing:2px;">{leaf(label)}</p>'
            f'{rows}</section>'
        )
    cards = []
    for index, heading in enumerate(items, 1):
        if layout == "editorial":
            card = (
                f'<section style="flex:1;background:#FEF2F2;border:1px solid #FEE2E2;border-radius:9px;padding:14px 10px;text-align:center;">'
                f'<p style="display:inline-block;background:#DC2626;color:#FFFFFF;font-size:11px;font-weight:800;padding:2px 9px;border-radius:4px;margin:0 0 7px;">{leaf(f"{index:02d}")}</p>'
                f'<p style="font-size:12px;font-weight:700;color:#1C1917;margin:0;line-height:1.5;">{leaf(heading)}</p></section>'
            )
        else:
            card = (
                f'<section style="flex:1;background:{theme["soft"]};border:1px solid {theme["line"]};border-radius:{theme["radius"]};padding:13px 10px;">'
                f'<p style="font-size:10px;color:{theme["accent"]};font-weight:800;margin:0 0 6px;">{leaf(f"{index:02d}")}</p>'
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
    if layout == "newswire":
        return (
            f'<section style="margin:46px 14px 21px;border-top:2px solid {theme["ink"]};'
            f'padding-top:12px;">'
            f'<p style="margin:0 0 5px;font-size:9px;font-weight:800;letter-spacing:2px;'
            f'color:{theme["accent"]};">{leaf(f"REPORT {number}")}</p>'
            f'<p style="margin:0;font-size:19px;font-weight:800;line-height:1.5;'
            f'color:{theme["ink"]};">{leaf(heading)}</p></section>'
        )
    if layout == "solemn":
        return (
            f'<section style="margin:48px 14px 22px;">'
            f'<section style="display:flex;align-items:center;margin-bottom:10px;">'
            f'<span style="display:inline-block;margin-right:11px;padding:3px 8px;'
            f'border:1px solid {theme["accent"]};font-size:10px;font-weight:700;'
            f'color:{theme["accent"]};">{leaf(number)}</span>'
            f'<span style="flex:1;height:1px;background:{theme["line"]};line-height:0;">'
            f'{leaf(" ")}</span></section>'
            f'<p style="margin:0;font-size:19px;font-weight:700;line-height:1.6;'
            f'color:{theme["ink"]};">{leaf(heading)}</p></section>'
        )
    if layout == "briefing":
        return (
            f'<section style="margin:46px 14px 22px;border-left:4px solid {theme["accent"]};'
            f'padding:2px 0 2px 13px;">'
            f'<p style="margin:0 0 4px;font-size:9px;font-weight:800;letter-spacing:2px;'
            f'color:{theme["accent"]};">{leaf(f"SECTION {number}")}</p>'
            f'<p style="margin:0;font-size:18px;font-weight:800;line-height:1.5;'
            f'color:{theme["ink"]};">{leaf(heading)}</p></section>'
        )
    if layout == "editorial":
        return (
            '<section style="margin:48px 10px 25px;display:flex;align-items:center;padding-bottom:13px;border-bottom:3px solid #DC2626;">'
            f'<p style="background:#DC2626;color:#FFFFFF;font-size:17px;font-weight:900;padding:4px 13px;border-radius:6px;margin:0 13px 0 0;">{leaf(number)}</p>'
            f'<section><p style="font-size:9px;color:#DC2626;font-weight:700;letter-spacing:3px;margin:0 0 2px;">{leaf(tag)}</p>'
            f'<p style="font-size:18px;font-weight:800;color:#1C1917;margin:0;line-height:1.45;">{leaf(heading)}</p></section></section>'
        )
    if layout == "plain":
        # 素白：大号浅色数字压在标题上方，是全篇唯一的「大」元素。
        return (
            f'<section style="margin:44px 14px 20px;">'
            f'<p style="margin:0 0 2px;font-size:34px;font-weight:800;line-height:1;'
            f'color:{theme.get("num", theme["line"])};letter-spacing:-1px;">{leaf(number)}</p>'
            f'<p style="margin:0;font-size:18px;font-weight:700;line-height:1.5;color:{theme["ink"]};">{leaf(heading)}</p></section>'
        )
    if layout == "serif-rule":
        # 墨线：实心黑方块编号 + 标题 + 细线收尾。
        rule = theme.get("rule", theme["ink"])
        return (
            f'<section style="margin:46px 14px 20px;">'
            f'<section style="margin-bottom:12px;">'
            f'<span style="display:inline-block;padding:5px 9px;background:{rule};color:#FFFFFF;'
            f'font-size:12px;font-weight:700;letter-spacing:1px;">{leaf(number)}</span></section>'
            f'<p style="margin:0 0 10px;font-size:19px;font-weight:700;line-height:1.5;color:{theme["ink"]};">{leaf(heading)}</p>'
            f'<section style="height:1px;background:{theme["line"]};line-height:0;">{leaf(" ")}</section></section>'
        )
    if layout == "darkhero":
        # 深潭：小方块编号（取 hero 的深色）+ 一道横线延伸到右边。
        dark = theme.get("dark", theme["ink"])
        return (
            f'<section style="margin:44px 14px 20px;">'
            f'<section style="display:flex;align-items:center;margin-bottom:10px;">'
            f'<span style="display:inline-block;width:22px;height:22px;background:{dark};color:#FFFFFF;'
            f'font-size:11px;font-weight:800;text-align:center;line-height:22px;">{leaf(number)}</span>'
            f'<span style="flex:1;height:1px;background:{theme["line"]};margin-left:10px;">{leaf(" ")}</span></section>'
            f'<p style="margin:0;font-size:18px;font-weight:750;line-height:1.5;color:{theme["ink"]};">{leaf(heading)}</p></section>'
        )
    if layout == "colorblock":
        # 色块：标题整条反白压在主色上，通栏出血，是这套的核心识别点。
        block, blockink = theme.get("block", theme["accent"]), theme.get("blockink", "#FFFFFF")
        return (
            f'<section style="margin:44px 0 22px;background:{block};padding:11px 18px;">'
            f'<section style="display:flex;align-items:center;">'
            f'<span style="display:inline-block;background:#FFFFFF;color:{block};font-size:12px;'
            f'font-weight:800;padding:3px 9px;margin-right:11px;">{leaf(number)}</span>'
            f'<span style="font-size:17px;font-weight:800;color:{blockink};line-height:1.4;">{leaf(heading)}</span>'
            f'</section></section>'
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
            f'<section style="text-align:center;"><p style="margin:0;font-size:24px;font-weight:800;color:#23251D;line-height:1;letter-spacing:-2px;">{leaf(number)}</p></section>'
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


def render_code(block, theme):
    """Fenced code block (```lang ... ```) → WeChat-safe literal rendering.

    Constraints that shape this markup (visual spec originally from
    archive/themes-v2/common-components.md §1, adapted here to use theme colors
    instead of the doc's hardcoded palette; this function is now authoritative):
    - WeChat strips <pre>/class, so everything is inline style on <section>.
    - white-space:pre is unreliable after paste, so each source line becomes
      its own block-level <p style="margin:0">, not one <pre> blob.
    - Leading/aligning spaces are converted to &nbsp; by code_leaf() because
      plain spaces collapse in the editor.
    - No inline markdown parsing runs over code content — lines go through
      code_leaf() (escape + whitespace lock) only, so **/==/`` etc. stay
      literal.
    """
    mono = "'SF Mono',Consolas,Monaco,monospace"
    lang = (block.get("lang") or "").strip()
    lines = block["code"].split("\n")
    header = ""
    if lang:
        header = (
            f'<section style="padding:9px 14px;border-bottom:1px solid {theme["line"]};">'
            f'<span style="font-size:12px;color:{theme["muted"]};font-family:{mono};'
            f'letter-spacing:1px;">{leaf(lang)}</span></section>'
        )
    body = "".join(
        f'<p style="margin:0;font-family:{mono};font-size:13px;line-height:1.6;'
        f'color:{theme["ink"]};">{code_leaf(raw.expandtabs(4))}</p>'
        for raw in lines
    )
    return (
        f'<section style="margin:24px 12px;border-radius:{theme["radius"]};overflow:hidden;'
        f'background:{theme["soft"]};border:1px solid {theme["line"]};'
        f'border-left:3px solid {theme["accent"]};">'
        f'{header}<section style="padding:11px 14px;">{body}</section></section>'
    )


def render_block(block, theme):
    kind = block["kind"]
    if kind == "paragraph":
        side = "14px"
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
    if kind == "code":
        return render_code(block, theme)
    if kind == "image":
        src = html.escape(block["src"], quote=True)
        alt = html.escape(block["alt"], quote=True)
        return (
            f'<section style="margin:28px 14px;text-align:center;">'
            f'<img src="{src}" alt="{alt}" style="display:block;width:100%;height:auto;border-radius:{theme["radius"]};">'
            "</section>"
        )
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
                elif block["kind"] == "code":
                    haystack = normalized(block["code"])
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


def render_follow_cta(theme):
    """Render a topic-appropriate footer.

    General themes keep the engagement CTA. News and report layouts use a
    restrained editorial note instead: asking for likes beside casualties or
    unresolved allegations would undermine the entire sober theme.
    """
    layout = theme["layout"]
    accent = theme["accent"]
    emphasis_color = accent      # 各 layout 可覆盖（深底上必须换成浅色）
    if layout in SOBER_LAYOUTS:
        copy = {
            "newswire": (
                "信息说明",
                "本文按公开信息整理，事实更新与文中判断应分开阅读。",
                "后续进展以权威发布与可核验报道为准。",
            ),
            "solemn": (
                "阅读说明",
                "对受影响者保持克制，对尚未查清的事实保留边界。",
                "不消费苦难，也不替调查和司法补写结论。",
            ),
            "briefing": (
                "报告说明",
                "本文区分事实、解释与判断，资料口径以文中说明为准。",
                "信息发生变化时，应先修订事实层，再调整结论。",
            ),
        }
        label, body, close = copy[layout]
        if layout == "briefing":
            container = (
                f'margin:46px 14px 0;background:{theme["soft"]};'
                f'border-left:4px solid {accent};padding:17px 18px;'
            )
        else:
            container = (
                f'margin:46px 14px 0;border-top:1px solid {accent};padding:17px 0 0;'
            )
        return (
            f'<section style="{container}">'
            f'<p style="margin:0 0 9px;font-size:10px;font-weight:800;letter-spacing:2.5px;'
            f'color:{accent};">{leaf(label)}</p>'
            f'<p style="margin:0 0 7px;font-size:14px;line-height:1.85;'
            f'color:{theme["body"]};">{leaf(body)}</p>'
            f'<p style="margin:0;font-size:13px;line-height:1.8;font-weight:700;'
            f'color:{theme["ink"]};">{leaf(close)}</p></section>'
        )
    if layout == "journal":
        container = (f'margin:44px 8px 0;background:{theme["ink"]};'
                     f'border-radius:{theme["radius"]};padding:18px 20px;')
        label_color, text_color, lead_color = theme["line"], "#EDEEE8", "#FFFFFF"
    elif layout == "ticket":
        container = (f'margin:44px 12px 0;background:{theme["soft"]};'
                     f'border:2px solid {theme["ink"]};padding:16px 18px;')
        label_color, text_color, lead_color = accent, theme["body"], theme["ink"]
    elif layout == "colorblock":
        # 与 hero、章节色条统一：CTA 也做成通栏色块反白。
        # 注意强调色必须改成白：accent 本身就是这块底色，压上去会看不见。
        block = theme.get("block", accent)
        container = f'margin:44px 0 0;background:{block};padding:18px 18px;'
        label_color, text_color, lead_color = "#FFFFFFB3", "#FFFFFFD9", theme.get("blockink", "#FFFFFF")
        emphasis_color = "#FFFFFF"
    elif layout in {"plain", "serif-rule"}:
        # 极简两套不用色块，只用一根上边线把 CTA 与正文分开。
        rule = theme.get("rule", theme["line"])
        container = f'margin:44px 14px 0;border-top:1px solid {rule};padding:18px 0 0;'
        label_color, text_color, lead_color = theme["muted"], theme["body"], theme["ink"]
    else:
        container = (f'margin:44px 12px 0;background:{theme["soft"]};'
                     f'border-radius:{theme["radius"]};border-left:4px solid {accent};'
                     f'padding:18px 18px;')
        label_color, text_color, lead_color = accent, theme["body"], theme["ink"]
    emphasis = f'font-weight:800;color:{emphasis_color};'
    return (
        f'<section style="{container}">'
        f'<p style="margin:0 0 10px;font-size:11px;font-weight:800;letter-spacing:3px;'
        f'color:{label_color};">{leaf("写在最后")}</p>'
        f'<p style="margin:0 0 8px;font-size:14px;line-height:1.85;color:{text_color};">'
        f'{leaf("看到这儿，说明你把它读完了。这类文章能走多远，只取决于两件事：你的")}'
        f'<span style="{emphasis}">{leaf("在看")}</span>{leaf("和")}'
        f'<span style="{emphasis}">{leaf("转发")}</span>{leaf("。")}</p>'
        f'<p style="margin:0;font-size:14px;line-height:1.85;font-weight:700;'
        f'color:{lead_color};">{leaf("顺手")}'
        f'<span style="{emphasis}">{leaf("关注")}</span>'
        f'{leaf("并设为星标，下一篇更新第一时间见。")}</p>'
        f'</section>'
    )


def render_end(theme):
    layout = theme["layout"]
    if layout in SOBER_LAYOUTS:
        labels = {
            "newswire": "END OF REPORT",
            "solemn": "记录结束 · 等待事实更新",
            "briefing": "REPORT END",
        }
        return (
            f'<section style="margin:46px 14px 8px;text-align:center;">'
            f'<section style="height:1px;background:{theme["line"]};margin-bottom:13px;'
            f'line-height:0;">{leaf(" ")}</section>'
            f'<p style="margin:0;font-size:9px;color:{theme["muted"]};letter-spacing:3px;">'
            f'{leaf(labels[layout])}</p></section>'
        )
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


def render_document(title, sections, plan_or_theme, theme=None):
    """Render body images by default; accept a legacy plan only for standalone callers."""
    if theme is None:
        theme = plan_or_theme
        anchors = {}
    else:
        anchors = module_map(plan_or_theme, sections)
    # 字体可由主题覆盖（墨线用衬线）；未声明的主题沿用原来的无衬线栈。
    font = theme.get("font", DEFAULT_FONT)
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
    output.append(render_follow_cta(theme))
    output.append(render_end(theme))
    output.append("</section>")
    return "".join(output)


def coerce_plan_shape(plan, theme):
    """Keep modules when agents omit top-level version/theme shell fields."""
    if not isinstance(plan, dict):
        return plan
    out = dict(plan)
    version = out.get("version", 1)
    if version in (None, "", "1", 1, 1.0):
        out["version"] = 1
    if not out.get("theme"):
        out["theme"] = theme
    if "modules" not in out or out.get("modules") is None:
        out["modules"] = []
    return out


def validate_plan_shape(plan, theme):
    if not isinstance(plan, dict):
        raise RenderError("inline-visuals.json 结构无效")
    # Allow only the three top-level fields after coercion.
    unknown = sorted(set(plan) - {"version", "theme", "modules"})
    if unknown:
        raise RenderError(f"inline-visuals.json 包含未知字段：{', '.join(unknown)}")
    missing = sorted({"version", "theme", "modules"} - set(plan))
    if missing:
        raise RenderError(f"inline-visuals.json 缺少字段：{', '.join(missing)}")
    if plan["version"] != 1 or plan["theme"] != theme or not isinstance(plan["modules"], list):
        raise RenderError("信息模块版本、主题或 modules 无效")
    if len(plan["modules"]) > 3:
        raise RenderError("信息模块不能超过 3 个")


def parse_args():
    parser = argparse.ArgumentParser(description="一次生成丰富主题正文与正文配图")
    parser.add_argument("--article", required=True)
    parser.add_argument("--theme", choices=tuple(THEMES), required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    started = time.monotonic()
    article_path, output_path = map(Path, (args.article, args.output))
    try:
        source = article_path.read_text(encoding="utf-8")
        title, sections = parse_article(source)
        rendered = render_document(title, sections, THEMES[args.theme])
        atomic_text(output_path, rendered + "\n")
    except (OSError, RenderError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    result = {
        "status": "ok", "title": title, "theme": args.theme,
        "image_count": sum(
            1 for section in sections for block in section["blocks"] if block["kind"] == "image"
        ),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
