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
                # 从 CTA 容器的 <section 开头切，而不是从「写在最后」切：
                # 有的主题（如 color-block）把主题色用在容器背景上，
                # 那段声明位于「写在最后」之前，从文案处切会漏掉。
                label_at = output.index("写在最后")
                cta = output[output.rindex("<section", 0, label_at):]
                self.assertIn(theme["accent"], cta[:1200])
                self.assertNotIn("<span leaf=\"\"><span", cta[:1200])

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
            # 低噪音 / 强母题组
            "plain-white": ("本文看点", "font-size:34px", "letter-spacing:-1px"),
            "ink-rule": ("本文看点", "Songti SC", "background:#111111"),
            "deep-pool": ("DEEP DIVE", "background:#16202B", "#6FBCC9"),
            "color-block": ("DEEP DIVE", "background:#1B5E8C", "color:#1B5E8C"),
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


class ThemeContrastTests(unittest.TestCase):
    """主题色的可读性回归。

    加主题最容易犯的错是「为了淡而淡」：muted 压到 3:1 以下，
    结果 hero 引言和小标签在手机上根本看不清。这里用 WCAG
    相对亮度把它卡死。深色 hero 的组合同样要查，否则会出现
    深字压深底（accent 压 dark 只有 3.47:1 就是这么发现的）。
    """

    SMALL_TEXT = {"body", "muted", "darkbody"}   # 正文级，需 4.5:1
    PAIRS_ON_PAPER = (("body", "paper"), ("muted", "paper"), ("ink", "paper"))
    PAIRS_ON_DARK = (("darkink", "dark"), ("darkbody", "dark"), ("ondark", "dark"))
    PAIRS_ON_BLOCK = (("blockink", "block"),)

    @staticmethod
    def _luminance(value):
        value = value.lstrip("#")
        if len(value) == 8:          # 带 alpha 的写法，只取 RGB
            value = value[:6]
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                  for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    @classmethod
    def _ratio(cls, foreground, background):
        a, b = cls._luminance(foreground), cls._luminance(background)
        high, low = max(a, b), min(a, b)
        return (high + 0.05) / (low + 0.05)

    def test_every_theme_meets_contrast_floor(self):
        for name, theme in renderer.THEMES.items():
            pairs = list(self.PAIRS_ON_PAPER)
            if "dark" in theme:
                pairs += list(self.PAIRS_ON_DARK)
            if "block" in theme:
                pairs += list(self.PAIRS_ON_BLOCK)
            for foreground, background in pairs:
                if foreground not in theme or background not in theme:
                    continue
                with self.subTest(theme=name, pair=f"{foreground}/{background}"):
                    floor = 4.5 if foreground in self.SMALL_TEXT else 3.0
                    ratio = self._ratio(theme[foreground], theme[background])
                    self.assertGreaterEqual(
                        round(ratio, 2), floor,
                        f"{name} 的 {foreground} 压在 {background} 上只有 "
                        f"{ratio:.2f}:1，低于 {floor}:1",
                    )

    def test_required_theme_keys_present(self):
        """缺键会在渲染时才 KeyError，这里提前拦住。"""
        required = {"layout", "name", "paper", "ink", "body", "muted",
                    "accent", "soft", "line", "underline", "radius", "shadow"}
        for name, theme in renderer.THEMES.items():
            with self.subTest(theme=name):
                self.assertEqual(set(), required - set(theme))

    def test_dark_layouts_declare_their_on_dark_colors(self):
        """深色 layout 必须自带 dark 系色值，不能退回浅色主题色。"""
        for name, theme in renderer.THEMES.items():
            if theme["layout"] == "darkhero":
                with self.subTest(theme=name):
                    for key in ("dark", "darkink", "darkbody", "ondark"):
                        self.assertIn(key, theme)
            if theme["layout"] == "colorblock":
                with self.subTest(theme=name):
                    for key in ("block", "blockink"):
                        self.assertIn(key, theme)


if __name__ == "__main__":
    unittest.main()
