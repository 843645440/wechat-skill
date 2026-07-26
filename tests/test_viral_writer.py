"""wechat-viral-writer：体检打分与热点雷达。

这两个脚本的价值全在「判得准不准」上，所以测试锁的不是「能跑通」，而是：

1. **区分度**：满分样例必须过线，典型的「新闻汇报腔」必须被拦下。一个所有稿子
   都给 90 分的体检脚本比没有体检更糟——它会让模型确信自己写得很好。
2. **不误伤**：清单里的多个加粗、结尾在倒数第三段回扣开头，这些是好写法，
   不能被判成问题。早期版本两条都误伤过。
3. **开关是真的开关**：热点雷达在配置关闭时必须一次网络请求都不发。
4. **降级**：单个榜单失败不能拖垮整轮，退出码恒为 0。
"""

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, ".agents", "skills", "wechat-viral-writer")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scorer = load_module("score_draft", os.path.join(SKILL, "scripts", "score_draft.py"))
radar = load_module("hot_radar", os.path.join(SKILL, "scripts", "hot_radar.py"))

GOLD = Path(SKILL) / "examples" / "gold-sample.md"
CONFIG = Path(SKILL) / "config" / "writer-config.json"


def score(article, thresholds=None):
    return scorer.analyze(article, thresholds or dict(scorer.THRESHOLDS))


def problems_in(result, dim):
    return [p for p in result["problems"] if p["dim"] == dim]


# ------------------------------------------------------------------ 打分

class ScoreCalibrationTests(unittest.TestCase):
    """区分度：好稿和差稿必须分得开，否则这个脚本没有存在意义。"""

    def test_gold_sample_passes(self):
        result = score(GOLD.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["blocking_count"], 0)
        self.assertGreaterEqual(result["score"], 85)
        self.assertEqual(result["grade"], "A")

    def test_report_style_draft_fails(self):
        """无加粗、无小标题、无利他物、长段落——典型的「新闻汇报腔」。"""
        body = (
            "某公司近日宣布将推出新的产品线，该产品将面向企业客户提供服务，"
            "相关负责人表示这一举措有助于提升整体效率并推动行业发展，"
            "业内人士认为这是一个值得关注的方向，未来还需要观察实际落地情况。"
        ) * 8
        article = f"# 某公司推出新产品线，行业迎来新的变化\n\n{body}\n"
        result = score(article)
        self.assertEqual(result["status"], "fix")
        self.assertGreater(result["blocking_count"], 0)
        self.assertLess(result["score"], 70)

    def test_gold_beats_report_style_by_a_wide_margin(self):
        gold = score(GOLD.read_text(encoding="utf-8"))["score"]
        weak = score("# 关于行业发展的几点思考\n\n" + "这是一段没有信息的话。" * 60)["score"]
        self.assertGreater(gold - weak, 25)


class EdgeCaseTests(unittest.TestCase):
    """畸形输入不能崩，也不能给出一个看起来「还行」的假分数。"""

    def test_empty_body_scores_zero_not_forty(self):
        for article in ("", "# 只有标题\n", "# 标题\n\n![图](imgs/1.png)\n",
                        "# 标题\n\n```python\nprint(1)\n```\n"):
            with self.subTest(article=article[:12]):
                result = score(article)
                self.assertEqual(result["score"], 0.0)
                self.assertEqual(result["blocking_count"], 1)
                self.assertEqual(result["body_chars"], 0)

    def test_no_title_is_reported(self):
        found = problems_in(score("没有一级标题的正文内容。\n"), "hook")
        self.assertTrue(any("没有一级标题" in p["what"] for p in found))

    def test_very_long_article_does_not_crash(self):
        result = score("# 标题\n\n" + "很长的一段话。" * 3000)
        self.assertEqual(result["status"], "fix")
        self.assertGreater(result["body_chars"], 20000)

    def test_quote_and_list_blocks_parse(self):
        result = score("# 标题\n\n> 引用一段话。\n\n- 清单一\n- 清单二\n")
        self.assertIsInstance(result["score"], float)


