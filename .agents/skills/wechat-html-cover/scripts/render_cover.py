#!/usr/bin/env python3
"""Render a deterministic WeChat cover with local HTML and Chrome/Chromium."""

import argparse
import html
import json
import os
import re
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path


WIDTH = 1410
HEIGHT = 600
TEMPLATES = ("signal-editorial", "night-signal", "redaction-poster")
PALETTES = {
    "moyu-green": {"background": "#F0FDF4", "paper": "#FFFFFF", "ink": "#111827", "muted": "#4B5563", "accent": "#059669", "accent-dark": "#065F46", "soft": "#A7F3D0", "line": "rgba(5,150,105,0.28)", "radius": "22px"},
    "red-white": {"background": "#FFF7F7", "paper": "#FFFFFF", "ink": "#1C1917", "muted": "#57534E", "accent": "#DC2626", "accent-dark": "#991B1B", "soft": "#FECACA", "line": "rgba(220,38,38,0.25)", "radius": "18px"},
    "graphite-minimal": {"background": "#FAFAFA", "paper": "#FFFFFF", "ink": "#27272A", "muted": "#71717A", "accent": "#52525B", "accent-dark": "#27272A", "soft": "#E4E4E7", "line": "rgba(82,82,91,0.26)", "radius": "12px"},
    "zen-whitespace": {"background": "#FAFCFA", "paper": "#FFFFFF", "ink": "#2B2B2B", "muted": "#737B76", "accent": "#4A5D52", "accent-dark": "#34423A", "soft": "#D6E4DC", "line": "rgba(74,93,82,0.24)", "radius": "8px"},
    "moyu-ticket": {"background": "#FFFEF8", "paper": "#FFFFFF", "ink": "#1A1A1A", "muted": "#555555", "accent": "#059669", "accent-dark": "#1A1A1A", "soft": "#A7F3D0", "line": "rgba(26,26,26,0.28)", "radius": "2px"},
    "olive-journal": {"background": "#EEEFE9", "paper": "#FDFDF8", "ink": "#23251D", "muted": "#65675E", "accent": "#ED7B2F", "accent-dark": "#1E1F23", "soft": "#D4C9B8", "line": "rgba(77,79,70,0.32)", "radius": "6px"},
}
TEMPLATE_PALETTES = {
    "signal-editorial": {
        "background": "#F5F1E8",
        "ink": "#111111",
        "primary": "#1457D9",
        "secondary": "#F3D900",
        "subtitle": "#242424",
    },
    "night-signal": {
        "background": "#06142F",
        "ink": "#F8F6EF",
        "primary": "#FF5A1F",
        "secondary": "#31C7F5",
        "subtitle": "#7DDBF8",
    },
    "redaction-poster": {
        "background": "#F5F1E9",
        "ink": "#F8F5ED",
        "primary": "#F03B33",
        "secondary": "#0C0C0C",
        "subtitle": "#181818",
    },
}
TITLE_SAFE_WIDTH = {
    "signal-editorial": 1150,
    "night-signal": 1130,
    "redaction-poster": 1090,
}


class CoverError(RuntimeError):
    pass


def relative_luminance(value):
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise CoverError(f"对比度检查只接受六位十六进制颜色：{value}")
    channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first, second):
    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def validate_template_contrast(template):
    palette = TEMPLATE_PALETTES[template]
    checks = {
        "标题": (palette["ink"], palette["background"]),
    }
    if template == "redaction-poster":
        checks["标题"] = (palette["ink"], palette["secondary"])
        checks["主题词"] = (palette["primary"], palette["secondary"])
    for label, colors in checks.items():
        ratio = contrast_ratio(*colors)
        if ratio < 4.5:
            raise CoverError(f"{template} 的{label}对比度不足：{ratio:.2f}:1")


def clean_text(value, field, maximum):
    if not isinstance(value, str) or not " ".join(value.split()):
        raise CoverError(f"{field} 必须是非空字符串")
    value = " ".join(value.split())
    if len(value) > maximum:
        raise CoverError(f"{field} 超过 {maximum} 字")
    return value


