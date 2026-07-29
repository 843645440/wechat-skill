import base64
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import wechat_publish as wp  # noqa: E402


class FakeClient:
    def __init__(self):
        self.uploads = []

    def upload_content_image(self, filename, data, content_type):
        self.uploads.append((filename, data, content_type))
        return "https://mmbiz.qpic.cn/uploaded/" + filename


class PublishTests(unittest.TestCase):
    PNG_1X1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    def test_account_aliases_keep_separate_environment_names(self):
        config = {
            "accounts": {
                "a": {"appid_env": "A_ID", "secret_env": "A_SECRET"},
                "b": {"appid_env": "B_ID", "secret_env": "B_SECRET"},
            }
        }
        self.assertEqual(wp.get_account(config, "a")["appid_env"], "A_ID")
        self.assertEqual(wp.get_account(config, "b")["appid_env"], "B_ID")
        with self.assertRaises(wp.PublishError):
            wp.get_account(config, "c")

    def test_html_images_are_uploaded_once_per_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = os.path.join(tmp, "cover.png")
            with open(image_path, "wb") as f:
                f.write(self.PNG_1X1)
            html_path = os.path.join(tmp, "article.html")
            html = (
                '<section><img src="cover.png"><img src="cover.png">'
                '<img src="https://mmbiz.qpic.cn/already.jpg"></section>'
            )
            client = FakeClient()
            result, uploaded, skipped = wp.upload_html_images(html, html_path, client)
        self.assertEqual(len(client.uploads), 1)
        self.assertEqual(len(uploaded), 1)
        self.assertEqual(skipped, 0)
        self.assertEqual(result.count("https://mmbiz.qpic.cn/uploaded/cover.png"), 2)
        self.assertIn("https://mmbiz.qpic.cn/already.jpg", result)

    def test_html_local_images_cannot_escape_html_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_dir = os.path.join(tmp, "article")
            os.makedirs(article_dir)
            outside = os.path.join(tmp, "outside.png")
            with open(outside, "wb") as f:
                f.write(self.PNG_1X1)
            html_path = os.path.join(article_dir, "article.html")
            client = FakeClient()
            with self.assertRaisesRegex(wp.PublishError, "目录|越界"):
                wp.upload_html_images(
                    '<section><img src="../outside.png"></section>', html_path, client
                )
            link = os.path.join(article_dir, "linked.png")
            os.symlink(outside, link)
            with self.assertRaisesRegex(wp.PublishError, "目录|越界"):
                wp.upload_html_images(
                    '<section><img src="linked.png"></section>', html_path, client
                )

    def test_multipart_contains_file_and_content_type(self):
        body, boundary = wp.multipart_body("media", "a.jpg", b"abc", "image/jpeg")
        self.assertTrue(boundary.startswith("----wechat-skill-"))
        self.assertIn(boundary.encode(), body)
        self.assertIn(b'filename="a.jpg"', body)
        self.assertIn(b"Content-Type: image/jpeg", body)
        self.assertIn(b"abc", body)

    def test_dry_run_needs_no_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "article.html")
            cover_path = os.path.join(tmp, "cover.png")
            with open(cover_path, "wb") as f:
                f.write(self.PNG_1X1)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write('<section><p><span leaf="">正文。</span></p></section>')
            args = Namespace(
                account="a", html=html_path, title="标题", strict=True,
                dry_run=True, action="publish", cover=cover_path,
                author=None, digest=None, source_url=None, no_token_cache=False,
                wait_seconds=0, result_file=None,
            )
            config = {
                "accounts": {
                    "a": {"appid_env": "MISSING_ID", "secret_env": "MISSING_SECRET"}
                }
            }
            output = io.StringIO()
            with mock.patch.object(
                wp.urllib.request, "urlopen", side_effect=AssertionError("network called")
            ), mock.patch.object(
                wp, "WeChatClient", side_effect=AssertionError("client constructed")
            ), contextlib.redirect_stdout(output):
                wp.cmd_send(config, args)
            result = json.loads(output.getvalue())
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["account"], "a")
        self.assertEqual(result["action"], "publish")

    def test_dry_run_skips_missing_local_content_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "article.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write('<section><img src="missing.png"></section>')
            args = Namespace(
                account="a", html=html_path, title="标题", strict=False,
                dry_run=True, action="draft", cover=None,
                author=None, digest=None, source_url=None, no_token_cache=False,
                wait_seconds=0, result_file=None,
            )
            config = {"accounts": {"a": {
                "appid_env": "MISSING_ID", "secret_env": "MISSING_SECRET",
                "default_thumb_media_id": "configured-thumb",
            }}}
            with contextlib.redirect_stdout(io.StringIO()):
                wp.cmd_send(config, args)

    def test_dry_run_skips_fake_image_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "article.html")
            image_path = os.path.join(tmp, "fake.png")
            with open(image_path, "wb") as f:
                f.write(b"not-a-real-png")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write('<section><img src="fake.png"></section>')
            args = Namespace(
                account="a", html=html_path, title="标题", strict=False,
                dry_run=True, action="draft", cover=None,
                author=None, digest=None, source_url=None, no_token_cache=False,
                wait_seconds=0, result_file=None,
            )
            config = {"accounts": {"a": {
                "appid_env": "MISSING_ID", "secret_env": "MISSING_SECRET",
                "default_thumb_media_id": "configured-thumb",
            }}}
            with contextlib.redirect_stdout(io.StringIO()):
                wp.cmd_send(config, args)

    def test_read_image_rejects_truncated_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "truncated.png")
            with open(path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")
            with self.assertRaisesRegex(wp.PublishError, "图片内容格式"):
                wp.read_image(path, tmp, allow_outside=True)

    def test_content_image_uses_actual_format_when_extension_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mismatch.jpg")
            with open(path, "wb") as f:
                f.write(self.PNG_1X1)
            filename, _, content_type = wp.read_image(
                path, tmp, allow_outside=True, strict_declared=False
            )
        self.assertEqual("mismatch.png", filename)
        self.assertEqual("image/png", content_type)

    def test_read_image_default_strict_still_rejects_mismatched_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mismatch.jpg")
            with open(path, "wb") as f:
                f.write(self.PNG_1X1)
            with self.assertRaisesRegex(wp.PublishError, "格式.*不一致"):
                wp.read_image(path, tmp, allow_outside=True)

    def test_cover_accepts_real_bytes_with_wrong_extension(self):
        """cover.png 内含 PNG 之外的合法字节时按真实格式规范化上传（对齐 ai-cover-generation 契约）。"""

        class CoverClient(FakeClient):
            def upload_cover(self, filename, data, content_type):
                self.uploads.append((filename, data, content_type))
                return "thumb-media-id"

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cover.jpg")  # 扩展名 jpg，内容 PNG
            with open(path, "wb") as f:
                f.write(self.PNG_1X1)
            client = CoverClient()
            args = Namespace(cover=path)
            thumb = wp.resolve_thumb({}, args, client)
        self.assertEqual("thumb-media-id", thumb)
        filename, _, content_type = client.uploads[0]
        self.assertEqual("cover.png", filename)
        self.assertEqual("image/png", content_type)

    def test_bad_content_image_is_removed_but_good_image_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "good.png"), "wb") as f:
                f.write(self.PNG_1X1)
            with open(os.path.join(tmp, "bad.png"), "wb") as f:
                f.write(b"not-an-image")
            client = FakeClient()
            html, uploaded, skipped = wp.upload_html_images(
                '<section><img src="good.png"><img src="bad.png"></section>',
                os.path.join(tmp, "article.html"), client,
            )
        self.assertEqual(1, len(uploaded))
        self.assertEqual(1, skipped)
        self.assertNotIn("bad.png", html)

    def test_read_image_rejects_truncated_gif(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "truncated.gif")
            with open(path, "wb") as f:
                f.write(b"GIF89a\x01\x00\x01\x00\x80\x00\x00")
            with self.assertRaisesRegex(wp.PublishError, "图片内容格式"):
                wp.read_image(path, tmp, allow_outside=True)

    def test_read_image_rejects_webp_without_image_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "truncated.webp")
            with open(path, "wb") as f:
                f.write(b"RIFF\x04\x00\x00\x00WEBP")
            with self.assertRaisesRegex(wp.PublishError, "图片内容格式"):
                wp.read_image(path, tmp)

    @unittest.skipIf(wp.Image is None, "缺 Pillow 时解码校验降级为 magic bytes，壳样本无法识别")
    def test_read_image_rejects_undecodable_format_shells(self):
        png_shell = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\x00IHDR"
            b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
        )
        samples = {
            "broken.png": png_shell,
            "broken.jpg": b"\xff\xd8\xff\xd9",
            "broken.gif": b"GIF89a" + b"\x00" * 7 + b",;",
            "broken.webp": b"RIFF" + (12).to_bytes(4, "little") + b"WEBPVP8 " + b"\x00" * 4,
        }
        for filename, data in samples.items():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, filename)
                with open(path, "wb") as f:
                    f.write(data)
                with self.assertRaisesRegex(wp.PublishError, "图片内容格式"):
                    wp.read_image(path, tmp)

    def test_read_image_degrades_to_magic_bytes_when_decoder_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "valid.png")
            with open(path, "wb") as f:
                f.write(self.PNG_1X1)
            with mock.patch.object(wp, "Image", None):
                with self.assertWarnsRegex(RuntimeWarning, "缺少 Pillow"):
                    filename, data, detected_type = wp.read_image(path, tmp)
                self.assertEqual(detected_type, "image/png")
                self.assertEqual(filename, "valid.png")

    def test_read_image_rejects_local_image_over_20_mib(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "huge.png")
            with open(path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")
                f.write(b"x" * (20 * 1024 * 1024))
                f.write(b"\x00\x00\x00\x00IEND\xaeB`\x82")
            with self.assertRaisesRegex(wp.PublishError, "超过 20 MiB"):
                wp.read_image(path, tmp, allow_outside=True)

    def test_publish_ready_rejects_unresolved_placeholder(self):
        with self.assertRaises(wp.PublishError):
            wp.validate_publish_ready(
                '<section><p><span leaf="">我是 {{作者名}}。</span></p></section>'
            )

    def test_write_result_persists_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_path = os.path.join(tmp, "result.json")
            with contextlib.redirect_stdout(io.StringIO()):
                wp.write_result({"draft_media_id": "draft-1"}, result_path)
            with open(result_path, encoding="utf-8") as f:
                saved = json.load(f)
        self.assertEqual(saved["draft_media_id"], "draft-1")

    def test_publish_existing_draft_does_not_create_another_draft(self):
        class ExistingDraftClient:
            def publish(self, media_id):
                self.media_id = media_id
                return {"publish_id": "publish-1"}

            def publish_status(self, publish_id):
                return {"publish_status": 0, "article_id": "article-1"}

        client = ExistingDraftClient()
        args = Namespace(
            account="a", media_id="draft-1", wait_seconds=1,
            no_token_cache=True, result_file=None,
        )
        config = {
            "accounts": {
                "a": {"appid_env": "A_ID", "secret_env": "A_SECRET"}
            }
        }
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"A_ID": "appid", "A_SECRET": "secret"}), \
                mock.patch.object(wp, "WeChatClient", return_value=client), \
                contextlib.redirect_stdout(output):
            wp.cmd_publish(config, args)
        result = json.loads(output.getvalue())
        self.assertEqual(client.media_id, "draft-1")
        self.assertEqual(result["publish_id"], "publish-1")


