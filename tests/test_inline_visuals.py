import importlib.util
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    ROOT,
    ".agents",
    "skills",
    "wechat-inline-visuals",
    "scripts",
    "validate_plan.py",
)
SPEC = importlib.util.spec_from_file_location("validate_inline_plan", SCRIPT)
validate_inline_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_inline_plan)


ARTICLE = """# AI 进入客服之后，工作为什么没有变轻

## 效率提高之后，压力转移给了谁

企业节省的是流程时间，但员工承担了新的复核责任。

一线客服减少了重复查询，技术主管需要重新划分工具权限。

## 真正昂贵的是流程改造

模型价格下降，不等于接入成本自然消失。
"""

THEMES = {
    "moyu-green",
    "red-white",
    "moyu-ticket",
    "olive-journal",
}


def insight_plan():
    return {
        "version": 1,
        "theme": "olive-journal",
        "modules": [
            {
                "id": "inline-01",
                "kind": "insight",
                "title": "效率提高之后，压力转移给了谁",
                "placement": {
                    "after_heading": "效率提高之后，压力转移给了谁",
                    "after_text": "企业节省的是流程时间，但员工承担了新的复核责任。",
                },
                "evidence": [
                    "企业节省的是流程时间，但员工承担了新的复核责任。",
                    "一线客服减少了重复查询，技术主管需要重新划分工具权限。",
                ],
                "items": [
                    {"label": "一线客服", "text": "重复查询减少，但复核责任增加"},
                    {"label": "技术主管", "text": "需要重新划分工具权限和责任"},
                ],
            }
        ],
    }


class InlineVisualPlanTests(unittest.TestCase):
    def test_valid_plan_keeps_theme_and_counts_modules(self):
        result = validate_inline_plan.validate_plan(insight_plan(), ARTICLE, THEMES)
        self.assertEqual(result["theme"], "olive-journal")
        self.assertEqual(result["module_count"], 1)
        self.assertEqual(result["kinds"], ["insight"])

    def test_empty_plan_is_valid(self):
        result = validate_inline_plan.validate_plan(
            {"version": 1, "theme": "moyu-green", "modules": []},
            ARTICLE,
            THEMES,
        )
        self.assertEqual(result["module_count"], 0)

    def test_rejects_evidence_not_present_in_article(self):
        plan = insight_plan()
        plan["modules"][0]["evidence"] = ["并不存在的采访结论。"]
        with self.assertRaisesRegex(validate_inline_plan.PlanError, "证据不是文章原文"):
            validate_inline_plan.validate_plan(plan, ARTICLE, THEMES)

    def test_rejects_metric_value_not_present_in_article(self):
        plan = {
            "version": 1,
            "theme": "red-white",
            "modules": [
                {
                    "id": "inline-01",
                    "kind": "metrics",
                    "title": "部署结果",
                    "placement": {
                        "after_heading": "真正昂贵的是流程改造",
                        "after_text": "模型价格下降，不等于接入成本自然消失。",
                    },
                    "evidence": ["模型价格下降，不等于接入成本自然消失。"],
                    "metrics": [
                        {"value": "37%", "label": "时间下降", "note": "指定测试场景"},
                        {"value": "3个月", "label": "观察周期", "note": "不是长期预测"},
                    ],
                }
            ],
        }
        with self.assertRaisesRegex(validate_inline_plan.PlanError, "指标值不是文章原文"):
            validate_inline_plan.validate_plan(plan, ARTICLE, THEMES)

    def test_cli_fixture_is_json_serializable(self):
        json.dumps(insight_plan(), ensure_ascii=False)

    def test_cli_can_degrade_invalid_plan_to_empty_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            article = Path(tmp) / "article.md"
            plan = Path(tmp) / "inline-visuals.json"
            index = Path(tmp) / "theme-index.md"
            article.write_text(ARTICLE, encoding="utf-8")
            plan.write_text("{invalid", encoding="utf-8")
            index.write_text(
                "## 已注册主题\n`references/theme-moyu-green.md`\n", encoding="utf-8"
            )
            original = os.sys.argv
            output = io.StringIO()
            try:
                os.sys.argv = [
                    "validate_plan.py", "--plan", str(plan), "--article", str(article),
                    "--theme-index", str(index), "--degrade-on-error",
                    "--fallback-theme", "moyu-green",
                ]
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, validate_inline_plan.main())
            finally:
                os.sys.argv = original
            result = json.loads(output.getvalue())
            self.assertIs(result["degraded"], True)
            self.assertEqual([], json.loads(plan.read_text(encoding="utf-8"))["modules"])


if __name__ == "__main__":
    unittest.main()
