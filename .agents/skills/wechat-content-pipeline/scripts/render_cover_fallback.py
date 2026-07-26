#!/usr/bin/env python3
"""离线确定性封面兜底渲染器。

当运行环境既没有生图 API（AGNES_API_KEY 等），也没有可用浏览器（
wechat-html-cover 的 Chrome 路径）时，用 Pillow 直接绘制一张编辑部风格的
排版封面，保证流水线不会卡在 cover 阶段。

设计遵循 references/ai-cover-generation.md 的「名 + 色 + 场景」策略中的
可离线部分：主体名文字清晰入画、强调色成为记忆点、不绘制任何官方商标图形。
场景由排版语言（色条、强调数字）代替，不画插画。

输出：stdout 单行 JSON。不打印字体路径以外的环境信息，不写日志文件。
"""

import argparse
import hashlib
import json
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - 环境缺 Pillow 时给出可执行的修法
    print(json.dumps({
        "status": "error",
        "error": "缺少 Pillow：pip install --user Pillow",
    }, ensure_ascii=False))
    sys.exit(1)


RATIOS = {
    "16:9": (1440, 810),
    "2.35:1": (1410, 600),
    "3:2": (1350, 900),
    "1:1": (1080, 1080),
    "20:9": (1440, 648),
}

# 深底 + 单强调色；按 seed 确定性选取，避免同账号连续多篇撞色。
PALETTES = [
    {"bg": "#0E1116", "accent": "#FF4D4F", "title": "#F5F7FA", "sub": "#AAB4C0"},
    {"bg": "#101418", "accent": "#FFC53D", "title": "#F7F8FA", "sub": "#A6B0BC"},
    {"bg": "#0B1220", "accent": "#36CFC9", "title": "#F2F6F9", "sub": "#9FB0BE"},
    {"bg": "#12100E", "accent": "#FF7A45", "title": "#F7F4F1", "sub": "#B3A99F"},
    {"bg": "#0D1117", "accent": "#A0D911", "title": "#F4F7F0", "sub": "#A5B0A2"},
    {"bg": "#14101A", "accent": "#B37FEB", "title": "#F6F3FA", "sub": "#AEA6BC"},
]

FONT_CANDIDATES = [
    # macOS
    ("/System/Library/Fonts/PingFang.ttc", 4),
    ("/System/Library/Fonts/PingFang.ttc", 2),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 1),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/Library/Fonts/Arial Unicode.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0),
    # Linux
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
    ("/usr/share/fonts/truetype/arphic/uming.ttc", 0),
]

PROBE = "验收判断"


class RenderError(Exception):
    pass


def hex_to_rgb(value):
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise RenderError(f"颜色必须是 6 位十六进制：{value}")
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise RenderError(f"颜色解析失败：{value}") from exc