if __name__ == "__main__":
    unittest.main()


class DraftUpdateTests(unittest.TestCase):
    """就地改写草稿：改一个标题不该在草稿箱里多留一篇。

    这里锁两件容易搞错的事：
    1. 微信 `draft/update` 的 articles 是**单个对象**，不是 add 那样的数组。传错
       不会报语法错，会静默改坏内容。
    2. send 和 update 必须共用同一条 article 拼装路径。分叉过一次就会出现
       「更新后评论区悄悄关了」这类只有事后才发现的问题。
    """

    def make_client(self, response=None):
        client = wp.WeChatClient("id", "secret")
        calls = []

        def fake_request(method, path, payload=None, headers=None,
                         authenticated=True, may_mutate=False):
            calls.append({"method": method, "path": path, "payload": payload,
                          "may_mutate": may_mutate})
            return response if response is not None else {"errcode": 0}

        client._request = fake_request
        return client, calls

    def test_update_posts_a_single_article_object(self):
        client, calls = self.make_client()
        result = client.update_draft("MID", {"title": "新标题"}, index=0)
        self.assertEqual(result, {"media_id": "MID", "index": 0})
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["path"], "/cgi-bin/draft/update")
        self.assertEqual(call["payload"]["media_id"], "MID")
        self.assertEqual(call["payload"]["index"], 0)
        self.assertIsInstance(call["payload"]["articles"], dict)
        self.assertTrue(call["may_mutate"])

    def test_update_raises_on_errcode(self):
        client, _ = self.make_client({"errcode": 40007, "errmsg": "invalid media_id"})
        with self.assertRaises(wp.PublishError):
            client.update_draft("MID", {"title": "x"})

    def test_send_and_update_build_identical_articles(self):
        account = {
            "default_author": "作者", "default_digest": "默认摘要",
            "default_source_url": "https://example.com",
            "need_open_comment": 1, "only_fans_can_comment": 0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "article.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write("<section><p>正文</p></section>")
            args = Namespace(html=html_path, title="标题", author=None, digest=None,
                             source_url=None, cover=None)
            client = FakeClient()
            with mock.patch.object(wp, "resolve_thumb", return_value="THUMB"):
                article, _, _ = wp.build_article(
                    account, client, args, "<section><p>正文</p></section>")
        self.assertEqual(article["author"], "作者")
        self.assertEqual(article["digest"], "默认摘要")
        self.assertEqual(article["thumb_media_id"], "THUMB")
        self.assertEqual(article["need_open_comment"], 1)

    def test_update_subcommand_is_wired(self):
        args = wp.build_parser().parse_args([
            "update", "--account", "a", "--media-id", "MID",
            "--html", "x.html", "--title", "T",
        ])
        self.assertEqual(args.command, "update")
        self.assertEqual(args.index, 0)
