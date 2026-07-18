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
            image_path = os.path.join(tmp, "cover.jpg")
            with open(image_path, "wb") as f:
                f.write(b"jpeg-data")
            html_path = os.path.join(tmp, "article.html")
            html = (
                '<section><img src="cover.jpg"><img src="cover.jpg">'
                '<img src="https://mmbiz.qpic.cn/already.jpg"></section>'
            )
            client = FakeClient()
            result, uploaded = wp.upload_html_images(html, html_path, client)
        self.assertEqual(len(client.uploads), 1)
        self.assertEqual(len(uploaded), 1)
        self.assertEqual(result.count("https://mmbiz.qpic.cn/uploaded/cover.jpg"), 2)
        self.assertIn("https://mmbiz.qpic.cn/already.jpg", result)

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
            with open(html_path, "w", encoding="utf-8") as f:
                f.write('<section><p><span leaf="">正文。</span></p></section>')
            args = Namespace(
                account="a", html=html_path, title="标题", strict=True,
                dry_run=True, action="publish", cover="cover.jpg",
                author=None, digest=None, source_url=None, no_token_cache=False,
                wait_seconds=0, result_file=None,
            )
            config = {
                "accounts": {
                    "a": {"appid_env": "MISSING_ID", "secret_env": "MISSING_SECRET"}
                }
            }
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                wp.cmd_send(config, args)
            result = json.loads(output.getvalue())
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["account"], "a")
        self.assertEqual(result["action"], "publish")

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