class HookTests(unittest.TestCase):
    def test_long_title_is_blocking(self):
        result = score("# " + "很" * 40 + "\n\n正文。\n")
        found = problems_in(result, "hook")
        self.assertTrue(any("超过 32 字" in p["what"] for p in found))
        self.assertTrue(any(p["severity"] == "high" for p in found))

    def test_cliche_opener_is_blocking(self):
        article = (
            "# 三行代码会直接 400，该不该升\n\n"
            "在当今人工智能飞速发展的时代，我们每个人都感受到了变化。\n"
        )
        found = problems_in(score(article), "hook")
        self.assertTrue(any("套话铺垫" in p["what"] for p in found))

    def test_title_without_sting_is_flagged(self):
        article = "# 某公司发布新版本产品并同步开放接口\n\n正文内容在这里。\n"
        found = problems_in(score(article), "hook")
        self.assertTrue(any("没有锚点" in p["what"] for p in found))

    def test_number_in_title_counts_as_sting(self):
        article = "# 贵一倍不等于更强，2 个模型怎么选\n\n正文内容在这里。\n"
        found = problems_in(score(article), "hook")
        self.assertFalse(any("没有锚点" in p["what"] for p in found))

    def test_latin_brand_alone_is_not_a_sting(self):
        """标题里出现 Google Cloud 是名词，不是刺点——这条曾经判反过。"""
        article = "# Google Cloud 与 Intel 达成新的技术合作\n\n正文内容。\n"
        found = problems_in(score(article), "hook")
        self.assertTrue(any("没有锚点" in p["what"] for p in found))