def clean_list(value, field, minimum, maximum, item_maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise CoverError(f"{field} 必须包含 {minimum}—{maximum} 项")
    return [clean_text(item, f"{field}[{index}]", item_maximum) for index, item in enumerate(value, 1)]


def validate_spec(raw):
    required = {
        "template",
        "theme",
        "eyebrow",
        "title",
        "title_lines",
        "highlights",
        "subtitle",
    }
    if not isinstance(raw, dict):
        raise CoverError("JSON 根节点必须是对象")
    unknown = sorted(set(raw) - required)
    missing = sorted(required - set(raw))
    if unknown:
        raise CoverError(f"包含未知字段：{', '.join(unknown)}")
    if missing:
        raise CoverError(f"缺少字段：{', '.join(missing)}")
    theme = clean_text(raw["theme"], "theme", 64)
    if theme not in PALETTES:
        raise CoverError(f"theme 必须是：{', '.join(PALETTES)}")
    template = clean_text(raw["template"], "template", 32)
    if template not in TEMPLATES:
        raise CoverError(f"template 必须是：{', '.join(TEMPLATES)}")
    title = clean_text(raw["title"], "title", 32)
    title_lines = clean_list(raw["title_lines"], "title_lines", 2, 3, 18)
    if "".join(title_lines) != title:
        raise CoverError("title_lines 拼接后必须与 title 完全一致")
    highlights = clean_list(raw["highlights"], "highlights", 0, 1, 8)
    if len(set(highlights)) != len(highlights):
        raise CoverError("highlights 不得重复")
    for item in highlights:
        if item not in title:
            raise CoverError(f"高亮词不在标题中：{item}")
    if template == "redaction-poster" and highlights:
        if highlights[0] not in title_lines[0]:
            raise CoverError("redaction-poster 的高亮词必须位于标题第一行")
    if template != "redaction-poster" and highlights:
        raise CoverError(f"{template} 不使用标题高亮词")
    return {
        "template": template,
        "theme": theme,
        "eyebrow": clean_text(raw["eyebrow"], "eyebrow", 18),
        "title": title,
        "title_lines": title_lines,
        "highlights": highlights,
        "subtitle": clean_text(raw["subtitle"], "subtitle", 40),
    }


def split_highlight(value, phrase):
    if not phrase or phrase not in value:
        return html.escape(value, quote=True), "", ""
    before, after = value.split(phrase, 1)
    return tuple(html.escape(item, quote=True) for item in (before, phrase, after))


def text_units(value):
    units = 0.0
    for char in value:
        if char.isspace():
            units += 0.32
        elif char.isascii() and char.isalnum():
            units += 0.62 if char.islower() else 0.72
        elif char in "，。！？：；、,.!?;:·—-()（）":
            units += 0.56
        else:
            units += 1.0
    return units


def title_font_size(spec):
    lines = spec["title_lines"]
    maximum_units = max(text_units(line) for line in lines)
    cap = 116 if len(lines) == 2 else 88
    calculated = int(TITLE_SAFE_WIDTH[spec["template"]] / (maximum_units * 1.08))
    return max(54, min(cap, calculated))


def title_style(spec):
    return f"--title-size:{title_font_size(spec)}px;--title-lines:{len(spec['title_lines'])}"


def render_title_lines(spec, class_prefix, highlight=False):
    phrase = spec["highlights"][0] if highlight and spec["highlights"] else ""
    parts = []
    for index, line in enumerate(spec["title_lines"]):
        before, marked, after = split_highlight(line, phrase if index == 0 else "")
        content = (
            f'<span class="{class_prefix}-plain">{before}</span>'
            f'<span class="{class_prefix}-highlight">{marked}</span>'
            f'<span class="{class_prefix}-plain">{after}</span>'
        )
        parts.append(
            f'<span class="{class_prefix}-line {class_prefix}-line-{index + 1}">{content}</span>'
        )
    return "".join(parts)


def render_signal_editorial(spec):
    return (
        '<main class="canvas signal-canvas">'
        '<section class="signal-blue-rail" aria-hidden="true"></section>'
        '<section class="signal-yellow-rule" aria-hidden="true"></section>'
        '<section class="signal-yellow-mark" aria-hidden="true"></section>'
        f'<p class="cover-eyebrow signal-eyebrow">{html.escape(spec["eyebrow"], quote=True)}</p>'
        f'<h1 class="cover-title signal-title" style="{title_style(spec)}">'
        f'{render_title_lines(spec, "signal-title")}</h1>'
        f'<p class="cover-subtitle signal-subtitle">{html.escape(spec["subtitle"], quote=True)}</p>'
        '</main>'
    )


def render_night_signal(spec):
    return (
        '<main class="canvas night-canvas">'
        '<section class="night-orange-short" aria-hidden="true"></section>'
        '<section class="night-orange-long" aria-hidden="true"></section>'
        '<section class="night-cyan-rule night-cyan-rule-one" aria-hidden="true"></section>'
        '<section class="night-cyan-rule night-cyan-rule-two" aria-hidden="true"></section>'
        f'<p class="cover-eyebrow night-eyebrow">{html.escape(spec["eyebrow"], quote=True)}</p>'
        f'<h1 class="cover-title night-title" style="{title_style(spec)}">'
        f'{render_title_lines(spec, "night-title")}</h1>'
        f'<p class="cover-subtitle night-subtitle">{html.escape(spec["subtitle"], quote=True)}</p>'
        '</main>'
    )


def render_redaction_poster(spec):
    return (
        '<main class="canvas redaction-canvas">'
        '<section class="redaction-top-rule" aria-hidden="true"></section>'
        f'<p class="cover-eyebrow redaction-eyebrow">{html.escape(spec["eyebrow"], quote=True)}</p>'
        '<section class="redaction-panel">'
        f'<h1 class="cover-title redaction-title" style="{title_style(spec)}">'
        f'{render_title_lines(spec, "redaction-title", highlight=True)}</h1>'
        '<section class="redaction-accent-rule" aria-hidden="true"></section>'
        '</section>'
        '<section class="redaction-bottom-rule" aria-hidden="true"></section>'
        f'<p class="cover-subtitle redaction-subtitle">{html.escape(spec["subtitle"], quote=True)}</p>'
        '</main>'
    )


def render_html(spec, css):
    validate_template_contrast(spec["template"])
    variables = ";".join(f"--{key}:{value}" for key, value in PALETTES[spec["theme"]].items())
    renderers = {
        "signal-editorial": render_signal_editorial,
        "night-signal": render_night_signal,
        "redaction-poster": render_redaction_poster,
    }
    body = renderers[spec["template"]](spec)
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<style>:root{{{variables}}}</style><style>{css}</style></head>'
        f'<body class="template-{spec["template"]}">{body}</body></html>'
    )


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise CoverError(f"无法写入 HTML：{exc}") from exc


