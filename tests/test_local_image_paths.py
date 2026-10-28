import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("image_path_publisher", ROOT / "scripts/wechat_publish.py")
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c02"
    "0000000b4944415478da6364f80f00010501012718e3660000000049454e44ae426082"
)


class LocalImagePathTests(unittest.TestCase):
    def test_absolute_and_relative_local_paths_read_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "图片.png"
            path.write_bytes(PNG)
            for source in (str(path), path.as_posix(), path.name):
                with self.subTest(source=source):
                    self.assertEqual((path.name, PNG, "image/png"), publisher.read_image(source, tmp))

    def test_absolute_outside_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "html"
            os.makedirs(base)
            outside = Path(tmp) / "outside.png"
            outside.write_bytes(PNG)
            with self.assertRaisesRegex(publisher.PublishError, "路径越出"):
                publisher.read_image(str(outside), base)
            self.assertEqual(PNG, publisher.read_image(str(outside), base, allow_outside=True)[1])

    def test_relative_escape_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(publisher.PublishError, "路径越出"):
                publisher.read_image("../outside.png", tmp)

    @unittest.skipUnless(os.name == "nt", "different-drive paths are Windows-specific")
    def test_other_drive_reports_directory_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            drive = Path(tmp).drive.upper()
            other = "Z" if drive != "Z:" else "Y"
            with self.assertRaisesRegex(publisher.PublishError, "路径越出"):
                publisher.read_image(other + ":\\outside.png", tmp)

    def test_non_http_uri_schemes_remain_rejected(self):
        for source in ("file:///tmp/image.png", "ftp://example.com/a.png", "data:image/png;base64,aA==", "javascript:alert(1)"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(publisher.PublishError, "不支持的图片地址"):
                    publisher.read_image(source, str(ROOT))

    def test_https_keeps_download_path(self):
        response = mock.MagicMock()
        response.read.return_value = PNG
        response.headers.get_content_type.return_value = "image/png"
        response.__enter__.return_value = response
        with mock.patch.object(publisher.urllib.request, "urlopen", return_value=response) as opened:
            self.assertEqual(("image.png", PNG, "image/png"), publisher.read_image("https://example.com/image.png", str(ROOT)))
        self.assertEqual("https://example.com/image.png", opened.call_args.args[0].full_url)


if __name__ == "__main__":
    unittest.main()
