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
            "template": "redaction-poster",
            "theme": "olive-journal",
            "eyebrow": "AI 与产业观察",
            "title": "模型变便宜之后，真正昂贵的是什么",
            "title_lines": ["模型变便宜之后，", "真正昂贵的是什么"],
            "highlights": ["模型"],
            "subtitle": "企业竞争正在从参数转向工作流程",
        }

    def test_validate_spec_accepts_registered_theme(self):
        result = render_html_cover.validate_spec(self.spec())
        self.assertEqual(result["theme"], "olive-journal")
        self.assertEqual(result["template"], "redaction-poster")

    def test_validate_spec_accepts_all_templates(self):
        for template in render_html_cover.TEMPLATES:
            spec = self.spec()
            spec["template"] = template
            if template != "redaction-poster":
                spec["highlights"] = []
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
        invalid["highlights"] = ["真正昂贵"]
        with self.assertRaisesRegex(render_html_cover.CoverError, "高亮词必须位于标题第一行"):
            render_html_cover.validate_spec(invalid)

    def test_render_html_escapes_text_and_has_no_remote_assets(self):
        spec = self.spec()
        spec["subtitle"] = "流程 < 口号 & 演示"
        validated = render_html_cover.validate_spec(spec)
        output = render_html_cover.render_html(validated, "body{margin:0}")
        self.assertIn("流程 &lt; 口号 &amp; 演示", output)
        self.assertIn("template-redaction-poster", output)
        self.assertIn("redaction-title-highlight", output)
        self.assertNotIn("https://", output)
        self.assertNotIn("<script", output)

    def test_all_template_title_pairs_meet_contrast_floor(self):
        for template in render_html_cover.TEMPLATES:
            with self.subTest(template=template):
                render_html_cover.validate_template_contrast(template)

    def test_title_css_uses_one_uninterrupted_surface_per_template(self):
        css = Path(
            ROOT,
            ".agents",
            "skills",
            "wechat-html-cover",
            "assets",
            "cover.css",
        ).read_text(encoding="utf-8")
        self.assertIn("font-size: var(--title-size)", css)
        self.assertNotIn("text-stroke", css)
        for selector in (".signal-title", ".night-title", ".redaction-title"):
            self.assertRegex(css, rf"(?s){selector}\s*\{{[^}}]*width:")

    def test_templates_render_separate_structures(self):
        expected = {
            "signal-editorial": "signal-blue-rail",
            "night-signal": "night-orange-long",
            "redaction-poster": "redaction-panel",
        }
        for template, marker in expected.items():
            spec = self.spec()
            spec["template"] = template
            if template != "redaction-poster":
                spec["highlights"] = []
            output = render_html_cover.render_html(
                render_html_cover.validate_spec(spec),
                "body{margin:0}",
            )
            self.assertIn(f"template-{template}", output)
            self.assertIn(marker, output)

    def test_dom_probe_rejects_browser_error_page(self):
        with self.assertRaisesRegex(render_html_cover.CoverError, "错误页"):
            render_html_cover.validate_dumped_dom(
                "<html><body>ERR_ACCESS_DENIED</body></html>"
            )

    def test_dom_probe_accepts_expected_cover_structure_and_title(self):
        render_html_cover.validate_dumped_dom(
            '<html><main class="canvas template-night-signal">'
            '<h1 class="cover-title">真实标题</h1></main></html>'
        )

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

    def test_find_browser_preserves_launcher_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            launcher = directory / "chromium"
            target = directory / "snap"
            target.write_text("#!/bin/sh\n", encoding="utf-8")
            target.chmod(0o755)
            launcher.symlink_to(target)
            self.assertEqual(launcher, render_html_cover.find_browser(launcher))

    def test_screenshot_stages_browser_output_outside_hidden_worktree(self):
        captured = {}
        target = Path.home() / ".hermes" / "work" / "cover.png"
        source = Path(tempfile.mkstemp(suffix=".html")[1])
        source.write_text("<html></html>", encoding="utf-8")

        class Process:
            pid = 123

            def poll(self):
                return 0

        original_popen = render_html_cover.subprocess.Popen
        original_dimensions = render_html_cover.png_dimensions
        original_replace = render_html_cover.os.replace
        original_probe = render_html_cover.probe_dom

        def fake_popen(command, **kwargs):
            screenshot_arg = next(item for item in command if item.startswith("--screenshot="))
            captured["browser_output"] = Path(screenshot_arg.split("=", 1)[1])
            captured["browser_output"].write_bytes(b"png")
            return Process()

        def fake_dimensions(path):
            return (render_html_cover.WIDTH, render_html_cover.HEIGHT)

        def fake_replace(source, destination):
            captured["replace"] = (Path(source), Path(destination))

        try:
            render_html_cover.subprocess.Popen = fake_popen
            render_html_cover.png_dimensions = fake_dimensions
            render_html_cover.os.replace = fake_replace
            render_html_cover.probe_dom = lambda *args: None
            render_html_cover.screenshot(
                Path("/usr/bin/chromium"),
                source,
                target,
                1,
            )
        finally:
            source.unlink(missing_ok=True)
            render_html_cover.subprocess.Popen = original_popen
            render_html_cover.png_dimensions = original_dimensions
            render_html_cover.os.replace = original_replace
            render_html_cover.probe_dom = original_probe

        self.assertIn(Path.home() / "wechat-cover-tmp", captured["browser_output"].parents)
        self.assertNotIn(Path.home() / ".hermes", captured["browser_output"].parents)
        self.assertEqual((captured["browser_output"], target), captured["replace"])

    def test_screenshot_checks_output_once_more_after_browser_exit(self):
        captured = {}
        target = Path.home() / ".hermes" / "work" / "cover.png"
        source = Path(tempfile.mkstemp(suffix=".html")[1])
        source.write_text("<html></html>", encoding="utf-8")

        class Process:
            pid = 123

            def poll(self):
                if "browser_output" in captured:
                    captured["browser_output"].write_bytes(b"png")
                return 0

        original_popen = render_html_cover.subprocess.Popen
        original_dimensions = render_html_cover.png_dimensions
        original_replace = render_html_cover.os.replace
        original_probe = render_html_cover.probe_dom

        def fake_popen(command, **kwargs):
            screenshot_arg = next(item for item in command if item.startswith("--screenshot="))
            captured["browser_output"] = Path(screenshot_arg.split("=", 1)[1])
            return Process()

        try:
            render_html_cover.subprocess.Popen = fake_popen
            render_html_cover.png_dimensions = lambda path: (
                render_html_cover.WIDTH,
                render_html_cover.HEIGHT,
            )
            render_html_cover.os.replace = lambda source, destination: captured.update(
                replace=(Path(source), Path(destination))
            )
            render_html_cover.probe_dom = lambda *args: None
            render_html_cover.screenshot(
                Path("/usr/bin/chromium"),
                source,
                target,
                1,
            )
        finally:
            source.unlink(missing_ok=True)
            render_html_cover.subprocess.Popen = original_popen
            render_html_cover.png_dimensions = original_dimensions
            render_html_cover.os.replace = original_replace
            render_html_cover.probe_dom = original_probe

        self.assertEqual((captured["browser_output"], target), captured["replace"])

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
                    self.assertIn(len(result["title_lines"]), (2, 3))
                    if template != "redaction-poster":
                        self.assertEqual([], result["highlights"])

    def test_long_title_uses_three_lines_and_safe_estimated_width(self):
        title = "这是一个用于验证三十二字中文标题能否完整显示且绝不被装饰遮挡的测试标题"
        title = title[:32]
        lines = build_html_cover_spec.split_title(title)
        self.assertEqual(3, len(lines))
        for template in render_html_cover.TEMPLATES:
            spec = build_html_cover_spec.build_spec(
                title,
                "olive-journal",
                template,
                "科技与产业观察",
                "看见技术变化背后的真实影响",
            )
            size = render_html_cover.title_font_size(spec)
            widest = max(render_html_cover.text_units(line) for line in spec["title_lines"])
            self.assertLessEqual(
                widest * size * 1.08,
                render_html_cover.TITLE_SAFE_WIDTH[template] + 0.01,
            )

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
