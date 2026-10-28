import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = load("ordered_list_renderer", ".agents/skills/wechat-content-pipeline/scripts/render_article.py")
validator = load("ordered_list_validator", "scripts/validate_gzh_html.py")


class OrderedListTests(unittest.TestCase):
    def blocks(self, body):
        _, sections = renderer.parse_article("# 操作说明\n\n" + body)
        return [block for section in sections for block in section["blocks"]]

    def test_consecutive_steps_are_separate_items(self):
        steps = [f"步骤{number}核对范围。" for number in range(1, 8)]
        blocks = self.blocks("\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)))
        self.assertEqual(["list"], [block["kind"] for block in blocks])
        self.assertEqual(steps, blocks[0]["items"])

    def test_ordered_list_stops_at_paragraph_and_heading(self):
        blocks = self.blocks("开头说明。\n\n1. 第一项。\n2. 第二项。\n\n后续说明。\n\n## 验收\n\n3. 第三项。")
        self.assertEqual(["paragraph", "list", "paragraph", "list"], [b["kind"] for b in blocks])
        self.assertEqual(["第一项。", "第二项。"], blocks[1]["items"])
        self.assertEqual(["第三项。"], blocks[3]["items"])

    def test_decimals_dates_and_inline_numbers_stay_in_paragraphs(self):
        body = "1.5 秒完成。\n\n2026.10.28 检查。\n\n第 1. 项是正文中的数字。"
        blocks = self.blocks(body)
        self.assertEqual(["paragraph"] * 3, [b["kind"] for b in blocks])

    def test_unordered_lists_and_code_are_unchanged(self):
        blocks = self.blocks("- 第一项。\n* 第二项。\n+ 第三项。\n\n```text\n1. 代码内不是列表\n```\n")
        self.assertEqual(["list", "code"], [b["kind"] for b in blocks])
        self.assertEqual(["第一项。", "第二项。", "第三项。"], blocks[0]["items"])
        self.assertEqual("1. 代码内不是列表", blocks[1]["code"])

    def test_emphasis_and_all_theme_validation(self):
        title, sections = renderer.parse_article("# 操作说明\n\n1. **核对范围**。\n2. 检查 `HTML`。\n")
        for theme_name, theme in renderer.THEMES.items():
            with self.subTest(theme=theme_name):
                output = renderer.render_document(title, sections, theme)
                errors, warnings, _ = validator.validate(output)
                self.assertEqual([], errors)
                self.assertEqual([], warnings)
                self.assertIn('>01</span>', output)
                self.assertIn('>02</span>', output)
                self.assertNotIn('1. **', output)


if __name__ == "__main__":
    unittest.main()