class TitleRankingTests(unittest.TestCase):
    """标题是整条漏斗最窄的闸门，所以它有独立的排序模式（写正文之前用）。"""

    def rank(self, *titles):
        return scorer.rank_titles(list(titles), dict(scorer.THRESHOLDS))

    def test_sting_title_beats_bulletin_title(self):
        result = self.rank(
            "英特尔把Gemini引入芯片研发，工程师先面对责任重分配",
            "别急着上多智能体，先算这三笔账",
        )
        self.assertEqual(result["best"], "别急着上多智能体，先算这三笔账")
        self.assertEqual(result["status"], "ok")

    def test_weekly_report_tone_is_penalised(self):
        [item] = self.rank("关于公众号写作的几点思考")["ranked"]
        self.assertLess(item["score"], 60)
        self.assertTrue(any("周报腔" in n for n in item["notes"]))

    def test_late_sting_is_penalised_but_recognised(self):
        [item] = self.rank("一套写给内容团队的完整方法论，能省下三成返工")["ranked"]
        self.assertTrue(item["late_stings"])
        self.assertFalse(item["stings"])
        self.assertTrue(any("后半截" in n for n in item["notes"]))

    def test_same_sting_kind_across_candidates_is_called_out(self):
        result = self.rank("3 个理由", "5 分钟搞定", "10 倍效率")
        self.assertTrue(any("同一类刺点" in a for a in result["advice"]))

    def test_fewer_than_three_candidates_is_called_out(self):
        self.assertTrue(any("少于 3 个" in a for a in self.rank("别急着上")["advice"]))

    def test_overlong_title_loses_points(self):
        long_title = ("别急着上多智能体，先算这三笔账，否则你会在三个月之后"
                      "收到一张多出四成的云账单")
        short = self.rank("别急着上多智能体，先算这三笔账")["ranked"][0]["score"]
        self.assertGreater(len(long_title), scorer.THRESHOLDS["title_max"])
        self.assertLess(self.rank(long_title)["ranked"][0]["score"], short)

    def test_cli_titles_mode_needs_no_article(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = scorer.main(["--titles", "别急着上，先算这三笔账"])
        self.assertEqual(code, 0)
        self.assertIn("ranked", json.loads(output.getvalue()))

    def test_cli_without_article_or_titles_errors(self):
        with self.assertRaises(SystemExit):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                scorer.main([])


class ValueDensityTests(unittest.TestCase):
    def test_long_gap_without_anchor_is_reported(self):
        article = "# 别急着上，先算这三笔账\n\n" + "这是一段完全没有具体信息的话。" * 40
        found = problems_in(score(article), "value_density")
        self.assertTrue(any("没有具体信息" in p["what"] for p in found))

    def test_latin_proper_noun_counts_as_anchor(self):
        """「英特尔用 Google Cloud 补算力」是有信息的，不该被判成空段。"""
        stream = "英特尔宣布使用 Google Cloud 补充本地算力"
        hits = scorer.marker_positions(stream, scorer.ANCHOR_PATTERNS)
        self.assertTrue(hits)

    def test_bold_and_heading_count_as_anchors(self):
        blocks = scorer.parse_blocks(
            "# 标题\n\n## 这是一句结论式小标题\n\n这段有一个**关键判断**在里面。\n"
        )
        _, _, offsets = scorer.body_stream(blocks)
        self.assertEqual(len(scorer.structural_anchors(blocks, offsets)), 2)

    def test_filler_words_are_penalised(self):
        article = (
            "# 别急着上，先算这三笔账\n\n"
            + "众所周知，这件事毫无疑问是重要的。不难看出，在一定程度上总而言之。" * 8
        )
        found = problems_in(score(article), "value_density")
        self.assertTrue(any("注水词" in p["what"] for p in found))

    def test_repeated_paragraph_is_reported(self):
        para = ("这个配置错了不会报错，你会在三个月后收到一张多出四成的账单，"
                "而那时候谁也说不清是哪一次改动引入的问题。\n")
        article = f"# 配置错了不报错，三个月后才收到账单\n\n{para}\n{para}\n"
        found = problems_in(score(article), "value_density")
        self.assertTrue(any("重复度" in p["what"] for p in found))


class ReaderBenefitTests(unittest.TestCase):
    def test_no_takeaway_is_blocking(self):
        article = "# 这件事的来龙去脉\n\n" + "事情是这样发生的，然后又变成了那样。" * 30
        found = problems_in(score(article), "reader_benefit")
        self.assertTrue(any(p["severity"] == "high" for p in found))
        self.assertTrue(any("带走" in p["what"] for p in found))

    def test_checklist_registers_as_benefit(self):
        article = (
            "# 三条今晚就能用的检查\n\n"
            "先说结论。\n\n"
            "- **第一步**：把标题前 16 个字单独拎出来看\n"
            "- **判断标准**：什么情况选 A，什么情况选 B\n"
            "- **前提是**：团队超过 5 个人，否则别抄\n\n"
            "如果你是新手，就从第一条开始。\n"
        )
        result = score(article)
        self.assertFalse(
            any(p["severity"] == "high" for p in problems_in(result, "reader_benefit"))
        )


class ReadabilityTests(unittest.TestCase):
    def test_huge_paragraph_is_blocking(self):
        article = "# 别急着上，先算这三笔账\n\n" + "这段话很长而且一直不换行。" * 25 + "\n"
        found = problems_in(score(article), "readability")
        self.assertTrue(any(p["severity"] == "high" for p in found))

    def test_list_block_is_exempt_from_bold_cap(self):
        """清单每条都加粗是正常写法，不该被判成「加粗过多」。"""
        article = (
            "# 四种利他物，按题材选\n\n"
            "- **判断标准**：什么情况选 A\n"
            "- **适用边界**：什么时候失效\n"
            "- **可执行步骤**：今晚做什么\n"
            "- **可转述结论**：一句话\n"
        )
        found = problems_in(score(article), "readability")
        self.assertFalse(any("加粗超过" in p["what"] for p in found))

    def test_missing_headings_reported_for_long_body(self):
        article = "# 别急着上，先算这三笔账\n\n" + ("一段合理长度的正文内容。\n\n" * 90)
        found = problems_in(score(article), "readability")
        self.assertTrue(any("小标题" in p["what"] for p in found))


class RetentionTests(unittest.TestCase):
    def test_flat_stretch_is_reported(self):
        article = "# 别急着上，先算这三笔账\n\n" + "这是一句平铺直叙的陈述句。" * 60
        found = problems_in(score(article), "retention")
        self.assertTrue(any("平铺直叙" in p["what"] for p in found))

    def test_callback_uses_ngram_recall_not_keyword_chunks(self):
        """正则「提词」会把中文切成无意义碎片，导致任何文章都判成没回扣。"""
        opener = "昨天我把五篇旧稿丢进体检脚本"
        self.assertGreater(radar_free_recall(opener, "回到那五篇旧稿"), 0.2)
        self.assertLess(radar_free_recall(opener, "完全无关的另一段文字内容"), 0.08)


def radar_free_recall(opener, closer):
    return scorer.recall_overlap(opener, closer)


class ScorerIOTests(unittest.TestCase):
    def test_missing_file_returns_json_and_exit_zero(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = scorer.main(["--article", "/nonexistent/article.md"])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "fix")
        self.assertEqual(payload["problems"][0]["dim"], "input")

    def test_config_overrides_thresholds(self):
        thresholds = scorer.load_thresholds(str(CONFIG))
        self.assertEqual(thresholds["pass_score"], 75)
        self.assertEqual(thresholds["anchor_gap_max"], 300)

    def test_config_ignores_unknown_and_non_numeric_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps(
                {"scoring": {"pass_score": 60, "nope": 1, "anchor_gap_max": "x"}}),
                encoding="utf-8")
            thresholds = scorer.load_thresholds(str(path))
        self.assertEqual(thresholds["pass_score"], 60)
        self.assertNotIn("nope", thresholds)
        self.assertEqual(thresholds["anchor_gap_max"], 300)

    def test_markdown_output_renders(self):
        output = io.StringIO()
        with redirect_stdout(output):
            scorer.main(["--article", str(GOLD), "--markdown"])
        text = output.getvalue()
        self.assertIn("稿件体检", text)
        self.assertIn("| 维度 | 得分 | 观测 |", text)

    def test_out_file_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "report.json"
            with redirect_stdout(io.StringIO()):
                scorer.main(["--article", str(GOLD), "--out", str(target)])
            payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["grade"], "A")


