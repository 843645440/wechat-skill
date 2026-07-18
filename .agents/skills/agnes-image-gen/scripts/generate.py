#!/usr/bin/env python3
"""Generate one image through Agnes Image 2.1 Flash without external packages."""

import argparse
import base64
import binascii
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_ENDPOINT = "https://apihub.agnes-ai.com/v1/images/generations"
DEFAULT_MODEL = "agnes-image-2.1-flash"
SUPPORTED_RATIOS = {"1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"}
RATIO_ALIASES = {
    "2.35:1": "21:9",
    "2.34:1": "21:9",
    "2.33:1": "21:9",
    "2.39:1": "21:9",
}
SIZE_RE = re.compile(r"^(?:[1-4]K|[1-9][0-9]{1,4}x[1-9][0-9]{1,4})$")
MAX_FILE_BYTES = 64 * 1024 * 1024
RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


class AgnesError(Exception):
    """Safe user-facing failure that never includes credentials."""


def normalize_ratio(value):
    value = value.strip().replace(" ", "")
    value = RATIO_ALIASES.get(value, value)
    if value not in SUPPORTED_RATIOS:
        allowed = ", ".join(sorted(SUPPORTED_RATIOS))
        raise AgnesError(f"不支持的宽高比 {value!r}；可用值：{allowed}，另支持 2.35:1")
    return value


def normalize_size(value):
    value = value.strip().upper()
    if not SIZE_RE.fullmatch(value):
        raise AgnesError("size 必须为 1K、2K、3K、4K 或合法的 WIDTHxHEIGHT")
    return value


def read_limited(path, limit=MAX_FILE_BYTES):
    try:
        size = path.stat().st_size
        if size > limit:
            raise AgnesError(f"文件过大：{path}（上限 {limit // 1024 // 1024} MiB）")
        return path.read_bytes()
    except OSError as exc:
        raise AgnesError(f"无法读取文件 {path}: {exc}") from exc


def image_mime(path, data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    guessed = mimetypes.guess_type(str(path))[0]
    if guessed in {"image/png", "image/jpeg", "image/webp"}:
        return guessed
    raise AgnesError(f"参考文件不是受支持的 PNG/JPEG/WebP 图片：{path}")


def reference_value(value):
    if value.startswith("data:image/"):
        return value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme:
        if parsed.scheme != "https":
            raise AgnesError("参考图片 URL 必须使用 HTTPS")
        return value
    path = Path(value).expanduser().resolve()
    data = read_limited(path)
    mime = image_mime(path, data)
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_payload(model, prompt, size, ratio, references):
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "ratio": ratio,
    }
    if references:
        payload["extra_body"] = {
            "image": references,
            "response_format": "b64_json",
        }
    else:
        payload["return_base64"] = True
    return payload


def safe_http_error(exc, api_key):
    try:
        body = exc.read(8192).decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if api_key and body:
        body = body.replace(api_key, "[REDACTED]")
    detail = f": {body}" if body else ""
    return AgnesError(f"Agnes API HTTP {exc.code}{detail}")


def post_json(endpoint, api_key, payload, timeout):
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AgnesError("AGNES_IMAGE_ENDPOINT 必须是 HTTPS URL")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "wechat-skill/agnes-image-gen",
        },
    )
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise AgnesError("Agnes API 响应超过 64 MiB")
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AgnesError("Agnes API 返回的不是有效 JSON") from exc
        except urllib.error.HTTPError as exc:
            last_error = safe_http_error(exc, api_key)
            if exc.code not in RETRYABLE_HTTP or attempt == 1:
                raise last_error
        except urllib.error.URLError as exc:
            last_error = AgnesError(f"无法连接 Agnes API：{exc.reason}")
            if attempt == 1:
                raise last_error
        time.sleep(1.5 * (attempt + 1))
    raise last_error or AgnesError("Agnes API 请求失败")


