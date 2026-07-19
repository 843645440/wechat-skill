#!/usr/bin/env python3
"""Render a deterministic WeChat cover with local HTML and Chrome/Chromium."""

import argparse
import html
import json
import os
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
TEMPLATES = ("editorial-ledger", "kinetic-type")
PALETTES = {
    "moyu-green": {"background": "#F0FDF4", "paper": "#FFFFFF", "ink": "#111827", "muted": "#4B5563", "accent": "#059669", "accent-dark": "#065F46", "soft": "#A7F3D0", "line": "rgba(5,150,105,0.28)", "radius": "22px"},
    "red-white": {"background": "#FFF7F7", "paper": "#FFFFFF", "ink": "#1C1917", "muted": "#57534E", "accent": "#DC2626", "accent-dark": "#991B1B", "soft": "#FECACA", "line": "rgba(220,38,38,0.25)", "radius": "18px"},
    "graphite-minimal": {"background": "#FAFAFA", "paper": "#FFFFFF", "ink": "#27272A", "muted": "#71717A", "accent": "#52525B", "accent-dark": "#27272A", "soft": "#E4E4E7", "line": "rgba(82,82,91,0.26)", "radius": "12px"},
    "zen-whitespace": {"background": "#FAFCFA", "paper": "#FFFFFF", "ink": "#2B2B2B", "muted": "#737B76", "accent": "#4A5D52", "accent-dark": "#34423A", "soft": "#D6E4DC", "line": "rgba(74,93,82,0.24)", "radius": "8px"},
    "moyu-ticket": {"background": "#FFFEF8", "paper": "#FFFFFF", "ink": "#1A1A1A", "muted": "#555555", "accent": "#059669", "accent-dark": "#1A1A1A", "soft": "#A7F3D0", "line": "rgba(26,26,26,0.28)", "radius": "2px"},
    "olive-journal": {"background": "#EEEFE9", "paper": "#FDFDF8", "ink": "#23251D", "muted": "#65675E", "accent": "#ED7B2F", "accent-dark": "#1E1F23", "soft": "#D4C9B8", "line": "rgba(77,79,70,0.32)", "radius": "6px"},
}


class CoverError(RuntimeError):
    pass


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
    title_lines = clean_list(raw["title_lines"], "title_lines", 2, 2, 18)
    if "".join(title_lines) != title:
        raise CoverError("title_lines 拼接后必须与 title 完全一致")
    highlights = clean_list(raw["highlights"], "highlights", 0, 2, 8)
    if len(set(highlights)) != len(highlights):
        raise CoverError("highlights 不得重复")
    for item in highlights:
        if item not in title:
            raise CoverError(f"高亮词不在标题中：{item}")
    if template == "editorial-ledger" and highlights:
        if highlights[0] not in title_lines[0]:
            raise CoverError("editorial-ledger 的第一个高亮词必须位于标题第一行")
        if len(highlights) > 1 and not title_lines[1].startswith(highlights[1]):
            raise CoverError("editorial-ledger 的第二个高亮词必须位于标题第二行开头")
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