# ------------------------------------------------------------------ 雷达

class RadarSwitchTests(unittest.TestCase):
    def test_disabled_by_default_and_makes_no_request(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertFalse(config["hot_topic_radar"]["enabled"],
                         "热点雷达必须默认关闭")
        args = radar.build_parser().parse_args(["--config", str(CONFIG)])
        with mock.patch.object(radar, "fetch",
                               side_effect=AssertionError("关闭时不许联网")):
            result = radar.run(config, args)
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["how_to_enable"])

    def test_force_bypasses_switch_without_touching_config(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        args = radar.build_parser().parse_args(
            ["--config", str(CONFIG), "--force", "--top", "3"])
        with mock.patch.object(radar, "pull_source", side_effect=fake_puller):
            result = radar.run(config, args)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(
            json.loads(CONFIG.read_text(encoding="utf-8"))["hot_topic_radar"]["enabled"],
            "--force 不得回写配置",
        )


FAKE_BOARDS = {
    "微博热搜": ["长鑫上市 合肥能赚多少", "某明星塌房", "AI 客服全面上线"],
    "百度热搜": ["长鑫科技上市 合肥赚多少", "某地天气", "AI 客服上线引发争议"],
    "36氪": ["9点1氪｜今日要闻汇总", "某公司完成融资", "另一家公司完成融资"],
}


def fake_puller(spec, timeout):
    name = spec.get("name")
    if name not in FAKE_BOARDS:
        return {"name": name, "ok": False, "count": 0, "error": "mock: 未配置"}
    return {"name": name, "ok": True, "count": len(FAKE_BOARDS[name]),
            "items": FAKE_BOARDS[name], "weight": float(spec.get("weight", 1.0)),
            "ranked": spec.get("kind", "json") != "rss"}


class RadarRankingTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.args = radar.build_parser().parse_args(
            ["--config", str(CONFIG), "--force", "--top", "10"])

    def run_radar(self):
        with mock.patch.object(radar, "pull_source", side_effect=fake_puller):
            return radar.run(self.config, self.args)

    def test_cross_board_topic_ranks_first(self):
        result = self.run_radar()
        top = result["candidates"][0]
        self.assertIn("长鑫", top["title"])
        self.assertEqual(len(top["sources"]), 2)

    def test_excluded_keywords_are_dropped(self):
        titles = " ".join(c["title"] for c in self.run_radar()["candidates"])
        self.assertNotIn("塌房", titles)
        self.assertNotIn("9点1氪", titles)

    def test_failed_source_does_not_kill_the_run(self):
        result = self.run_radar()
        self.assertTrue(result["failed_sources"])
        self.assertEqual(result["status"], "ok")

    def test_max_per_source_caps_single_board_domination(self):
        self.config["hot_topic_radar"]["max_per_source"] = 1
        self.config["hot_topic_radar"]["min_score"] = 0
        counts = {}
        for item in self.run_radar()["candidates"]:
            if len(item["sources"]) == 1:
                counts[item["sources"][0]] = counts.get(item["sources"][0], 0) + 1
        self.assertTrue(all(n <= 1 for n in counts.values()), counts)

    def test_every_candidate_carries_angles(self):
        for item in self.run_radar()["candidates"]:
            self.assertEqual(len(item["angles"]), 3)


class RadarParserTests(unittest.TestCase):
    def test_json_parser_walks_dotted_path(self):
        payload = json.dumps({"data": {"realtime": [{"word": "甲"}, {"word": "乙"}]}})
        items = radar.parse_json_source(
            payload, {"path": "data.realtime", "title_field": "word"})
        self.assertEqual(items, ["甲", "乙"])

    def test_json_parser_walks_nested_title_field(self):
        payload = json.dumps({"data": [{"target": {"title": "丙"}}]})
        items = radar.parse_json_source(
            payload, {"path": "data", "title_field": "target.title"})
        self.assertEqual(items, ["丙"])

    def test_json_parser_rejects_wrong_path(self):
        with self.assertRaises(ValueError):
            radar.parse_json_source(json.dumps({"data": 1}), {"path": "data"})

    def test_rss_parser_reads_titles(self):
        xml = ("<rss><channel><item><title>第一条</title></item>"
               "<item><title>第二条</title></item></channel></rss>")
        self.assertEqual(radar.parse_rss_source(xml, {}), ["第一条", "第二条"])

    def test_baidu_parser_reads_embedded_json(self):
        payload = json.dumps({"data": {"cards": [
            {"content": [{"query": "热点甲"}, {"word": "热点乙"}]}]}})
        html = f"<html><!--s-data:{payload}--></html>"
        self.assertEqual(radar.parse_baidu_source(html, {}), ["热点甲", "热点乙"])

    def test_html_tags_are_stripped_from_titles(self):
        self.assertEqual(radar.clean_title("<b>标题</b>&nbsp;后半"), "标题 后半")

    def test_unknown_kind_reports_instead_of_raising(self):
        result = radar.pull_source({"name": "x", "kind": "csv", "url": "u"}, 1)
        self.assertFalse(result["ok"])
        self.assertIn("未知 kind", result["error"])

    def test_network_failure_is_captured_not_raised(self):
        with mock.patch.object(radar, "fetch", side_effect=OSError("boom")):
            result = radar.pull_source(
                {"name": "x", "kind": "json", "url": "u", "path": ""}, 1)
        self.assertFalse(result["ok"])
        self.assertIn("网络失败", result["error"])

    def test_source_headers_are_passed_through(self):
        """微博接口没有 Referer 会 403，站点差异必须能在配置里表达。"""
        seen = {}

        def spy(url, timeout, extra_headers=None):
            seen["headers"] = extra_headers
            return json.dumps([{"title": "甲"}])

        with mock.patch.object(radar, "fetch", side_effect=spy):
            radar.pull_source({"name": "x", "kind": "json", "url": "u", "path": "",
                               "headers": {"Referer": "https://weibo.com/"}}, 1)
        self.assertEqual(seen["headers"], {"Referer": "https://weibo.com/"})


class RadarOutputTests(unittest.TestCase):
    def test_markdown_for_disabled_explains_the_switch(self):
        text = radar.render_markdown({
            "status": "disabled", "reason": "关着", "candidates": [],
            "how_to_enable": ["改配置", "加 --force"],
        })
        self.assertIn("未开启", text)
        self.assertIn("--force", text)

    def test_main_exits_zero_even_when_run_explodes(self):
        output = io.StringIO()
        with mock.patch.object(radar, "run", side_effect=RuntimeError("boom")):
            with redirect_stdout(output):
                code = radar.main(["--config", str(CONFIG)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "failed")

    def test_empty_result_tells_the_writer_not_to_force_it(self):
        text = radar.render_markdown({
            "status": "empty", "sources": [], "failed_sources": [],
            "total_entries": 0, "candidates": [],
        })
        self.assertIn("不要硬写", text)


if __name__ == "__main__":
    unittest.main()
