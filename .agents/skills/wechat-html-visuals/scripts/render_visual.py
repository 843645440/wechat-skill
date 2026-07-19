#!/usr/bin/env python3
"""Render constrained WeChat visual specs to deterministic HTML and PNG."""

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


DIMENSIONS = {
    "cover": (1410, 600),
    "insight": (1200, 800),
    "comparison": (1200, 800),
    "process": (1200, 800),
    "metrics": (1200, 800),
}

PALETTES = {
    "emerald": {
        "background": "#eef6f1",
        "background_alt": "#f8fbf9",
        "paper": "#ffffff",
        "paper_translucent": "rgba(255,255,255,0.88)",
        "ink": "#15382a",
        "muted": "#557065",
        "accent": "#16805a",
        "accent_dark": "#0d6243",
        "accent_2": "#e5a93d",
        "soft": "#dcefe5",
        "line": "rgba(22,128,90,0.18)",
        "line_strong": "rgba(22,128,90,0.42)",
        "glow": "rgba(90,195,145,0.20)",
        "shadow": "rgba(25,73,54,0.10)",
    },
    "indigo": {
        "background": "#eff2fb",
        "background_alt": "#fafbff",
        "paper": "#ffffff",
        "paper_translucent": "rgba(255,255,255,0.89)",
        "ink": "#202a4f",
        "muted": "#626b8a",
        "accent": "#5367c7",
        "accent_dark": "#3548a1",
        "accent_2": "#ef9664",
        "soft": "#e0e5fa",
        "line": "rgba(83,103,199,0.18)",
        "line_strong": "rgba(83,103,199,0.42)",
        "glow": "rgba(115,134,225,0.20)",
        "shadow": "rgba(36,48,104,0.10)",
    },
    "amber": {
        "background": "#fbf4e8",
        "background_alt": "#fffdf8",
        "paper": "#ffffff",
        "paper_translucent": "rgba(255,255,255,0.90)",
        "ink": "#4c3420",
        "muted": "#7a6757",
        "accent": "#c77723",
        "accent_dark": "#9a5518",
        "accent_2": "#4a8b77",
        "soft": "#f8e4c6",
        "line": "rgba(199,119,35,0.20)",
        "line_strong": "rgba(199,119,35,0.44)",
        "glow": "rgba(241,177,90,0.22)",
        "shadow": "rgba(103,65,29,0.10)",
    },
    "slate": {
        "background": "#eef1f4",
        "background_alt": "#fafbfc",
        "paper": "#ffffff",
        "paper_translucent": "rgba(255,255,255,0.90)",
        "ink": "#26323c",
        "muted": "#64717b",
        "accent": "#3f6677",
        "accent_dark": "#2c4c5a",
        "accent_2": "#c98962",
        "soft": "#dce7eb",
        "line": "rgba(63,102,119,0.19)",
        "line_strong": "rgba(63,102,119,0.42)",
        "glow": "rgba(98,153,176,0.19)",
        "shadow": "rgba(33,53,63,0.10)",
    },
}

COMMON_KEYS = {"kind", "theme"}
KIND_KEYS = {
    "cover": {"eyebrow", "title", "subtitle"},
    "insight": {"title", "subtitle", "points"},
    "comparison": {"title", "left", "right", "footer"},
    "process": {"title", "subtitle", "steps"},
    "metrics": {"title", "subtitle", "metrics"},
}


class VisualError(RuntimeError):
    pass


def normalized_text(value, field, maximum, required=True):
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise VisualError(f"{field} 必须是字符串")
    value = " ".join(value.split())
    if required and not value:
        raise VisualError(f"{field} 不能为空")
    if len(value) > maximum:
        raise VisualError(f"{field} 超过 {maximum} 字：当前 {len(value)} 字")
    return value


def strict_keys(value, allowed, field):
    if not isinstance(value, dict):
        raise VisualError(f"{field} 必须是对象")
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise VisualError(f"{field} 包含未知字段：{', '.join(unknown)}")


