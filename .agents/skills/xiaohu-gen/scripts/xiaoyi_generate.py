#!/usr/bin/env python3
"""Generate one image through xiaoyi (gpt-image-2) with dual-key failover."""

import argparse
import base64
import binascii
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_ENDPOINT = "https://xiaoyiapi.xyz/v1/images/generations"
DEFAULT_MODEL = "gpt-image-2"
SIZE_MAP = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "square": "1024x1024",
    "landscape": "1536x1024",
    "portrait": "1024x1536",
}
MAX_FILE_BYTES = 64 * 1024 * 1024
RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


class XiaoyiError(Exception):
    """Safe user-facing failure that never includes credentials."""


def resolve_size(value):
    """Accept either ratio (1:1, 16:9, 9:16) or direct WxH."""
    value = value.strip()
    if value in SIZE_MAP:
        return SIZE_MAP[value]
    # Accept direct WxH like 1024x1024
    parts = value.lower().split("x")
    if len(parts) == 2:
        try:
            w, h = int(parts[0]), int(parts[1])
            if 256 <= w <= 4096 and 256 <= h <= 4096:
                return f"{w}x{h}"
        except ValueError:
            pass
    allowed = ", ".join(sorted(SIZE_MAP.keys()))
    raise XiaoyiError(f"不支持的尺寸 {value!r}；可用比例：{allowed}，或直接 WxH")


def safe_http_error(exc, api_key):
    try:
        body = exc.read(8192).decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if api_key and body:
        body = body.replace(api_key, "[REDACTED]")
    detail = f": {body}" if body else ""
    return XiaoyiError(f"xiaoyi API HTTP {exc.code}{detail}")


def post_json(endpoint, api_key, payload, timeout):
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise XiaoyiError("endpoint 必须是 HTTPS URL")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "wechat-skill/xiaohu-gen",
        },
    )
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise XiaoyiError("API 响应超过 64 MiB")
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise XiaoyiError("API 返回的不是有效 JSON") from exc
        except urllib.error.HTTPError as exc:
            last_error = safe_http_error(exc, api_key)
            if exc.code not in RETRYABLE_HTTP or attempt == 1:
                raise last_error
        except urllib.error.URLError as exc:
            last_error = XiaoyiError(f"无法连接 API：{exc.reason}")
            if attempt == 1:
                raise last_error
        except (http.client.HTTPException, OSError) as exc:
            last_error = XiaoyiError(f"API 连接中断：{type(exc).__name__}")
            if attempt == 1:
                raise last_error
        time.sleep(1.5 * (attempt + 1))
    raise last_error or XiaoyiError("API 请求失败")


def extract_image(response):
    """Extract b64_json from response data[0]."""
    try:
        item = response["data"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise XiaoyiError("API 响应缺少 data[0]") from exc
    if not isinstance(item, dict):
        raise XiaoyiError("API 响应 data[0] 格式异常")
    encoded = item.get("b64_json")
    if not encoded:
        raise XiaoyiError("API 响应 data[0] 缺少 b64_json（200 OK 但无图片数据）")
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise XiaoyiError("API 返回了无效 Base64 图片") from exc


def write_image(output, data):
    output = Path(output).expanduser().resolve()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        fmt = "png"
        expected_exts = {".png"}
    elif data.startswith(b"\xff\xd8\xff"):
        fmt = "jpeg"
        expected_exts = {".jpg", ".jpeg"}
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        fmt = "webp"
        expected_exts = {".webp"}
    else:
        raise XiaoyiError("生成的数据不是可识别的 PNG/JPEG/WebP 图片")

    if output.suffix.lower() not in expected_exts:
        raise XiaoyiError(
            f"生成图片格式为 {fmt}，但输出路径扩展名 {output.suffix} 不匹配；"
            f"期望 {expected_exts}"
        )
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
        raise XiaoyiError(f"无法写入生成图片 {output}: {exc}") from exc
    return output, fmt


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate one image with xiaoyi (gpt-image-2), dual-key failover"
    )
    parser.add_argument("--prompt-file", required=True, help="完整最终提示词文件")
    parser.add_argument("--output", required=True, help="输出 PNG/JPEG/WebP 路径")
    parser.add_argument(
        "--size", default="1024x1024",
        help="尺寸：比例(1:1/16:9/9:16)或直接 WxH"
    )
    parser.add_argument("--timeout", type=int, default=200, help="单次请求超时秒数")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只检查配置和输入，不调用 API"
    )
    return parser


def try_with_key(endpoint, api_key, payload, timeout, key_label):
    """Attempt one API call; return (response, key_label) or raise."""
    response = post_json(endpoint, api_key, payload, timeout)
    data = extract_image(response)
    return data, key_label


def run(args):
    prompt_path = Path(args.prompt_file).expanduser().resolve()
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise XiaoyiError(f"无法读取提示词文件 {prompt_path}: {exc}") from exc
    if not prompt:
        raise XiaoyiError("提示词文件为空")
    if args.timeout < 1 or args.timeout > 360:
        raise XiaoyiError("timeout 必须在 1–360 秒之间")

    size = resolve_size(args.size)
    model = os.environ.get("XIAOYI_IMAGE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    endpoint = os.environ.get("XIAOYI_IMAGE_ENDPOINT", DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
    primary_key = os.environ.get("XIAOYI_API_KEY_PRIMARY", "").strip()
    secondary_key = os.environ.get("XIAOYI_API_KEY_SECONDARY", "").strip()

    if args.dry_run:
        if not primary_key and not secondary_key:
            raise XiaoyiError("缺少环境变量 XIAOYI_API_KEY_PRIMARY 和 XIAOYI_API_KEY_SECONDARY")
        return {
            "status": "dry-run",
            "prompt_file": str(prompt_path),
            "output": str(Path(args.output).expanduser().resolve()),
            "model": model,
            "size": size,
            "primary_key": bool(primary_key),
            "secondary_key": bool(secondary_key),
        }

    if not primary_key and not secondary_key:
        raise XiaoyiError("缺少环境变量 XIAOYI_API_KEY_PRIMARY 和 XIAOYI_API_KEY_SECONDARY")

    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }

    # Try primary key first
    last_error = None
    used_key_label = None
    data = None
    if primary_key:
        try:
            data, used_key_label = try_with_key(
                endpoint, primary_key, payload, args.timeout, "primary"
            )
        except XiaoyiError as exc:
            last_error = exc
            data = None

    # Failover to secondary key
    if data is None and secondary_key:
        try:
            data, used_key_label = try_with_key(
                endpoint, secondary_key, payload, args.timeout, "secondary"
            )
        except XiaoyiError as exc:
            last_error = exc

    if data is None:
        raise last_error or XiaoyiError("primary 和 secondary key 均失败")

    output, fmt = write_image(args.output, data)
    return {
        "status": "ok",
        "path": str(output),
        "bytes": len(data),
        "format": fmt,
        "model": model,
        "size": size,
        "key_used": used_key_label,
    }


def load_project_env():
    """Load secrets from project env file if available."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "scripts" / "local_env.py"
        if candidate.is_file():
            sys.path.insert(0, str(candidate.parent))
            try:
                from local_env import load_local_env
            except ImportError:
                return
            load_local_env(str(candidate.parent))
            return


def main():
    load_project_env()
    args = build_parser().parse_args()
    try:
        result = run(args)
    except XiaoyiError as exc:
        print(
            json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
