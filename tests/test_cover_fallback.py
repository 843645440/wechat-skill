import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    ROOT, ".agents", "skills", "wechat-content-pipeline", "scripts",
    "render_cover_fallback.py",
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fallback = load_module("cover_fallback", SCRIPT)

try:
    fallback.resolve_font()
    HAS_FONT = True
except fallback.RenderError:
    HAS_FONT = False


def run(*args):
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, check=False,
    )
    return result.returncode, json.loads(result.stdout.strip().splitlines()[-1])


class CoverFallbackTest(unittest.TestCase):
    """离线封面兜底：无生图 API、无浏览器时保证 finish 不被封面阻塞。"""

    def test_hex_and_mix(self):
        self.assertEqual(fallback.hex_to_rgb("#FF7A45"), (255, 122, 69))
        self.assertEqual(fallback.mix((0, 0, 0), (100, 200, 50), 0.5), (50, 100, 25))
        with self.assertRaises(fallback.RenderError):
            fallback.hex_to_rgb("#FFF")

    def test_palette_is_deterministic_per_seed(self):
        first = fallback.pick_palette("run-abc", "")
        again = fallback.pick_palette("run-abc", "")
        other = fallback.pick_palette("run-xyz", "")
        self.assertEqual(first, again)
        self.assertIn(other["accent"], [p["accent"] for p in fallback.PALETTES])

    def test_accent_override_wins(self):
        palette = fallback.pick_palette("run-abc", "#123456")
        self.assertEqual(palette["accent"], "#123456")

    def test_split_highlight_marks_only_requested_spans(self):
        spans = fallback.split_highlight("法院判赔26万", ["26万"])
        self.assertEqual(spans, [("法院判赔", False), ("26万", True)])
        self.assertEqual(
            fallback.split_highlight("无强调", []), [("无强调", False)]
        )

    def test_missing_output_is_rejected(self):
        code, payload = run("--title", "标题")
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "error")

    def test_unknown_ratio_is_rejected(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--title", "标题", "--ratio", "5:4", "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    @unittest.skipUnless(HAS_FONT, "运行环境没有可渲染中文的字体")
    def test_dry_run_reports_font_without_writing(self):
        code, payload = run("--title", "测试封面", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["dry_run"])
        self.assertTrue(os.path.isfile(payload["font"]))

    @unittest.skipUnless(HAS_FONT, "运行环境没有可渲染中文的字体")
    def test_renders_png_with_expected_size_and_magic(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "cover", "cover.png")
            code, payload = run(
                "--title", "「这活AI能干」|法院判赔26万",
                "--highlight", "26万",
                "--subtitle", "两地法院给出同一条线",
                "--kicker", "熵增时刻",
                "--seed", "run-1",
                "--output", out,
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual((payload["width"], payload["height"]), (1440, 810))
            self.assertEqual(payload["title_lines"], ["「这活AI能干」", "法院判赔26万"])
            data = Path(out).read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(len(data), 4096)

    @unittest.skipUnless(HAS_FONT, "运行环境没有可渲染中文的字体")
    def test_same_seed_gives_identical_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = os.path.join(tmp, "a.png")
            second = os.path.join(tmp, "b.png")
            for out in (first, second):
                code, _ = run("--title", "确定性封面", "--seed", "fixed", "--output", out)
                self.assertEqual(code, 0)
            self.assertEqual(Path(first).read_bytes(), Path(second).read_bytes())

    @unittest.skipUnless(HAS_FONT, "运行环境没有可渲染中文的字体")
    def test_long_title_wraps_within_max_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "c.png")
            code, payload = run(
                "--title", "这是一个非常非常长的封面标题" * 4,
                "--max-lines", "3",
                "--output", out,
            )
            self.assertEqual(code, 0, payload)
            self.assertLessEqual(len(payload["title_lines"]), 3)

    @unittest.skipUnless(HAS_FONT, "运行环境没有可渲染中文的字体")
    def test_ratio_maps_to_documented_canvas(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "d.png")
            code, payload = run(
                "--title", "比例", "--ratio", "2.35:1", "--output", out
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual((payload["width"], payload["height"]), (1410, 600))

    def test_font_error_names_the_env_override(self):
        original = fallback.FONT_CANDIDATES
        fallback.FONT_CANDIDATES = [("/nonexistent/font.ttc", 0)]
        try:
            with self.assertRaises(fallback.RenderError) as ctx:
                fallback.resolve_font()
            self.assertIn("WECHAT_COVER_FONT", str(ctx.exception))
        finally:
            fallback.FONT_CANDIDATES = original


if __name__ == "__main__":
    unittest.main()