def validate_items(value, field, minimum, maximum, item_keys, validators):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise VisualError(f"{field} 必须包含 {minimum}—{maximum} 项")
    output = []
    for index, item in enumerate(value, 1):
        item_field = f"{field}[{index}]"
        strict_keys(item, item_keys, item_field)
        output.append({key: validator(item.get(key), f"{item_field}.{key}") for key, validator in validators.items()})
    return output


def validate_string_list(value, field, minimum=2, maximum=4, item_maximum=28):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise VisualError(f"{field} 必须包含 {minimum}—{maximum} 项")
    return [normalized_text(item, f"{field}[{index}]", item_maximum) for index, item in enumerate(value, 1)]


def validate_spec(raw):
    if not isinstance(raw, dict):
        raise VisualError("JSON 根节点必须是对象")
    kind = raw.get("kind")
    if kind not in DIMENSIONS:
        raise VisualError(f"kind 必须是：{', '.join(DIMENSIONS)}")
    strict_keys(raw, COMMON_KEYS | KIND_KEYS[kind], "spec")
    theme = raw.get("theme", "emerald")
    if theme not in PALETTES:
        raise VisualError(f"theme 必须是：{', '.join(PALETTES)}")
    spec = {"kind": kind, "theme": theme}

    if kind == "cover":
        spec.update(
            eyebrow=normalized_text(raw.get("eyebrow"), "eyebrow", 18),
            title=normalized_text(raw.get("title"), "title", 28),
            subtitle=normalized_text(raw.get("subtitle"), "subtitle", 40),
        )
    elif kind == "insight":
        spec.update(
            title=normalized_text(raw.get("title"), "title", 24),
            subtitle=normalized_text(raw.get("subtitle"), "subtitle", 44),
            points=validate_items(
                raw.get("points"),
                "points",
                2,
                4,
                {"label", "text"},
                {
                    "label": lambda value, field: normalized_text(value, field, 10),
                    "text": lambda value, field: normalized_text(value, field, 42),
                },
            ),
        )
    elif kind == "comparison":
        spec["title"] = normalized_text(raw.get("title"), "title", 24)
        for side in ("left", "right"):
            strict_keys(raw.get(side), {"heading", "items"}, side)
            spec[side] = {
                "heading": normalized_text(raw[side].get("heading"), f"{side}.heading", 12),
                "items": validate_string_list(raw[side].get("items"), f"{side}.items"),
            }
        spec["footer"] = normalized_text(raw.get("footer"), "footer", 36)
    elif kind == "process":
        spec.update(
            title=normalized_text(raw.get("title"), "title", 24),
            subtitle=normalized_text(raw.get("subtitle"), "subtitle", 36),
            steps=validate_items(
                raw.get("steps"),
                "steps",
                3,
                5,
                {"label", "text"},
                {
                    "label": lambda value, field: normalized_text(value, field, 10),
                    "text": lambda value, field: normalized_text(value, field, 28),
                },
            ),
        )
    else:
        spec.update(
            title=normalized_text(raw.get("title"), "title", 24),
            subtitle=normalized_text(raw.get("subtitle"), "subtitle", 44),
            metrics=validate_items(
                raw.get("metrics"),
                "metrics",
                2,
                4,
                {"value", "label", "note"},
                {
                    "value": lambda value, field: normalized_text(value, field, 12),
                    "label": lambda value, field: normalized_text(value, field, 12),
                    "note": lambda value, field: normalized_text(value, field, 28),
                },
            ),
        )
    return spec


def esc(value):
    return html.escape(value, quote=True)


def card_head(title, subtitle):
    subtitle_html = f'<p class="card-subtitle">{esc(subtitle)}</p>' if subtitle else ""
    return (
        '<header class="card-head">'
        '<section><h1 class="card-title">'
        + esc(title)
        + '</h1><div class="accent-rule" aria-hidden="true"></div></section>'
        + subtitle_html
        + "</header>"
    )


