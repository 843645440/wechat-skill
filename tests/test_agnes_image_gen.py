import base64
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".agents/skills/agnes-image-gen/scripts/generate.py"
)
SPEC = importlib.util.spec_from_file_location("agnes_image_generate", SCRIPT)
agnes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agnes)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class AgnesImageGenTests(unittest.TestCase):
    def test_wechat_cover_ratio_maps_to_supported_ratio(self):
        self.assertEqual(agnes.normalize_ratio("2.35:1"), "21:9")
        self.assertEqual(agnes.normalize_ratio("16:9"), "16:9")
        with self.assertRaises(agnes.AgnesError):
            agnes.normalize_ratio("5:4")

    def test_text_to_image_requests_base64(self):
        payload = agnes.build_payload("model", "prompt", "2K", "16:9", [])
        self.assertTrue(payload["return_base64"])
        self.assertNotIn("extra_body", payload)

    def test_image_to_image_uses_extra_body(self):
        payload = agnes.build_payload(
            "model", "prompt", "2K", "16:9", ["data:image/png;base64,abc"]
        )
        self.assertEqual(payload["extra_body"]["response_format"], "b64_json")
        self.assertEqual(len(payload["extra_body"]["image"]), 1)
        self.assertNotIn("return_base64", payload)

    def test_local_reference_becomes_data_uri(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ref.png"
            path.write_bytes(PNG_1X1)
            value = agnes.reference_value(str(path))
        self.assertTrue(value.startswith("data:image/png;base64,"))

    def test_base64_response_is_written_atomically(self):
        response = {"data": [{"b64_json": base64.b64encode(PNG_1X1).decode()}]}
        data, source = agnes.response_image(response, 10)
        with tempfile.TemporaryDirectory() as directory:
            output, fmt = agnes.write_image(Path(directory) / "output.png", data)
            self.assertEqual(output.read_bytes(), PNG_1X1)
        self.assertEqual(source, "base64")
        self.assertEqual(fmt, "png")

    def test_dry_run_requires_configured_key_without_exposing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "prompt.md"
            prompt.write_text("A clean editorial illustration", encoding="utf-8")
            args = SimpleNamespace(
                prompt_file=str(prompt),
                output=str(Path(directory) / "output.png"),
                size="2K",
                ratio="2.35:1",
                ref=[],
                timeout=180,
                dry_run=True,
            )
            with mock.patch.dict(os.environ, {"AGNES_API_KEY": "test-only-key"}, clear=False):
                result = agnes.run(args)
        self.assertTrue(result["api_key_configured"])
        self.assertEqual(result["ratio"], "21:9")
        self.assertNotIn("test-only-key", str(result))


if __name__ == "__main__":
    unittest.main()