def mix(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def font_candidates():
    override = os.environ.get("WECHAT_COVER_FONT", "").strip()
    if override:
        try:
            index = int(os.environ.get("WECHAT_COVER_FONT_INDEX", "0"))
        except ValueError:
            index = 0
        return [(override, index)] + FONT_CANDIDATES
    return list(FONT_CANDIDATES)


def resolve_font():
    """返回第一款能渲染中文的字体 (path, index)。"""
    tried = []
    for path, index in font_candidates():
        if not os.path.isfile(path):
            continue
        tried.append(path)
        try:
            probe = ImageFont.truetype(path, 64, index=index)
            if probe.getlength(PROBE) > 0 and probe.getbbox(PROBE):
                return path, index
        except Exception:
            continue
    raise RenderError(
        "找不到可渲染中文的字体；设置 WECHAT_COVER_FONT=<字体文件绝对路径>"
        + ("（已尝试：" + "，".join(tried) + "）" if tried else "")
    )


def load_font(path, index, size):
    return ImageFont.truetype(path, size, index=index)


def wrap_text(text, font, max_width):
    """按渲染宽度折行；`|` 为强制换行，英文单词尽量不拆。"""
    lines = []
    for block in text.split("|"):
        block = block.strip()
        if not block:
            continue
        current = ""
        for ch in block:
            trial = current + ch
            if font.getlength(trial) <= max_width or not current:
                current = trial
                continue
            # 回退到最近的词边界，避免拆开英文/数字
            if ch.isalnum() and current[-1].isalnum():
                cut = len(current)
                while cut > 0 and current[cut - 1].isalnum():
                    cut -= 1
                if 0 < cut < len(current):
                    lines.append(current[:cut].rstrip())
                    current = current[cut:] + ch
                    continue
            lines.append(current.rstrip())
            current = ch
        if current.strip():
            lines.append(current.rstrip())
    return lines or [""]


def fit_lines(text, path, index, max_width, max_lines, size_from, size_to):
    size = size_from
    while size >= size_to:
        font = load_font(path, index, size)
        lines = wrap_text(text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines, size
        size -= 4
    font = load_font(path, index, size_to)
    lines = wrap_text(text, font, max_width)
    return font, lines[:max_lines], size_to


def split_highlight(line, highlights):
    """把一行切成 [(片段, 是否强调)]。"""
    if not highlights:
        return [(line, False)]
    spans = []
    idx = 0
    while idx < len(line):
        hit = None
        for word in highlights:
            if not word:
                continue
            if line.startswith(word, idx):
                if hit is None or len(word) > len(hit):
                    hit = word
        if hit:
            spans.append((hit, True))
            idx += len(hit)
        else:
            if spans and not spans[-1][1]:
                spans[-1] = (spans[-1][0] + line[idx], False)
            else:
                spans.append((line[idx], False))
            idx += 1
    return spans


def pick_palette(seed, accent_override):
    digest = hashlib.sha256((seed or "").encode("utf-8")).digest()
    palette = dict(PALETTES[digest[0] % len(PALETTES)])
    if accent_override:
        palette["accent"] = accent_override
    return palette


def render(args):
    if args.ratio not in RATIOS:
        raise RenderError(f"不支持的比例：{args.ratio}（可选 {'、'.join(RATIOS)}）")
    title = (args.title or "").strip()
    if not title:
        raise RenderError("--title 不能为空")

    font_path, font_index = resolve_font()
    palette = pick_palette(args.seed or title, args.accent)
    bg = hex_to_rgb(palette["bg"])
    accent = hex_to_rgb(palette["accent"])
    title_color = hex_to_rgb(palette["title"])
    sub_color = hex_to_rgb(palette["sub"])

    width, height = RATIOS[args.ratio]
    if args.dry_run:
        return {
            "status": "ok",
            "dry_run": True,
            "font": font_path,
            "width": width,
            "height": height,
            "accent": palette["accent"],
        }

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    margin = int(width * 0.067)
    text_left = margin + 48
    max_text_width = width - text_left - margin

    # 右上角装饰色条：编辑部气质，非商标图形
    bar_w = max(10, width // 120)
    gap = bar_w * 2
    bar_x = width - margin - (bar_w * 4 + gap * 3)
    for i in range(4):
        shade = mix(bg, accent, 0.85 - i * 0.2)
        x0 = bar_x + i * (bar_w + gap)
        draw.rectangle([x0, margin, x0 + bar_w, margin + int(height * 0.16)], fill=shade)

    # 先测量整块文字，再垂直居中，避免短标题时下方大片空白
    kicker = (args.kicker or "").strip()
    kicker_font = kicker_gap = None
    if kicker:
        kicker_font = load_font(font_path, font_index, max(26, int(height * 0.043)))
        kicker_gap = int(kicker_font.size * 2.0)

    title_font, title_lines, title_size = fit_lines(
        title, font_path, font_index, max_text_width,
        args.max_lines, int(height * 0.125), int(height * 0.068),
    )
    line_h = int(title_size * 1.42)

    subtitle = (args.subtitle or "").strip()
    sub_font = sub_lines = sub_size = None
    if subtitle:
        sub_font, sub_lines, sub_size = fit_lines(
            subtitle, font_path, font_index, max_text_width, 2,
            int(height * 0.052), int(height * 0.036),
        )

    block_h = (kicker_gap or 0) + line_h * len(title_lines)
    if sub_lines:
        block_h += int(sub_size * 0.6) + int(sub_size * 1.4) * len(sub_lines)
    top_limit = margin + int(height * 0.055)
    bottom_limit = height - int(height * 0.155)
    y = top_limit + max(0, (bottom_limit - top_limit - block_h) // 2)
    block_top = y

    if kicker:
        draw.text((text_left, y), kicker, font=kicker_font, fill=accent)
        y += kicker_gap

    highlights = [h for h in (args.highlight or []) if h.strip()]
    for line in title_lines:
        x = text_left
        for chunk, is_hl in split_highlight(line, highlights):
            draw.text((x, y), chunk, font=title_font, fill=accent if is_hl else title_color)
            x += title_font.getlength(chunk)
        y += line_h
    block_bottom = y - int(line_h * 0.18)

    if sub_lines:
        y += int(sub_size * 0.6)
        for line in sub_lines:
            draw.text((text_left, y), line, font=sub_font, fill=sub_color)
            y += int(sub_size * 1.4)
        block_bottom = y - int(sub_size * 0.4)

    # 左侧强调竖条：与文字块等高
    draw.rectangle(
        [margin, block_top, margin + max(8, width // 160), min(block_bottom, height - margin)],
        fill=accent,
    )

    brand = (args.brand or kicker).strip()
    if brand:
        rule_y = height - int(height * 0.115)
        draw.rectangle([text_left, rule_y, width - margin, rule_y + 2],
                       fill=mix(bg, sub_color, 0.35))
        brand_font = load_font(font_path, font_index, max(24, int(height * 0.038)))
        draw.text((text_left, rule_y + int(height * 0.028)), brand,
                  font=brand_font, fill=sub_color)

    output = os.path.abspath(args.output)
    parent = os.path.dirname(output)
    if parent:
        os.makedirs(parent, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    return {
        "status": "ok",
        "output": output,
        "width": width,
        "height": height,
        "backend": "offline_render",
        "font": font_path,
        "accent": palette["accent"],
        "title_lines": title_lines,
        "bytes": os.path.getsize(output),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="离线确定性封面兜底渲染（无需生图 API 与浏览器）",
    )
    parser.add_argument("--title", required=True, help="封面主文案；`|` 强制换行")
    parser.add_argument("--output", help="输出 PNG 路径；--dry-run 时可省略")
    parser.add_argument("--subtitle", default="", help="副标题，最多 2 行")
    parser.add_argument("--kicker", default="", help="眉标，如账号名或栏目名")
    parser.add_argument("--brand", default="", help="底部品牌名；缺省用 kicker")
    parser.add_argument("--highlight", nargs="*", default=[],
                        help="标题中需要用强调色渲染的片段，可多个")
    parser.add_argument("--ratio", default="16:9", choices=sorted(RATIOS))
    parser.add_argument("--accent", default="", help="强调色 #RRGGBB；缺省按 seed 选")
    parser.add_argument("--seed", default="", help="确定性配色种子，建议用 run_id")
    parser.add_argument("--max-lines", type=int, default=4, help="标题最多行数")
    parser.add_argument("--dry-run", action="store_true", help="只检查字体与参数")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.dry_run and not args.output:
        print(json.dumps({"status": "error", "error": "缺少 --output"},
                         ensure_ascii=False))
        return 2
    if args.max_lines < 1:
        print(json.dumps({"status": "error", "error": "--max-lines 必须 ≥1"},
                         ensure_ascii=False))
        return 2
    try:
        result = render(args)
    except RenderError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    except Exception as exc:  # noqa: BLE001 - 统一成机器可读错误
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