def render_body(spec):
    kind = spec["kind"]
    if kind == "cover":
        return (
            '<main class="canvas"><div class="grain" aria-hidden="true"></div>'
            '<section class="cover-shell"><div class="cover-copy">'
            f'<div class="eyebrow">{esc(spec["eyebrow"])}</div>'
            f'<h1 class="cover-title">{esc(spec["title"])}</h1>'
            f'<p class="cover-subtitle">{esc(spec["subtitle"])}</p></div>'
            '<div class="cover-art" aria-hidden="true"><div class="orbit"></div>'
            '<span class="chip chip-a"></span><span class="chip chip-b"></span>'
            '<span class="chip chip-c"></span></div></section></main>'
        )
    if kind == "insight":
        items = "".join(
            '<article class="insight-item">'
            f'<div class="insight-index">{index:02d}</div><div>'
            f'<div class="item-label">{esc(item["label"])}</div>'
            f'<div class="item-text">{esc(item["text"])}</div></div></article>'
            for index, item in enumerate(spec["points"], 1)
        )
        content = f'<section class="insight-grid count-{len(spec["points"])}">{items}</section>'
        return '<main class="canvas"><div class="grain" aria-hidden="true"></div><section class="card-shell">' + card_head(spec["title"], spec["subtitle"]) + content + "</section></main>"
    if kind == "comparison":
        columns = []
        for side in ("left", "right"):
            items = "".join(f"<li>{esc(item)}</li>" for item in spec[side]["items"])
            columns.append(
                '<article class="compare-column">'
                f'<div class="compare-heading">{esc(spec[side]["heading"])}</div>'
                f'<ul class="compare-list">{items}</ul></article>'
            )
        content = (
            '<section class="comparison-grid">'
            + columns[0]
            + '<div class="compare-vs" aria-hidden="true"></div>'
            + columns[1]
            + '</section><p class="compare-footer">'
            + esc(spec["footer"])
            + "</p>"
        )
        return '<main class="canvas"><div class="grain" aria-hidden="true"></div><section class="card-shell">' + card_head(spec["title"], "") + content + "</section></main>"
    if kind == "process":
        steps = "".join(
            '<article class="step-item">'
            f'<div class="step-number">{index}</div>'
            f'<div class="step-label">{esc(item["label"])}</div>'
            f'<div class="step-text">{esc(item["text"])}</div></article>'
            for index, item in enumerate(spec["steps"], 1)
        )
        content = f'<section class="process-grid" style="--step-count:{len(spec["steps"])}">{steps}</section>'
        return '<main class="canvas"><div class="grain" aria-hidden="true"></div><section class="card-shell">' + card_head(spec["title"], spec["subtitle"]) + content + "</section></main>"
    metrics = "".join(
        '<article class="metric-item"><div>'
        f'<div class="metric-value">{esc(item["value"])}</div>'
        f'<div class="metric-label">{esc(item["label"])}</div></div>'
        f'<div class="metric-note">{esc(item["note"])}</div></article>'
        for item in spec["metrics"]
    )
    content = f'<section class="metrics-grid" style="--metric-count:{len(spec["metrics"])}">{metrics}</section>'
    return '<main class="canvas"><div class="grain" aria-hidden="true"></div><section class="card-shell">' + card_head(spec["title"], spec["subtitle"]) + content + "</section></main>"


def render_html(spec, css):
    width, height = DIMENSIONS[spec["kind"]]
    variables = {
        "canvas-width": f"{width}px",
        "canvas-height": f"{height}px",
        **{key.replace("_", "-"): value for key, value in PALETTES[spec["theme"]].items()},
    }
    root_css = ";".join(f"--{key}:{value}" for key, value in variables.items())
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>:root{{{root_css}}}</style><style>{css}</style></head><body>"
        + render_body(spec)
        + "</body></html>"
    )


