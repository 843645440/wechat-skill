import importlib.util
import contextlib
import html
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDERER_PATH = os.path.join(
    ROOT, ".agents", "skills", "wechat-content-pipeline", "scripts", "render_article.py"
)
VALIDATOR_PATH = os.path.join(ROOT, "scripts", "validate_gzh_html.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = load_module("wechat_article_renderer", RENDERER_PATH)
validator = load_module("wechat_html_validator", VALIDATOR_PATH)


ARTICLE = """# 谷歌把代码执行接进研究工具，教师先面对核验责任

研究工具能够运行代码之后，最先变化的不是论文结论，而是资料整理和结果复核的方式。

## 工具进入真实流程

教师可以减少重复整理时间，但需要确认**代码、数据和引用是否可靠**。

学生得到更快的分析反馈，学校技术人员则要重新划分权限。

## 效率提高之后

公开测试显示处理时间缩短了30%，观察周期为3个月。
"""


def plan_for(kind, theme):
    common = {
        "id": "inline-01",
        "kind": kind,
        "title": "工具进入流程后的变化",
        "placement": {
            "after_heading": "工具进入真实流程",
            "after_text": "教师可以减少重复整理时间，但需要确认代码、数据和引用是否可靠。",
        },
        "evidence": ["教师可以减少重复整理时间，但需要确认代码、数据和引用是否可靠。"],
    }
    if kind == "insight":
        common["items"] = [
            {"label": "教师", "text": "减少整理时间，增加核验责任"},
            {"label": "技术人员", "text": "重新划分工具权限"},
        ]
    elif kind == "comparison":
        common["left"] = {"heading": "得到便利", "items": ["减少重复整理", "反馈速度提高"]}
        common["right"] = {"heading": "承担成本", "items": ["核验代码结果", "管理使用权限"]}
    elif kind == "process":
        common["steps"] = [
            {"label": "收集", "text": "整理公开资料"},
            {"label": "执行", "text": "运行分析代码"},
            {"label": "复核", "text": "核对数据引用"},
        ]
    else:
        common["placement"] = {
            "after_heading": "效率提高之后",
            "after_text": "公开测试显示处理时间缩短了30%，观察周期为3个月。",
        }
        common["evidence"] = ["公开测试显示处理时间缩短了30%，观察周期为3个月。"]
        common["metrics"] = [
            {"value": "30%", "label": "时间缩短", "note": "公开测试场景"},
            {"value": "3个月", "label": "观察周期", "note": "不代表长期结果"},
        ]
    return {"version": 1, "theme": theme, "modules": [common]}


class ArticleRendererTests(unittest.TestCase):
    def test_all_themes_render_all_module_kinds(self):
        _, sections = renderer.parse_article(ARTICLE)
        labels = {
            "insight": "KEY INSIGHTS",
            "comparison": "SIDE BY SIDE",
            "process": "WORKFLOW",
            "metrics": "DATA POINTS",
        }
        for theme_name, theme in renderer.THEMES.items():
            for kind in ("insight", "comparison", "process", "metrics"):
                with self.subTest(theme=theme_name, kind=kind):
                    output = renderer.render_document(
                        "测试标题", sections, plan_for(kind, theme_name), theme
                    )
                    errors, warnings, leaf_count = validator.validate(output)
                    self.assertEqual([], errors)
                    self.assertEqual([], warnings)
                    self.assertGreater(leaf_count, 10)
                    self.assertIn(labels[kind], output)

    def test_every_theme_ends_with_a_follow_cta(self):
        """涨关注的留存钩子：所有主题文末必须有在看/转发/关注引导，且仍然合规。"""
        _, sections = renderer.parse_article(ARTICLE)
        for theme_name, theme in renderer.THEMES.items():
            with self.subTest(theme=theme_name):
                output = renderer.render_document(
                    "测试标题", sections,
                    {"version": 1, "theme": theme_name, "modules": []}, theme,
                )
                errors, warnings, _ = validator.validate(output)
                self.assertEqual([], errors)
                self.assertEqual([], warnings)
                for token in ("写在最后", "在看", "转发", "关注", "星标"):
                    self.assertIn(token, output)
                cta = output[output.index("写在最后"):]
                self.assertIn(theme["accent"], cta[:900])
                self.assertNotIn("<span leaf=\"\"><span", cta[:900])

    def test_follow_cta_sits_between_body_and_end_marker(self):
        _, sections = renderer.parse_article(ARTICLE)
        theme = renderer.THEMES["red-white"]
        output = renderer.render_document(
            "测试标题", sections,
            {"version": 1, "theme": "red-white", "modules": []}, theme,
        )
        self.assertLess(output.index("写在最后"), output.rindex(">END<"))

    def test_each_theme_uses_a_distinct_rich_component_system(self):
        _, sections = renderer.parse_article(ARTICLE)
        expected = {
            "moyu-green": ("TECH INSIGHT", "linear-gradient", "PART 01"),
            "red-white": ("本文看点", "background:#DC2626", "WORKFLOW"),
            "moyu-ticket": ("VALID FOR ONE READ", "END OF TICKET", "NO. 001"),
            "olive-journal": ("EDITORIAL NOTE", "END NOTE", "PART"),
        }
        for theme_name, tokens in expected.items():
            with self.subTest(theme=theme_name):
                output = renderer.render_document(
                    "测试标题", sections,
                    {"version": 1, "theme": theme_name, "modules": []},
                    renderer.THEMES[theme_name],
                )
                for token in tokens:
                    self.assertIn(token, output)
                self.assertGreater(output.count("<section"), 8)

    def test_semantic_markdown_table_and_highlight_render_in_all_themes(self):
        article = """# 三家企业公布模型价格，采购人员先核对口径

同样写着百万 Token，**输入与输出价格并不相同**。

## 公开价格不能只看一个数字

| 企业 | 输入价格 | 输出价格 |
|---|---:|---:|
| 甲公司 | 2元 | 8元 |
| 乙公司 | 3元 | 9元 |
| 丙公司 | 4元 | 12元 |
"""
        _, sections = renderer.parse_article(article)
        self.assertEqual("table", sections[-1]["blocks"][-1]["kind"])
        for theme_name, theme in renderer.THEMES.items():
            with self.subTest(theme=theme_name):
                output = renderer.render_document(
                    "测试标题", sections,
                    {"version": 1, "theme": theme_name, "modules": []}, theme,
                )
                errors, warnings, _ = validator.validate(output)
                self.assertEqual([], errors)
                self.assertEqual([], warnings)
                self.assertIn("<table", output)
                self.assertIn("丙公司", output)
                self.assertIn(theme["underline"], output)

    def test_fenced_code_block_preserves_literals_and_indentation_in_all_themes(self):
        article = """# 代码块测试标题

正文说明。

## 代码示例

```python
def f(x):
    if x == 1:
        return "**not bold**"
    return x + 1
```

代码块之后的正文。
"""
        _, sections = renderer.parse_article(article)
        code_blocks = [
            block for section in sections for block in section["blocks"]
            if block["kind"] == "code"
        ]
        self.assertEqual(1, len(code_blocks))
        self.assertEqual("python", code_blocks[0]["lang"])
        self.assertIn('    if x == 1:', code_blocks[0]["code"])
        for theme_name, theme in renderer.THEMES.items():
            with self.subTest(theme=theme_name):
                output = renderer.render_document(
                    "测试标题", sections,
                    {"version": 1, "theme": theme_name, "modules": []}, theme,
                )
                errors, warnings, _ = validator.validate(output)
                self.assertEqual([], errors)
                self.assertEqual([], warnings)
                self.assertIn('if x == 1:', output)
                self.assertIn('**not bold**', output)
                # indentation is locked in as &nbsp;, not literal spaces
                self.assertIn('&nbsp;&nbsp;&nbsp;&nbsp;if x == 1:', output)
                self.assertIn('&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
                              'return &quot;**not bold**&quot;', output)

    def test_unclosed_code_fence_does_not_raise_and_captures_rest_of_file(self):
        article = """# 未闭合代码块测试标题

正文说明。

```bash
echo "hello"
echo "world"
"""
        _, sections = renderer.parse_article(article)
        code_blocks = [
            block for section in sections for block in section["blocks"]
            if block["kind"] == "code"
        ]
        self.assertEqual(1, len(code_blocks))
        self.assertEqual("bash", code_blocks[0]["lang"])
        self.assertIn('echo "hello"', code_blocks[0]["code"])
        self.assertIn('echo "world"', code_blocks[0]["code"])
        output = renderer.render_document(
            "测试标题", sections,
            {"version": 1, "theme": "moyu-green", "modules": []},
            renderer.THEMES["moyu-green"],
        )
        errors, warnings, _ = validator.validate(output)
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_markdown_image_renders_as_wechat_image_block(self):
        article = """# 正文图测试标题

说明文字。

![流程示意](imgs/workflow.png)
"""
        _, sections = renderer.parse_article(article)
        self.assertEqual("image", sections[-1]["blocks"][-1]["kind"])
        output = renderer.render_document("正文图测试标题", sections, renderer.THEMES["moyu-green"])
        errors, warnings, _ = validator.validate(output)
        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        self.assertIn('<img src="imgs/workflow.png"', output)
        self.assertIn('alt="流程示意"', output)

    def test_plain_text_preserves_literal_operators_and_cpp(self):
        value = "C++ 是语言，a == b，邮箱 a++b@example.com"
        self.assertEqual(value, renderer.plain_text(value))

    def test_parse_rejects_missing_title(self):
        with self.assertRaisesRegex(renderer.RenderError, "一级标题"):
            renderer.parse_article("只有正文。")

    def test_render_keeps_every_source_paragraph(self):
        _, sections = renderer.parse_article(ARTICLE)
        output = renderer.render_document(
            "测试标题",
            sections,
            {"version": 1, "theme": "moyu-green", "modules": []},
            renderer.THEMES["moyu-green"],
        )
        text_only = html.unescape(re.sub(r"<[^>]+>", "", output))
        for section in sections:
            for block in section["blocks"]:
                values = block.get("items", [block.get("text", "")])
                for value in values:
                    self.assertIn(value, text_only)


if __name__ == "__main__":
    unittest.main()
