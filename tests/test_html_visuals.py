import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/wechat-html-visuals/scripts/render_visual.py"
CSS = ROOT / ".agents/skills/wechat-html-visuals/assets/visual.css"
SPEC = importlib.util.spec_from_file_location("wechat_html_visuals", SCRIPT)
visuals = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(visuals)


class HtmlVisualTests(unittest.TestCase):
    def fixture(self, name):
        path = ROOT / "tests/fixtures" / name
        return json.loads(path.read_text(encoding="utf-8"))

    def test_cover_is_escaped_and_self_contained(self):
        raw = self.fixture("html-visual-cover.json")
        raw["title"] = "模型 < 价格，价值 > 参数"
        spec = visuals.validate_spec(raw)
        rendered = visuals.render_html(spec, CSS.read_text(encoding="utf-8"))
        self.assertIn("模型 &lt; 价格，价值 &gt; 参数", rendered)
        self.assertNotIn("<script", rendered)
        self.assertNotIn("https://", rendered)
        self.assertIn("--canvas-width:1410px", rendered)

    def test_process_numbers_are_generated_by_template(self):
        spec = visuals.validate_spec(self.fixture("html-visual-process.json"))
        rendered = visuals.render_body(spec)
        for number in range(1, 6):
            self.assertEqual(rendered.count(f'>{number}</div>'), 1)
        self.assertNotIn("ZONES", rendered)

    def test_unknown_and_too_long_fields_fail_before_render(self):
        raw = self.fixture("html-visual-cover.json")
        raw["random_text"] = "should fail"
        with self.assertRaises(visuals.VisualError):
            visuals.validate_spec(raw)
        raw = self.fixture("html-visual-cover.json")
        raw["title"] = "长" * 29
        with self.assertRaises(visuals.VisualError):
            visuals.validate_spec(raw)

    def test_png_dimensions_reads_ihdr(self):
        header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 1200, 800)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            path.write_bytes(header)
            self.assertEqual(visuals.png_dimensions(path), (1200, 800))

    def test_comparison_footer_is_not_duplicated(self):
        raw = {
            "kind": "comparison",
            "theme": "indigo",
            "title": "演示与部署的差距",
            "left": {"heading": "演示阶段", "items": ["任务边界清楚", "环境经过筛选"]},
            "right": {"heading": "生产环境", "items": ["输入经常变化", "责任必须可追溯"]},
            "footer": "部署能力决定最终体验",
        }
        rendered = visuals.render_body(visuals.validate_spec(raw))
        self.assertEqual(rendered.count("部署能力决定最终体验"), 1)


if __name__ == "__main__":
    unittest.main()
