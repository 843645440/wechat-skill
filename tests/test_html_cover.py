import importlib.util
import os
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    ROOT,
    ".agents",
    "skills",
    "wechat-html-cover",
    "scripts",
    "render_cover.py",
)
SPEC = importlib.util.spec_from_file_location("render_html_cover", SCRIPT)
render_html_cover = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_html_cover)

BUILDER_SCRIPT = os.path.join(
    ROOT,
    ".agents",
    "skills",
    "wechat-html-cover",
    "scripts",
    "build_cover_spec.py",
)
BUILDER_SPEC = importlib.util.spec_from_file_location("build_html_cover_spec", BUILDER_SCRIPT)
build_html_cover_spec = importlib.util.module_from_spec(BUILDER_SPEC)
BUILDER_SPEC.loader.exec_module(build_html_cover_spec)


class HtmlCoverTests(unittest.TestCase):
    def spec(self):
        return {
            "template": "editorial-ledger",
            "theme": "olive-journal",
            "eyebrow": "AI 与产业观察",
            "title": "模型变便宜之后，真正昂贵的是什么",
            "title_lines": ["模型变便宜之后，", "真正昂贵的是什么"],
            "highlights": ["变便宜", "真正昂贵"],
            "subtitle": "企业竞争正在从参数转向工作流程",
        }

    def test_validate_spec_accepts_registered_theme(self):
        result = render_html_cover.validate_spec(self.spec())
        self.assertEqual(result["theme"], "olive-journal")
        self.assertEqual(result["template"], "editorial-ledger")

    def test_validate_spec_accepts_both_templates(self):
        for template in render_html_cover.TEMPLATES:
            spec = self.spec()
            spec["template"] = template
            self.assertEqual(render_html_cover.validate_spec(spec)["template"], template)

    def test_validate_spec_rejects_unknown_fields_and_theme(self):
        invalid = self.spec()
        invalid["remote_image"] = "https://example.com/image.png"
        with self.assertRaisesRegex(render_html_cover.CoverError, "未知字段"):
            render_html_cover.validate_spec(invalid)
        invalid = self.spec()
        invalid["theme"] = "unknown"
        with self.assertRaisesRegex(render_html_cover.CoverError, "theme 必须是"):
            render_html_cover.validate_spec(invalid)
        invalid = self.spec()
        invalid["template"] = "unknown"
        with self.assertRaisesRegex(render_html_cover.CoverError, "template 必须是"):
            render_html_cover.validate_spec(invalid)

    def test_validate_spec_rejects_title_line_or_highlight_drift(self):
        invalid = self.spec()
        invalid["title_lines"] = ["模型变便宜之后，", "昂贵的是什么"]
        with self.assertRaisesRegex(render_html_cover.CoverError, "title_lines"):
            render_html_cover.validate_spec(invalid)
        invalid = self.spec()
        invalid["highlights"] = ["不存在"]
        with self.assertRaisesRegex(render_html_cover.CoverError, "高亮词不在标题中"):
            render_html_cover.validate_spec(invalid)
        invalid = self.spec()
        invalid["highlights"] = ["真正昂贵", "变便宜"]
        with self.assertRaisesRegex(render_html_cover.CoverError, "第一个高亮词"):
            render_html_cover.validate_spec(invalid)

    def test_render_html_escapes_text_and_has_no_remote_assets(self):
        spec = self.spec()
        spec["subtitle"] = "流程 < 口号 & 演示"
        validated = render_html_cover.validate_spec(spec)
        output = render_html_cover.render_html(validated, "body{margin:0}")
        self.assertIn("流程 &lt; 口号 &amp; 演示", output)
        self.assertIn("template-editorial-ledger", output)
        self.assertIn("ledger-accent-word", output)
        self.assertNotIn("https://", output)
        self.assertNotIn("<script", output)

    def test_kinetic_template_renders_separate_structure(self):
        spec = self.spec()
        spec["template"] = "kinetic-type"
        output = render_html_cover.render_html(
            render_html_cover.validate_spec(spec),
            "body{margin:0}",
        )
        self.assertIn("template-kinetic-type", output)
        self.assertIn("kinetic-title-line-two", output)
        self.assertNotIn("ledger-title", output)

    def test_png_dimensions_reads_ihdr(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cover.png"
            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + b"\x00\x00\x00\x0dIHDR"
                + struct.pack(">II", 1410, 600)
            )
            self.assertEqual(render_html_cover.png_dimensions(path), (1410, 600))

    def test_browser_candidates_include_playwright_linux64_layout(self):
        patterns = []
        original_glob = Path.glob

        def capture_glob(path, pattern):
            patterns.append(pattern)
            return []

        try:
            Path.glob = capture_glob
            list(render_html_cover.browser_candidates())
        finally:
            Path.glob = original_glob

        self.assertIn(
            ".cache/ms-playwright/chromium-*/chrome-linux64/chrome",
            patterns,
        )

    def test_builder_makes_valid_specs_for_stress_test_titles(self):
        titles = [
            "英特尔把Gemini引入芯片研发，工程师先面对责任重分配",
            "NotebookLM更名，Google让研究工具直接运行代码",
            "Google给AI广告加制作标签，广告主的低成本创意开始留痕",
            "FREE Walk外骨骼进医院，治疗师从扶走转向调参",
            "Claude教师版免费开放，Anthropic把AI接进备课流程",
            "WAIC 2026发布300多款新品，职场人先面对任务重分配",
        ]
        for title in titles:
            for template in render_html_cover.TEMPLATES:
                with self.subTest(title=title, template=template):
                    result = build_html_cover_spec.build_spec(
                        title,
                        "olive-journal",
                        template,
                        "科技与产业观察",
                        "看见技术变化背后的真实影响",
                    )
                    self.assertEqual(title, "".join(result["title_lines"]))
                    self.assertTrue(all(len(item) <= 18 for item in result["title_lines"]))
                    if template == "kinetic-type":
                        self.assertEqual([], result["highlights"])

    def test_builder_rejects_title_over_32_characters(self):
        with self.assertRaisesRegex(build_html_cover_spec.BuildError, "超过 32 字"):
            build_html_cover_spec.split_title("这是一个明显超过封面长度限制而且没有任何必要继续延长下去的公众号文章标题")

    def test_auto_template_is_stable_for_same_title(self):
        title = "WAIC 2026发布300多款新品，职场人先面对任务重分配"
        first = build_html_cover_spec.choose_template(title)
        self.assertEqual(first, build_html_cover_spec.choose_template(title))
        self.assertIn(first, render_html_cover.TEMPLATES)


if __name__ == "__main__":
    unittest.main()