def atomic_write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise VisualError(f"无法写入 HTML：{exc}") from exc


def browser_candidates():
    explicit = os.environ.get("HTML_VISUAL_BROWSER", "").strip()
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
        ".cache/ms-playwright/chromium-*/chrome-linux/headless_shell",
        "Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
    ):
        yield from sorted(home.glob(pattern), reverse=True)


def find_browser(override=None):
    candidates = [Path(override).expanduser()] if override else list(browser_candidates())
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise VisualError("找不到 Chrome/Chromium；请安装浏览器或设置 HTML_VISUAL_BROWSER")


def png_dimensions(path):
    try:
        with path.open("rb") as file:
            header = file.read(24)
    except OSError as exc:
        raise VisualError(f"无法读取 PNG：{exc}") from exc
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise VisualError("浏览器输出不是有效 PNG")
    return struct.unpack(">II", header[16:24])


def screenshot(browser, html_path, output, width, height, timeout):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp.png")
    with tempfile.TemporaryDirectory(prefix="wechat-html-visual-") as profile:
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-sync",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--force-device-scale-factor=1",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1000",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            f"--screenshot={temporary}",
            html_path.as_uri(),
        ]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(1, "--no-sandbox")
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise VisualError(f"无法启动浏览器：{exc}") from exc
        deadline = time.monotonic() + timeout
        actual = None
        while time.monotonic() < deadline:
            if temporary.exists():
                try:
                    actual = png_dimensions(temporary)
                    if actual == (width, height):
                        break
                except VisualError:
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
        if actual is None:
            if process.returncode not in (None, 0):
                raise VisualError(f"浏览器退出码 {process.returncode}，且未生成有效 PNG")
            raise VisualError(f"浏览器在 {timeout} 秒内未生成有效 PNG")
    if actual != (width, height):
        raise VisualError(f"PNG 尺寸错误：期望 {width}x{height}，实际 {actual[0]}x{actual[1]}")
    try:
        os.replace(temporary, output)
    except OSError as exc:
        raise VisualError(f"无法保存 PNG：{exc}") from exc


def parse_args():
    parser = argparse.ArgumentParser(description="Render constrained WeChat HTML visuals to PNG")
    parser.add_argument("--spec", required=True, help="视觉图 JSON 规格")
    parser.add_argument("--output", required=True, help="PNG 输出路径")
    parser.add_argument("--html-output", help="HTML 输出路径；默认与 PNG 同名")
    parser.add_argument("--browser", help="Chrome/Chromium 可执行文件")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--html-only", action="store_true", help="只生成 HTML，不启动浏览器")
    return parser.parse_args()


def run(args):
    spec_path = Path(args.spec).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise VisualError("--output 必须使用 .png 扩展名")
    html_output = (
        Path(args.html_output).expanduser().resolve()
        if args.html_output
        else output.with_suffix(".html")
    )
    if args.timeout < 1 or args.timeout > 120:
        raise VisualError("timeout 必须在 1—120 秒之间")
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualError(f"无法读取 JSON：{exc}") from exc
    spec = validate_spec(raw)
    css_path = Path(__file__).resolve().parents[1] / "assets" / "visual.css"
    try:
        css = css_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VisualError(f"无法读取视觉样式：{exc}") from exc
    rendered = render_html(spec, css)
    atomic_write_text(html_output, rendered)
    width, height = DIMENSIONS[spec["kind"]]
    browser = None
    if not args.html_only:
        browser = find_browser(args.browser)
        screenshot(browser, html_output, output, width, height, args.timeout)
    return {
        "status": "html-only" if args.html_only else "ok",
        "kind": spec["kind"],
        "theme": spec["theme"],
        "width": width,
        "height": height,
        "html": str(html_output),
        "png": None if args.html_only else str(output),
        "browser": None if browser is None else str(browser),
        "visual_check": "not-required",
    }


def main():
    args = parse_args()
    try:
        result = run(args)
    except VisualError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