def download_https(url, timeout):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AgnesError("Agnes 返回了非 HTTPS 图片 URL")
    request = urllib.request.Request(url, headers={"User-Agent": "wechat-skill/agnes-image-gen"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_FILE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise AgnesError(f"无法下载 Agnes 生成图片：{exc}") from exc
    if len(data) > MAX_FILE_BYTES:
        raise AgnesError("生成图片超过 64 MiB")
    return data


def response_image(response, timeout):
    try:
        item = response["data"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise AgnesError("Agnes API 响应缺少 data[0]") from exc
    encoded = item.get("b64_json") if isinstance(item, dict) else None
    if encoded:
        try:
            return base64.b64decode(encoded, validate=True), "base64"
        except (binascii.Error, ValueError) as exc:
            raise AgnesError("Agnes API 返回了无效 Base64 图片") from exc
    url = item.get("url") if isinstance(item, dict) else None
    if url:
        return download_https(url, timeout), "url"
    raise AgnesError("Agnes API 响应既没有 b64_json 也没有 url")


def image_format(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    raise AgnesError("Agnes 返回的数据不是可识别的 PNG/JPEG/WebP 图片")


def write_image(output, data):
    output = Path(output).expanduser().resolve()
    fmt = image_format(data)
    expected = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}.get(
        output.suffix.lower()
    )
    if expected is None:
        raise AgnesError("输出文件扩展名必须是 .png、.jpg、.jpeg 或 .webp")
    if expected != fmt:
        raise AgnesError(f"生成图片格式为 {fmt}，但输出路径要求 {expected}；拒绝写入错误扩展名")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, output)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise AgnesError(f"无法写入生成图片 {output}: {exc}") from exc
    return output, fmt


def build_parser():
    parser = argparse.ArgumentParser(description="Generate one image with Agnes Image 2.1 Flash")
    parser.add_argument("--prompt-file", required=True, help="完整最终提示词文件")
    parser.add_argument("--output", required=True, help="输出 PNG/JPEG/WebP 路径")
    parser.add_argument("--size", default=os.environ.get("AGNES_IMAGE_SIZE", "2K"))
    parser.add_argument("--ratio", default="16:9")
    parser.add_argument("--ref", action="append", default=[], help="本地图片、Data URI 或 HTTPS URL")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true", help="只检查配置和输入，不调用 API")
    return parser


def run(args):
    prompt_path = Path(args.prompt_file).expanduser().resolve()
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AgnesError(f"无法读取提示词文件 {prompt_path}: {exc}") from exc
    if not prompt:
        raise AgnesError("提示词文件为空")
    if args.timeout < 1 or args.timeout > 360:
        raise AgnesError("timeout 必须在 1–360 秒之间")

    ratio = normalize_ratio(args.ratio)
    size = normalize_size(args.size)
    model = os.environ.get("AGNES_IMAGE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    endpoint = os.environ.get("AGNES_IMAGE_ENDPOINT", DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
    api_key = os.environ.get("AGNES_API_KEY", "").strip()
    references = [reference_value(value) for value in args.ref]

    if args.dry_run:
        if not api_key:
            raise AgnesError("缺少环境变量 AGNES_API_KEY")
        return {
            "status": "dry-run",
            "prompt_file": str(prompt_path),
            "output": str(Path(args.output).expanduser().resolve()),
            "model": model,
            "size": size,
            "ratio": ratio,
            "references": len(references),
            "api_key_configured": True,
        }
    if not api_key:
        raise AgnesError("缺少环境变量 AGNES_API_KEY")

    payload = build_payload(model, prompt, size, ratio, references)
    response = post_json(endpoint, api_key, payload, args.timeout)
    data, source = response_image(response, args.timeout)
    output, fmt = write_image(args.output, data)
    return {
        "status": "ok",
        "path": str(output),
        "bytes": len(data),
        "format": fmt,
        "model": model,
        "size": size,
        "ratio": ratio,
        "references": len(references),
        "response_source": source,
    }


def main():
    args = build_parser().parse_args()
    try:
        result = run(args)
    except AgnesError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
