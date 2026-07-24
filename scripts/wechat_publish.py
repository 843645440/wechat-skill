#!/usr/bin/env python3
"""将已排版 HTML 写入指定微信公众号的草稿箱或提交发布。

凭证只从环境变量读取。配置、内容图片和 access_token 都按账号隔离。
用法见 references/multi-account-publishing.md。
"""

import argparse
import hashlib
import io
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings

try:
    from PIL import Image, ImageFile
except ImportError:  # 安全失败；不得退回只看 magic bytes 的弱校验。
    Image = None
    ImageFile = None


API_BASE = "https://api.weixin.qq.com"
TOKEN_ERRORS = {40001, 40014, 42001}
MP_IMAGE_HOSTS = {"mmbiz.qpic.cn", "mmbiz.qlogo.cn"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
IMG_SRC = re.compile(r"(<img\b[^>]*?\bsrc\s*=\s*)(['\"])(.*?)\2", re.I | re.S)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I | re.S)
PUBLISH_PLACEHOLDER = re.compile(
    r"\{\{[^{}]+\}\}|【(?:插入|待补|待填写)[^】]*】"
)

# 推送草稿/发布默认直连微信 API，忽略 HTTP(S)_PROXY / ALL_PROXY。
# 本机常开代理时，白名单应对准直连出口 IP，而不是代理出口。
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _urlopen_direct(request, timeout=30):
    """Open URL without proxy (WeChat IP whitelist uses direct egress)."""
    return _DIRECT_OPENER.open(request, timeout=timeout)


class PublishError(RuntimeError):
    pass


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"无法读取配置 {path}: {exc}") from exc


def get_account(config, alias):
    accounts = config.get("accounts")
    if not isinstance(accounts, dict) or alias not in accounts:
        known = ", ".join(sorted(accounts or {})) or "（无）"
        raise PublishError(f"配置中没有账号 {alias!r}；可用账号：{known}")
    account = accounts[alias]
    for key in ("appid_env", "secret_env"):
        if not account.get(key):
            raise PublishError(f"账号 {alias!r} 缺少 {key}")
    return account


def env_value(name, label):
    value = os.environ.get(name)
    if not value:
        raise PublishError(f"未设置 {label} 环境变量：{name}")
    return value