def browser_candidates():
    explicit = os.environ.get("WECHAT_COVER_BROWSER", "").strip()
    if explicit:
        yield Path(explicit).expanduser()
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        value = shutil.which(name)
        if value:
            yield Path(value)
    for value in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ):
        yield Path(value)
    home = Path.home()
    for pattern in (
        ".cache/ms-playwright/chromium-*/chrome-linux/chrome",
        ".cache/ms-playwright/chromium-*/chrome-linux64/chrome",
        ".cache/ms-playwright/chromium-*/chrome-linux/headless_shell",
        "Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
    ):
        yield from sorted(home.glob(pattern), reverse=True)


def find_browser(override=None):
    candidates = [Path(override).expanduser()] if override else list(browser_candidates())
    for candidate in candidates:
        candidate = candidate.expanduser().absolute()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise CoverError("找不到 Chrome/Chromium；请安装浏览器或设置 WECHAT_COVER_BROWSER")


def png_dimensions(path):
    try:
        header = path.read_bytes()[:24]
    except OSError as exc:
        raise CoverError(f"无法读取 PNG：{exc}") from exc
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise CoverError("浏览器输出不是有效 PNG")
    return struct.unpack(">II", header[16:24])


def validate_dumped_dom(value):
    normalized = value.lower()
    error_markers = (
        "err_access_denied", "err_file_not_found", "err_name_not_resolved",
        "err_connection_refused", "your file couldn't be accessed",
        "this site can’t be reached", "this site can't be reached",
    )
    if any(marker in normalized for marker in error_markers):
        raise CoverError("浏览器内容探针检测到错误页")
    if 'class="canvas ' not in value or 'class="cover-title' not in value:
        raise CoverError("浏览器内容探针未找到封面画布或标题")