def render_editorial_ledger(spec):
    accent = spec["highlights"][0] if spec["highlights"] else ""
    inverse = spec["highlights"][1] if len(spec["highlights"]) > 1 else ""
    first_before, first_accent, first_after = split_highlight(spec["title_lines"][0], accent)
    second_before, second_inverse, second_after = split_highlight(spec["title_lines"][1], inverse)
    return (
        '<main class="canvas ledger-canvas">'
        '<section class="ledger-paper-fold" aria-hidden="true"></section>'
        '<section class="ledger-dark-top" aria-hidden="true"></section>'
        '<section class="ledger-dark-left" aria-hidden="true"></section>'
        '<section class="ledger-soft-panel" aria-hidden="true"></section>'
        '<section class="ledger-accent-panel" aria-hidden="true"></section>'
        '<section class="ledger-dots" aria-hidden="true"></section>'
        '<section class="ledger-rule-grid" aria-hidden="true"></section>'
        f'<p class="cover-eyebrow ledger-eyebrow">{html.escape(spec["eyebrow"], quote=True)}</p>'
        '<h1 class="ledger-title">'
        '<span class="ledger-title-line ledger-title-line-one">'
        f'<span class="ledger-prefix">{first_before}</span>'
        f'<span class="ledger-accent-word">{first_accent}</span>'
        f'<span class="ledger-line-rest">{first_after}</span>'
        '</span>'
        '<span class="ledger-title-line ledger-title-line-two">'
        f'<span class="ledger-second-before">{second_before}</span>'
        f'<span class="ledger-inverse-word">{second_inverse}</span>'
        f'<span class="ledger-second-rest">{second_after}</span>'
        '</span></h1>'
        '<section class="ledger-subtitle-strip">'
        '<span class="ledger-subtitle-lead" aria-hidden="true"></span>'
        f'<p class="cover-subtitle ledger-subtitle">{html.escape(spec["subtitle"], quote=True)}</p>'
        '</section></main>'
    )


def render_kinetic_type(spec):
    return (
        '<main class="canvas kinetic-canvas">'
        '<section class="kinetic-dot-field" aria-hidden="true"></section>'
        '<section class="kinetic-orange-slab" aria-hidden="true"></section>'
        '<section class="kinetic-dark-edge" aria-hidden="true"></section>'
        '<section class="kinetic-rings" aria-hidden="true"></section>'
        '<section class="kinetic-route route-one" aria-hidden="true"></section>'
        '<section class="kinetic-route route-two" aria-hidden="true"></section>'
        f'<p class="cover-eyebrow kinetic-eyebrow">{html.escape(spec["eyebrow"], quote=True)}</p>'
        '<h1 class="kinetic-title">'
        f'<span class="kinetic-title-line kinetic-title-line-one">{html.escape(spec["title_lines"][0], quote=True)}</span>'
        f'<span class="kinetic-title-line kinetic-title-line-two">{html.escape(spec["title_lines"][1], quote=True)}</span>'
        '</h1>'
        '<section class="kinetic-subtitle-strip">'
        f'<p class="cover-subtitle kinetic-subtitle">{html.escape(spec["subtitle"], quote=True)}</p>'
        '</section></main>'
    )


def render_html(spec, css):
    variables = ";".join(f"--{key}:{value}" for key, value in PALETTES[spec["theme"]].items())
    body = (
        render_editorial_ledger(spec)
        if spec["template"] == "editorial-ledger"
        else render_kinetic_type(spec)
    )
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
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise CoverError("找不到 Chrome/Chromium；请安装浏览器或设置 WECHAT_COVER_BROWSER")


def png_dimensions(path):
    try:
        header = path.read_bytes()[:24]
    except OSError as exc:
        raise CoverError(f"无法读取 PNG：{exc}") from exc
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise CoverError("浏览器输出不是有效 PNG")
    return struct.unpack(">II", header[16:24])


def screenshot(browser, html_path, output, timeout):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp.png")
    with tempfile.TemporaryDirectory(prefix="wechat-html-cover-") as profile:
        command = [
            str(browser), "--headless=new", "--disable-gpu", "--disable-background-networking",
            "--disable-default-apps", "--disable-dev-shm-usage", "--disable-extensions",
            "--disable-sync", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
            "--force-device-scale-factor=1", "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1000", f"--user-data-dir={profile}",
            f"--window-size={WIDTH},{HEIGHT}", f"--screenshot={temporary}", html_path.as_uri(),
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
        if actual != (WIDTH, HEIGHT):
            raise CoverError(f"PNG 尺寸错误或未生成：期望 {WIDTH}x{HEIGHT}，实际 {actual}")
    os.replace(temporary, output)


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