def multipart_body(field, filename, data, content_type):
    boundary = "----wechat-skill-" + hashlib.sha256(data).hexdigest()[:24]
    safe_name = filename.replace('"', "")
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{safe_name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    return head + data + f"\r\n--{boundary}--\r\n".encode(), boundary


class WeChatClient:
    def __init__(self, appid, secret, cache_path=None, api_base=API_BASE):
        self.appid = appid
        self.secret = secret
        self.cache_path = os.path.expanduser(cache_path) if cache_path else None
        self.api_base = api_base.rstrip("/")
        self._token = None

    def _read_cache(self):
        if not self.cache_path:
            return None
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                item = json.load(f)
            fresh = item.get("expires_at", 0) > time.time() + 300
            if item.get("appid") == self.appid and fresh:
                return item.get("access_token")
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def _write_cache(self, token, expires_in):
        if not self.cache_path:
            return
        item = {
            "appid": self.appid,
            "access_token": token,
            "expires_at": int(time.time()) + int(expires_in),
        }
        parent = os.path.dirname(self.cache_path)
        if parent:
            os.makedirs(parent, mode=0o700, exist_ok=True)
        tmp = self.cache_path + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(item, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.cache_path)

    def access_token(self, refresh=False):
        if not refresh and self._token:
            return self._token
        if not refresh:
            self._token = self._read_cache()
            if self._token:
                return self._token
        query = urllib.parse.urlencode({
            "grant_type": "client_credential",
            "appid": self.appid,
            "secret": self.secret,
        })
        result = self._request("GET", f"/cgi-bin/token?{query}", authenticated=False)
        token = result.get("access_token")
        if not token:
            raise PublishError(f"获取 access_token 失败：{result}")
        self._token = token
        self._write_cache(token, result.get("expires_in", 7200))
        return token

    def _request(self, method, path, payload=None, headers=None, authenticated=True,
                 retry_token=True):
        if authenticated:
            separator = "&" if "?" in path else "?"
            path += separator + urllib.parse.urlencode({"access_token": self.access_token()})
        data = payload
        req_headers = {"User-Agent": "wechat-skill/1.0"}
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req_headers["Content-Type"] = "application/json; charset=utf-8"
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(self.api_base + path, data=data,
                                         headers=req_headers, method=method)
        try:
            # 强制直连 api.weixin.qq.com，不走本机 HTTP(S)_PROXY
            with _urlopen_direct(request, timeout=30) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise PublishError(f"微信 API 请求失败：{exc}") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PublishError("微信 API 返回了无法解析的响应") from exc
        errcode = result.get("errcode", 0)
        if authenticated and retry_token and errcode in TOKEN_ERRORS:
            self.access_token(refresh=True)
            clean_path = re.sub(r"([?&])access_token=[^&]*&?", r"\1", path).rstrip("?&")
            return self._request(method, clean_path, payload, headers, True, False)
        if errcode:
            raise PublishError(
                f"微信 API 错误 {errcode}: {result.get('errmsg', 'unknown error')}"
            )
        return result

    def upload_content_image(self, filename, data, content_type):
        body, boundary = multipart_body("media", filename, data, content_type)
        result = self._request(
            "POST", "/cgi-bin/media/uploadimg", body,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        if not result.get("url"):
            raise PublishError(f"正文图片上传失败：{result}")
        return result["url"]

    def upload_cover(self, filename, data, content_type):
        body, boundary = multipart_body("media", filename, data, content_type)
        result = self._request(
            "POST", "/cgi-bin/material/add_material?type=image", body,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        if not result.get("media_id"):
            raise PublishError(f"封面图片上传失败：{result}")
        return result["media_id"]

    def add_draft(self, article):
        result = self._request("POST", "/cgi-bin/draft/add", {"articles": [article]})
        if not result.get("media_id"):
            raise PublishError(f"创建草稿失败：{result}")
        return result["media_id"]

    def publish(self, media_id):
        result = self._request(
            "POST", "/cgi-bin/freepublish/submit", {"media_id": media_id}
        )
        if not result.get("publish_id"):
            raise PublishError(f"提交发布失败：{result}")
        return result

    def publish_status(self, publish_id):
        return self._request(
            "POST", "/cgi-bin/freepublish/get", {"publish_id": publish_id}
        )


def _valid_webp(data):
    if (
        len(data) < 20
        or not data.startswith(b"RIFF")
        or data[8:12] != b"WEBP"
        or int.from_bytes(data[4:8], "little") + 8 != len(data)
    ):
        return False
    offset = 12
    has_image_chunk = False
    while offset < len(data):
        if offset + 8 > len(data):
            return False
        chunk_type = data[offset:offset + 4]
        chunk_size = int.from_bytes(data[offset + 4:offset + 8], "little")
        chunk_end = offset + 8 + chunk_size
        if chunk_end > len(data):
            return False
        if chunk_type in (b"VP8 ", b"VP8L", b"ANMF"):
            has_image_chunk = True
        offset = chunk_end + (chunk_size % 2)
    return offset == len(data) and has_image_chunk


def _detected_image_type(data):
    if (
        len(data) >= 24
        and data.startswith(b"\x89PNG\r\n\x1a\n")
        and data[12:16] == b"IHDR"
        and data.endswith(b"IEND\xaeB`\x82")
    ):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if (
        len(data) >= 15
        and data.startswith((b"GIF87a", b"GIF89a"))
        and data.endswith(b"\x3b")
        and b"\x2c" in data[13:-1]
    ):
        return "image/gif"
    if _valid_webp(data):
        return "image/webp"
    return None


def _normalize_image_type(value):
    aliases = {
        "image/jpg": "image/jpeg",
        "image/pjpeg": "image/jpeg",
        "image/x-png": "image/png",
    }
    return aliases.get((value or "").lower(), (value or "").lower())


def _verify_decodable_image(data):
    if Image is None or ImageFile is None:
        raise PublishError("图片内容格式无法完整校验：当前环境缺少 Pillow")
    format_types = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }
    previous_truncated = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(io.BytesIO(data)) as image:
                decoded_type = format_types.get((image.format or "").upper())
                if not decoded_type:
                    raise PublishError("图片内容格式不受支持")
                frame_count = int(getattr(image, "n_frames", 1))
                if frame_count < 1 or frame_count > 500:
                    raise PublishError("图片内容格式的帧数无效或过多")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                for frame_index in range(frame_count):
                    image.seek(frame_index)
                    image.load()
        return decoded_type
    except PublishError:
        raise
    except Exception as exc:
        raise PublishError("图片内容格式无效或已损坏") from exc
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = previous_truncated


def read_image(source, base_dir, allow_outside=False, strict_declared=True):
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in ("http", "https"):
        req = urllib.request.Request(source, headers={"User-Agent": "wechat-skill/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read(MAX_IMAGE_BYTES + 1)
                content_type = response.headers.get_content_type()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise PublishError(f"下载图片失败 {source}: {exc}") from exc
        if len(data) > MAX_IMAGE_BYTES:
            raise PublishError(f"图片超过 20 MiB：{source}")
        filename = os.path.basename(parsed.path) or "image"
    elif parsed.scheme == "":
        base_real = os.path.realpath(base_dir)
        path = source if os.path.isabs(source) else os.path.join(base_real, source)
        path = os.path.realpath(path)
        if not allow_outside and os.path.commonpath((base_real, path)) != base_real:
            raise PublishError(f"本地图片路径越出 HTML 目录：{source}")
        try:
            with open(path, "rb") as f:
                data = f.read(MAX_IMAGE_BYTES + 1)
        except OSError as exc:
            raise PublishError(f"读取图片失败 {path}: {exc}") from exc
        if len(data) > MAX_IMAGE_BYTES:
            raise PublishError(f"图片超过 20 MiB：{source}")
        filename = os.path.basename(path)
        content_type = mimetypes.guess_type(path)[0]
    else:
        raise PublishError(f"不支持的图片地址：{source}")
    guessed_type = mimetypes.guess_type(filename)[0]
    if not content_type or content_type == "application/octet-stream":
        content_type = guessed_type
    if not content_type or not content_type.startswith("image/"):
        raise PublishError(f"文件不是可识别的图片：{source}")
    detected_type = _detected_image_type(data)
    if not detected_type:
        raise PublishError(f"图片内容格式无法识别：{source}")
    decoded_type = _verify_decodable_image(data)
    if decoded_type != detected_type:
        raise PublishError(
            f"图片 magic bytes 类型 {detected_type} 与解码结果 {decoded_type} 不一致：{source}"
        )
    declared_types = {
        _normalize_image_type(value)
        for value in (content_type, guessed_type)
        if value and value.startswith("image/")
    }
    if strict_declared and any(value != detected_type for value in declared_types):
        declared = ", ".join(sorted(declared_types))
        raise PublishError(
            f"图片声明格式 {declared} 与实际格式 {detected_type} 不一致：{source}"
        )
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }[detected_type]
    filename = os.path.splitext(filename)[0] + extension
    return filename, data, detected_type


def upload_html_images(html, html_path, client):
    uploaded = {}
    skipped = 0

    def replace_tag(tag_match):
        nonlocal skipped
        tag = tag_match.group(0)
        match = IMG_SRC.search(tag)
        if not match:
            return tag
        source = match.group(3)
        parsed = urllib.parse.urlparse(source)
        if parsed.hostname in MP_IMAGE_HOSTS:
            return tag
        if source not in uploaded:
            try:
                filename, data, content_type = read_image(
                    source, os.path.dirname(html_path), strict_declared=False
                )
            except PublishError as exc:
                if "路径越出" in str(exc):
                    raise
                skipped += 1
                return ""
            uploaded[source] = client.upload_content_image(filename, data, content_type)
        replacement = match.group(1) + match.group(2) + uploaded[source] + match.group(2)
        return IMG_SRC.sub(replacement, tag, count=1)

    return IMG_TAG.sub(replace_tag, html), uploaded, skipped


def validate_html(html, strict=False):
    try:
        from validate_gzh_html import validate
    except ImportError as exc:
        raise PublishError(f"无法加载 HTML 校验器：{exc}") from exc
    errors, warnings, _ = validate(html)
    if errors or (strict and warnings):
        details = "；".join(errors + warnings)
        raise PublishError(f"HTML 校验未通过：{details}")
    for warning in warnings:
        print(f"⚠ {warning}", file=sys.stderr)


def validate_publish_ready(html):
    match = PUBLISH_PLACEHOLDER.search(html)
    if match:
        raise PublishError(f"HTML 仍包含发布占位内容：{match.group(0)}")


def preflight_send(account, args, html):
    """Validate all local publish inputs without credentials or network access."""
    base_dir = os.path.dirname(os.path.abspath(args.html))
    checked = set()
    skipped = set()
    for match in IMG_SRC.finditer(html):
        source = match.group(3)
        parsed = urllib.parse.urlparse(source)
        if parsed.hostname in MP_IMAGE_HOSTS:
            continue
        if parsed.scheme in ("http", "https"):
            raise PublishError(f"dry-run 不允许联网校验外部图片：{source}")
        if source not in checked and source not in skipped:
            try:
                read_image(source, base_dir, strict_declared=False)
                checked.add(source)
            except PublishError as exc:
                if "路径越出" in str(exc):
                    raise
                skipped.add(source)
    if args.cover:
        parsed = urllib.parse.urlparse(args.cover)
        if parsed.scheme in ("http", "https"):
            raise PublishError(f"dry-run 不允许联网校验外部封面：{args.cover}")
        read_image(args.cover, os.getcwd(), allow_outside=True)
    else:
        env_name = account.get("default_thumb_media_id_env")
        has_thumb = bool(
            (env_name and os.environ.get(env_name))
            or account.get("default_thumb_media_id")
        )
        if not has_thumb:
            raise PublishError("dry-run 需要有效 --cover 或已配置的默认 thumb_media_id")
    return len(checked), len(skipped)


def write_result(result, path=None):
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if path:
        path = os.path.abspath(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + f".{os.getpid()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(rendered + "\n")
            os.replace(tmp, path)
        except OSError as exc:
            raise PublishError(f"无法写入结果文件 {path}: {exc}") from exc
    print(rendered)


def client_for_account(config, alias, no_token_cache=False):
    account = get_account(config, alias)
    appid = env_value(account["appid_env"], "AppID")
    secret = env_value(account["secret_env"], "AppSecret")
    if no_token_cache:
        cache_path = None
    else:
        cache_dir = os.path.expanduser(config.get(
            "token_cache_dir", "~/.cache/wechat-skill"
        ))
        account_hash = hashlib.sha256(appid.encode()).hexdigest()[:16]
        cache_path = os.path.join(cache_dir, f"token-{account_hash}.json")
    return account, WeChatClient(appid, secret, cache_path)


def resolve_thumb(account, args, client):
    if args.cover:
        filename, data, content_type = read_image(
            args.cover, os.getcwd(), allow_outside=True
        )
        return client.upload_cover(filename, data, content_type)
    env_name = account.get("default_thumb_media_id_env")
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    if account.get("default_thumb_media_id"):
        return account["default_thumb_media_id"]
    raise PublishError("必须传 --cover，或为账号配置默认 thumb_media_id")


def wait_for_publish(client, publish_id, timeout):
    deadline = time.monotonic() + timeout
    while True:
        result = client.publish_status(publish_id)
        status = result.get("publish_status")
        if status == 0:
            return result
        if status != 1:
            raise PublishError(f"发布任务失败（status={status}）：{result}")
        if time.monotonic() >= deadline:
            raise PublishError(f"发布任务在 {timeout} 秒内未完成：{publish_id}")
        time.sleep(min(5, max(0.1, deadline - time.monotonic())))


def cmd_accounts(config):
    for alias, account in sorted(config.get("accounts", {}).items()):
        print(f"{alias}\t{account.get('label', alias)}")


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return number


def cmd_send(config, args):
    account = get_account(config, args.account)
    try:
        with open(args.html, encoding="utf-8") as f:
            html = f.read().strip()
    except OSError as exc:
        raise PublishError(f"无法读取 HTML：{exc}") from exc
    validate_html(html, args.strict)
    validate_publish_ready(html)
    if args.dry_run:
        checked_images, skipped_images = preflight_send(account, args, html)
        result = {
            "dry_run": True,
            "account": args.account,
            "action": args.action,
            "run_id": getattr(args, "run_id", None),
            "html": os.path.abspath(args.html),
            "title": args.title,
            "content_images": len(IMG_SRC.findall(html)),
            "checked_local_images": checked_images,
            "skipped_content_images": skipped_images,
            "cover": args.cover or "configured thumb_media_id",
        }
        write_result(result, args.result_file)
        return

    account, client = client_for_account(config, args.account, args.no_token_cache)
    html, images, skipped_images = upload_html_images(
        html, os.path.abspath(args.html), client
    )
    thumb_media_id = resolve_thumb(account, args, client)
    article = {
        "title": args.title,
        "author": args.author if args.author is not None else account.get("default_author", ""),
        "digest": args.digest if args.digest is not None else account.get("default_digest", ""),
        "content": html,
        "content_source_url": (
            args.source_url if args.source_url is not None
            else account.get("default_source_url", "")
        ),
        "thumb_media_id": thumb_media_id,
        "need_open_comment": int(account.get("need_open_comment", 0)),
        "only_fans_can_comment": int(account.get("only_fans_can_comment", 0)),
    }
    draft_media_id = client.add_draft(article)
    result = {
        "account": args.account,
        "action": args.action,
        "run_id": getattr(args, "run_id", None),
        "draft_media_id": draft_media_id,
        "uploaded_content_images": len(images),
        "skipped_content_images": skipped_images,
    }
    if args.action == "publish":
        publish_result = client.publish(draft_media_id)
        result.update(publish_result)
        if args.wait_seconds:
            result["publish_result"] = wait_for_publish(
                client, publish_result["publish_id"], args.wait_seconds
            )
    write_result(result, args.result_file)


def cmd_publish(config, args):
    _, client = client_for_account(config, args.account, args.no_token_cache)
    publish_result = client.publish(args.media_id)
    result = {
        "account": args.account,
        "action": "publish",
        "draft_media_id": args.media_id,
        **publish_result,
    }
    if args.wait_seconds:
        result["publish_result"] = wait_for_publish(
            client, publish_result["publish_id"], args.wait_seconds
        )
    write_result(result, args.result_file)


def build_parser():
    parser = argparse.ArgumentParser(description="多账号微信公众号草稿/发布工具")
    parser.add_argument(
        "--config", default="wechat-accounts.json", help="账号配置 JSON"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("accounts", help="列出账号别名（不读取凭证）")
    send = sub.add_parser("send", help="创建草稿，或创建后提交发布")
    send.add_argument("--account", required=True, help="配置中的账号别名")
    send.add_argument("--html", required=True, help="已通过校验的正文 HTML")
    send.add_argument("--title", required=True)
    send.add_argument("--author")
    send.add_argument("--digest")
    send.add_argument("--source-url")
    send.add_argument("--cover", help="封面图片路径或 URL")
    send.add_argument("--action", choices=("draft", "publish"), default="draft")
    send.add_argument("--run-id", help="调用方生成的本次运行 ID")
    send.add_argument(
        "--wait-seconds", type=nonnegative_int, default=0,
        help="提交发布后等待最终结果；定时任务建议 300",
    )
    send.add_argument("--strict", action="store_true", help="HTML warning 也视为失败")
    send.add_argument("--dry-run", action="store_true", help="只校验输入，不调用微信 API")
    send.add_argument("--no-token-cache", action="store_true")
    send.add_argument("--result-file", help="同时把 JSON 结果原子写入指定文件")
    publish = sub.add_parser("publish", help="发布已经审核过的现有草稿")
    publish.add_argument("--account", required=True, help="配置中的账号别名")
    publish.add_argument("--media-id", required=True, help="已有草稿的 media_id")
    publish.add_argument(
        "--wait-seconds", type=nonnegative_int, default=0,
        help="提交发布后等待最终结果；定时任务建议 300",
    )
    publish.add_argument("--no-token-cache", action="store_true")
    publish.add_argument("--result-file", help="同时把 JSON 结果原子写入指定文件")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        config = load_json(args.config)
        if args.command == "accounts":
            cmd_accounts(config)
        elif args.command == "send":
            cmd_send(config, args)
        else:
            cmd_publish(config, args)
    except PublishError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