def probe_dom(browser, html_uri, profile, timeout):
    command = [
        str(browser), "--headless=new", "--disable-gpu", "--disable-background-networking",
        "--disable-default-apps", "--disable-dev-shm-usage", "--disable-extensions",
        "--disable-sync", "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile}", "--dump-dom", html_uri,
    ]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        command.insert(1, "--no-sandbox")
    try:
        result = subprocess.run(
            command, text=True, capture_output=True, timeout=min(timeout, 15)
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CoverError(f"浏览器内容探针失败：{exc}") from exc
    if result.returncode:
        raise CoverError("浏览器内容探针执行失败")
    validate_dumped_dom(result.stdout)


def screenshot(browser, html_path, output, timeout):
    output.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path.home() / "wechat-cover-tmp"
    staging_root.mkdir(mode=0o700, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="render-", dir=staging_root))
    staged_html = staging / "cover.html"
    temporary = staging / "cover.png"
    profile = staging / "profile"
    try:
        shutil.copy2(html_path, staged_html)
        probe_dom(browser, staged_html.as_uri(), profile, timeout)
        command = [
            str(browser), "--headless=new", "--disable-gpu", "--disable-background-networking",
            "--disable-default-apps", "--disable-dev-shm-usage", "--disable-extensions",
            "--disable-sync", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
            "--force-device-scale-factor=1", "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1000", f"--user-data-dir={profile}",
            f"--window-size={WIDTH},{HEIGHT}", f"--screenshot={temporary}", staged_html.as_uri(),
        ]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(1, "--no-sandbox")
        try:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            raise CoverError(f"无法启动浏览器：{exc}") from exc
        deadline = time.monotonic() + timeout
        actual = None
        while time.monotonic() < deadline:
            if temporary.exists():
                try:
                    actual = png_dimensions(temporary)
                    if actual == (WIDTH, HEIGHT):
                        break
                except CoverError:
                    pass
            if process.poll() is not None:
                break
            time.sleep(0.1)
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    process.kill()
        if actual != (WIDTH, HEIGHT) and temporary.exists():
            actual = png_dimensions(temporary)
        if actual != (WIDTH, HEIGHT):
            raise CoverError(f"PNG 尺寸错误或未生成：期望 {WIDTH}x{HEIGHT}，实际 {actual}")
        os.replace(temporary, output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def parse_args():
    parser = argparse.ArgumentParser(description="生成确定性微信公众号封面")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--html-output")
    parser.add_argument("--browser")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--html-only", action="store_true")
    return parser.parse_args()


def run(args):
    spec_path = Path(args.spec).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise CoverError("--output 必须使用 .png 扩展名")
    html_output = Path(args.html_output).expanduser().resolve() if args.html_output else output.with_suffix(".html")
    if not 1 <= args.timeout <= 120:
        raise CoverError("timeout 必须在 1—120 秒之间")
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        css = (Path(__file__).resolve().parents[1] / "assets" / "cover.css").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        raise CoverError(f"无法读取输入：{exc}") from exc
    spec = validate_spec(raw)
    atomic_write(html_output, render_html(spec, css))
    browser = None
    if not args.html_only:
        browser = find_browser(args.browser)
        screenshot(browser, html_output, output, args.timeout)
    return {
        "status": "html-only" if args.html_only else "ok", "theme": spec["theme"],
        "template": spec["template"],
        "width": WIDTH, "height": HEIGHT, "html": str(html_output),
        "png": None if args.html_only else str(output),
        "browser": None if browser is None else str(browser), "visual_check": "not-required",
    }


def main():
    try:
        result = run(parse_args())
    except CoverError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
