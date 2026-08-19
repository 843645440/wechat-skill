import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / ".agents/skills/wechat-content-pipeline/scripts/pipeline_runtime.py"
SPEC = importlib.util.spec_from_file_location("wechat_pipeline_runtime", RUNTIME_PATH)
pipeline_runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline_runtime)


# 一篇结构合法且写作体检能过线的样例正文（约 1700 字）。
# 段落短、有小标题、有加粗、有具体数字、有读者落点、结尾回扣开头。
PASSING_ARTICLE = """# 上线前那道验收，卡了我们三周

上个月这条流水线卡在最后一步，整整三周。

不是模型不会写，也不是接口调不通。**卡住的是一句谁也没写进文档的话**：这份稿子归谁签字。

## 演示跑通不等于可以交付

演示环境里，一条命令就能从选题走到草稿箱。看起来这件事已经做完了。

但真要放进日常流程，问题立刻换了一批。**谁来确认这篇能发**？出了事找谁？
这些问题在演示里根本不存在，因为演示没有后果。

我第一次意识到这个差别，是看到一个 40164 的错误码。那是微信在说：你的 IP 不在白名单。

技术上五分钟就能解决。流程上，它需要一个有权限改配置的人，而那个人当时在休假。

## 文档里写的是流程，实际跑的是人情

我们一开始以为缺的是一份文档。于是写了一份，六页，覆盖了每一步该做什么。

结果没人看。**因为文档回答的是「怎么做」，而卡住的问题是「谁来做」**。

这两个问题看起来只差一个字，实际上差着一整套责任分配。怎么做可以写成清单，
谁来做必须落到具体的人和具体的权限上。

后来我们把那六页删到一页，只留三行：这一步谁执行、谁验收、出问题找谁。
从那之后，同类的卡壳再也没出现过。

## 效率提升的账，要算到人头上

自动化省下来的时间不会凭空消失。

更常见的情况是**交付节奏跟着变快**，同一个人同时在管的任务数从 3 个变成 7 个。
省下的不是工时，是每件事上能分到的注意力。

这里有个反直觉的地方：**流程越自动，人工环节反而越贵**。因为剩下的那几个人工环节，
全是需要判断和担责的环节，没有一个是能靠熟练度加速的。

抽查比例定多少、什么结果必须逐项复核、异常时谁有权暂停——这些都是新增的工作，
而不是被省掉的工作。

## 三条可以直接抄的判断

说点能用的。如果你也在把一条人工流程改成自动流程，先回答这三个问题：

- **谁签字**：自动化产出的东西，最终由谁确认可以发出去
- **什么情况必须停**：把暂停条件写死在脚本里，别指望人临场判断
- **失败之后重跑安不安全**：分不清「没做」和「做了但不知道结果」，就一定会出双份

第三条最容易被忽略。我们踩过一次：一个超时被当成失败重跑，结果草稿箱里躺了两篇。

## 重跑安全，是这里最贵的一条

展开说第三条，因为它的代价最容易被低估。

一次调用失败之后，只有两种可能：**要么根本没执行，要么执行了但结果没读回来**。
这两种情况看起来一模一样——都是一条报错——但处置方式完全相反。

前者可以直接重跑。后者重跑就会出双份。

我们后来的做法是让发布器自己回答这个问题：它明确知道请求有没有发出去，
就把结论写进错误信息里，而不是让调用方去猜错误码的语义。

**判断依据必须来自最清楚状况的那一层**。让上层靠正则去猜下层发生了什么，
是所有重试逻辑里最常见的错法。

## 边界在哪

这套办法有明确的适用范围。

**团队少于 3 个人的时候别抄**。三个人以内，沟通成本本来就低于流程成本，
把判断写成文档反而更慢。

**流程还在频繁变的时候也别抄**。固化一个还没稳定的流程，等于把返工提前。

## 先改配置，再改代码

顺序也很重要。

我们最初的本能是写脚本：既然人工环节慢，就把它自动化掉。但那三周里真正起作用的，
是一次五分钟的配置修改——**把「谁验收」这件事从口头约定变成一个字段**。

代码解决的是「怎么执行」，配置解决的是「按谁的意思执行」。当卡点在后者的时候，
再多的代码只会把错误的默认值执行得更快。

一个便宜的检验方法：把你打算写的那个脚本，先用一句话描述它替代了谁的哪个判断。
描述不出来，说明这个判断本来就还没人做过，那就先去把判断定下来。

**没有人做过的判断，自动化不了。**这句话我们花了三周才真正接受。

## 回到那三周

那三周最后是怎么解决的？我们没有优化任何一行代码。

我们只是在配置文件里加了一个字段，写清楚这个账号的稿子由谁验收。

**能被写下来的责任，就能被交接。**真正拖慢一件事的，往往不是它有多难，
而是没人说清楚它归谁。

所以下次卡住的时候，先别急着找技术方案。先问一句：这一步，谁签字。
"""


class PipelineRuntimeTests(unittest.TestCase):
    def make_job(self, tmp, topic="测试主题"):
        job_dir = Path(tmp) / "a/current"
        (job_dir / "cover").mkdir(parents=True)
        created = pipeline_runtime.pipeline_job.now_iso()
        stages = {
            name: pipeline_runtime.pipeline_job.stage_record()
            for name in pipeline_runtime.pipeline_job.STAGES
        }
        stages["discover"] = pipeline_runtime.pipeline_job.stage_record(
            "completed", created, "使用测试主题", {"source": "provided"}
        )
        job = {
            "schema_version": 5,
            "created_at": created,
            "updated_at": created,
            "project_root": str(ROOT),
            "profiles_path": str(ROOT / "config/wechat-content-profiles.json"),
            "job_dir": str(job_dir),
            "account": "a",
            "run_id": "run-test-1",
            "topic": topic,
            "event_focus": "测试主题发生了一个需要解释的核心变化",
            "topic_source": "provided",
            "article_shape": {
                "structure_id": "conflict",
                "opening_type": "contrast",
                "ending_type": "hook_return",
                "felt_sense": "发紧",
                "tension_type": "efficiency_vs_duty",
                "heading_count": 5,
                "body_band": "short",
            },
            "state": "initialized",
            "artifacts": {
                "article": "article.md",
                "illustrations": "imgs",
                "cover": "cover/cover.png",
                "html": "article.html",
                "draft_result": "draft-result.json",
            },
            "stages": stages,
        }
        path = job_dir / "job.json"
        path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        (job_dir / "user-brief.md").write_text(
            "# Brief\n\n## 主题\n测试主题\n\n## 思路\n"
            "- 解释核心变化发生的机制\n- 写清谁承担成本以及适用边界\n",
            encoding="utf-8",
        )
        return path

    def complete_agent_stages(self, job_path, illustration_status="completed"):
        job = pipeline_runtime.pipeline_job.load_job(job_path)
        if job["stages"]["write"]["status"] == "pending":
            job["stages"]["write"] = pipeline_runtime.pipeline_job.stage_record(
                "running", job["created_at"], "write started"
            )
        job["stages"]["humanize"] = pipeline_runtime.pipeline_job.stage_record(
            "completed", job["created_at"], "humanize complete", {"intensity": "strong"}
        )
        job["stages"]["illustrations"] = pipeline_runtime.pipeline_job.stage_record(
            illustration_status, job["created_at"], "illustrations handled"
        )
        pipeline_runtime.pipeline_job.save_job(job_path, job)

    def write_article(self, job_path, image_refs=()):
        """一篇「合格」的稿子。

        check 现在会连带跑写作体检（wechat-viral-writer），所以夹具不能再是
        「一句话重复 65 遍」——那种正文结构合法但没人读得下去，正是体检要拦的东西。
        这里的样例带小标题、短段落、加粗、具体数字和读者落点，跑体检是 80 分以上。
        """
        images = "\n".join(f"![配图]({ref})" for ref in image_refs)
        (job_path.parent / "article.md").write_text(
            PASSING_ARTICLE + "\n\n" + images + "\n", encoding="utf-8",
        )

    def args(self, job_path, **overrides):
        values = {
            "job": str(job_path),
            "config": "wechat-accounts.json",
            "dry_run": False,
            "skip_draft": False,
        }
        values.update(overrides)
        return type("Args", (), values)()

    def make_completed_draft(self, job_path, result_run_id=None):
        job = pipeline_runtime.pipeline_job.load_job(job_path)
        job["stages"]["draft"] = pipeline_runtime.pipeline_job.stage_record(
            "completed", job["created_at"], "draft complete", {"run_id": job["run_id"]}
        )
        job["state"] = "drafted"
        pipeline_runtime.pipeline_job.save_job(job_path, job)
        (job_path.parent / "draft-result.json").write_text(json.dumps({
            "account": "a",
            "action": "draft",
            "run_id": result_run_id or job["run_id"],
            "draft_media_id": "existing-draft",
        }), encoding="utf-8")
        return job

    def test_begin_preserves_completed_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            job = pipeline_runtime.pipeline_job.load_job(job_path)
            job["stages"]["write"] = pipeline_runtime.pipeline_job.stage_record(
                "completed", job["created_at"], "write complete"
            )
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            pipeline_runtime.cmd_begin(self.args(job_path))
            current = pipeline_runtime.pipeline_job.load_job(job_path)
        self.assertEqual("completed", current["stages"]["write"]["status"])
        self.assertNotIn("fact-check", current["stages"])

    def test_begin_rejects_missing_brief_and_unlocked_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            (job_path.parent / "user-brief.md").unlink()
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "缺少用户 brief"):
                pipeline_runtime.cmd_begin(self.args(job_path))

        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            job = pipeline_runtime.pipeline_job.load_job(job_path)
            job.pop("article_shape")
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "结构尚未锁定"):
                pipeline_runtime.cmd_begin(self.args(job_path))

    def test_prepare_accepts_zero_images_and_no_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            pipeline_runtime.cmd_begin(self.args(job_path))
            self.complete_agent_stages(job_path, "skipped")
            self.write_article(job_path)
            result = pipeline_runtime.cmd_prepare(self.args(job_path))
            prepared = pipeline_runtime.pipeline_job.load_job(job_path)
        self.assertEqual(0, result["image_count"])
        self.assertEqual("finish", result["next"])
        self.assertGreaterEqual(result["writing_quality"]["score"], 75)
        self.assertTrue(result["writing_quality"]["checked_after_humanize"])
        self.assertEqual(
            "true",
            prepared["stages"]["write"]["details"]["quality_checked_after_humanize"],
        )
        self.assertFalse((job_path.parent / "sources.md").exists())

    def test_prepare_rechecks_quality_after_humanize(self):
        """humanize 可能改坏节奏；prepare 必须检查最终稿，而不是相信更早的 check。"""
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.complete_agent_stages(job_path, "skipped")
            (job_path.parent / "article.md").write_text(
                "# 关于行业发展的一些观察与思考\n\n"
                + "这件事情引发了广泛的关注，相关方面表示将持续推进后续工作。" * 60,
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                pipeline_runtime.RuntimeFailure, "最终稿写作体检未通过"
            ):
                pipeline_runtime.cmd_prepare(self.args(job_path))

    def test_finish_rechecks_article_changed_after_prepare(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.complete_agent_stages(job_path, "skipped")
            self.write_article(job_path)
            pipeline_runtime.cmd_prepare(self.args(job_path))
            (job_path.parent / "article.md").write_text(
                "# 关于行业发展的一些观察与思考\n\n"
                + "这件事情引发了广泛的关注，相关方面表示将持续推进后续工作。" * 60,
                encoding="utf-8",
            )
            with mock.patch.object(
                pipeline_runtime, "render_body",
                side_effect=AssertionError("质量门禁前不应渲染"),
            ), self.assertRaisesRegex(
                pipeline_runtime.RuntimeFailure, "最终稿写作体检未通过"
            ):
                pipeline_runtime.cmd_finish(self.args(job_path))

    def test_prepare_accepts_three_images_and_rejects_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.complete_agent_stages(job_path)
            refs = [f"imgs/{index}.png" for index in range(3)]
            (job_path.parent / "imgs").mkdir()
            for ref in refs:
                (job_path.parent / ref).write_bytes(b"image")
            self.write_article(job_path, refs)
            result = pipeline_runtime.cmd_prepare(self.args(job_path))
            self.assertEqual(3, result["image_count"])

        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.complete_agent_stages(job_path)
            self.write_article(job_path, [f"imgs/{index}.png" for index in range(4)])
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "最多 3 张"):
                pipeline_runtime.cmd_prepare(self.args(job_path))

    def test_prepare_removes_missing_image_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.complete_agent_stages(job_path)
            self.write_article(job_path, ["imgs/missing.png"])
            result = pipeline_runtime.cmd_prepare(self.args(job_path))
            article = (job_path.parent / "article.md").read_text(encoding="utf-8")
        self.assertEqual(0, result["image_count"])
        self.assertNotIn("missing.png", article)

    def test_prepare_keeps_path_and_length_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.complete_agent_stages(job_path)
            self.write_article(job_path, ["../outside.png"])
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "路径越界"):
                pipeline_runtime.cmd_prepare(self.args(job_path))

        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.complete_agent_stages(job_path)
            (job_path.parent / "article.md").write_text("# 标题\n\n太短。\n", encoding="utf-8")
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "正文字数"):
                pipeline_runtime.cmd_prepare(self.args(job_path))

    def test_render_body_and_cover_do_not_reuse_hash_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            job, artifacts = pipeline_runtime.job_paths(job_path)
            job["stages"]["format"] = pipeline_runtime.pipeline_job.stage_record(
                "completed", job["created_at"], details={"theme": "moyu-green"}
            )
            artifacts["html"].write_text("stale", encoding="utf-8")
            artifacts["inline_visuals"].write_text(
                json.dumps({"version": 1, "theme": "moyu-green", "modules": []}),
                encoding="utf-8",
            )
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            with mock.patch.object(
                pipeline_runtime, "run_json",
                return_value={"status": "ok", "output": str(artifacts["html"])},
            ) as run:
                result = pipeline_runtime.render_body(
                    job_path, job, artifacts, pipeline_runtime.command_roots(job)
                )
            self.assertFalse(result["reused"])
            run.assert_called_once()
            command = run.call_args.args[0]
            self.assertIn("--inline-plan", command)
            self.assertIn(str(artifacts["inline_visuals"]), command)

    def test_accept_cover_preserves_recorded_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            job, artifacts = pipeline_runtime.job_paths(job_path)
            artifacts["cover"].write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
            job["stages"]["cover"] = pipeline_runtime.pipeline_job.stage_record(
                "completed", job["created_at"], details={"backend": "offline_render"}
            )
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            result, generated = pipeline_runtime.accept_cover(
                job_path, job, artifacts, ROOT / "wechat-accounts.json"
            )
        self.assertEqual("offline_render", result["backend"])
        self.assertTrue(generated)

    def test_verified_draft_requires_matching_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.make_completed_draft(job_path)
            job, artifacts = pipeline_runtime.job_paths(job_path)
            result = pipeline_runtime.verified_draft_result(job, artifacts)
            self.assertEqual("existing-draft", result["draft_media_id"])
            artifacts["draft_result"].write_text(json.dumps({
                "account": "a", "action": "draft", "run_id": "other-run",
                "draft_media_id": "wrong",
            }), encoding="utf-8")
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "run_id"):
                pipeline_runtime.verified_draft_result(job, artifacts)

    def test_verified_draft_rejects_stage_run_id_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.make_completed_draft(job_path)
            job = pipeline_runtime.pipeline_job.load_job(job_path)
            job["stages"]["draft"]["details"]["run_id"] = "other-run"
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            job, artifacts = pipeline_runtime.job_paths(job_path)
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "run_id"):
                pipeline_runtime.verified_draft_result(job, artifacts)

    def test_finish_reuses_completed_run_without_external_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            self.make_completed_draft(job_path)
            with mock.patch.object(
                pipeline_runtime, "render_body", side_effect=AssertionError("external command")
            ):
                result = pipeline_runtime.cmd_finish(self.args(job_path))
        self.assertTrue(result["resumed"])
        self.assertEqual("drafted", result["state"])

    def test_finish_blocks_running_and_uncertain_draft(self):
        for status, details in (
            ("running", {"run_id": "run-test-1", "outcome": "pending"}),
            ("failed", {"run_id": "run-test-1", "outcome": "uncertain"}),
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                job_path = self.make_job(tmp)
                job = pipeline_runtime.pipeline_job.load_job(job_path)
                job["stages"]["draft"] = pipeline_runtime.pipeline_job.stage_record(
                    status, job["created_at"], details=details
                )
                pipeline_runtime.pipeline_job.save_job(job_path, job)
                with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "人工核对"):
                    pipeline_runtime.cmd_finish(self.args(job_path, dry_run=True))

    def test_publish_draft_records_run_id_and_classifies_failures(self):
        messages = (
            ("未设置 AppID 环境变量：A_ID", "preflight-failed", "true"),
            ("SSL unexpected EOF", "uncertain", "false"),
        )
        for message, outcome, retry_safe in messages:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                job_path = self.make_job(tmp)
                self.write_article(job_path)
                job, artifacts = pipeline_runtime.job_paths(job_path)
                artifacts["html"].write_text("<section>正文</section>", encoding="utf-8")
                with mock.patch.object(
                    pipeline_runtime, "run_json",
                    side_effect=pipeline_runtime.RuntimeFailure(message),
                ):
                    with self.assertRaises(pipeline_runtime.RuntimeFailure):
                        pipeline_runtime.publish_draft(
                            self.args(job_path), job, artifacts,
                            pipeline_runtime.command_roots(job), False,
                            ROOT / "wechat-accounts.json",
                        )
                failed = pipeline_runtime.pipeline_job.load_job(job_path)["stages"]["draft"]
                self.assertEqual(outcome, failed["details"]["outcome"])
                self.assertEqual(retry_safe, failed["details"]["retry_safe"])
                self.assertEqual("run-test-1", failed["details"]["run_id"])

    def test_publish_draft_accepts_only_complete_matching_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            job, artifacts = pipeline_runtime.job_paths(job_path)
            artifacts["html"].write_text("<section>正文</section>", encoding="utf-8")
            result = {
                "account": "a", "action": "draft", "run_id": "run-test-1",
                "draft_media_id": "new-draft",
            }
            with mock.patch.object(pipeline_runtime, "run_json", return_value=result):
                returned = pipeline_runtime.publish_draft(
                    self.args(job_path), job, artifacts,
                    pipeline_runtime.command_roots(job), False,
                    ROOT / "wechat-accounts.json",
                )
            current = pipeline_runtime.pipeline_job.load_job(job_path)
        self.assertEqual("new-draft", returned["draft_media_id"])
        self.assertEqual("completed", current["stages"]["draft"]["status"])
        self.assertEqual("run-test-1", current["stages"]["draft"]["details"]["run_id"])

    def test_begin_outputs_writing_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            job = pipeline_runtime.pipeline_job.load_job(job_path)
            job["article_shape"] = {
                "structure_id": "industry_game", "opening_type": "myth",
                "ending_type": "actionable_question", "heading_count": 5,
                "body_band": "long",
            }
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            result = pipeline_runtime.cmd_begin(self.args(job_path))
        contract = result["writing_contract"]
        self.assertEqual("article.md", contract["output_file"])
        self.assertIn("32", contract["title"])
        self.assertIn("1500", contract["body_chars"])
        self.assertIn("2600—4000", contract["body_chars"])
        self.assertEqual("industry_game", contract["shape"]["structure_id"])

    def test_check_reports_all_problems_without_state_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            (job_path.parent / "article.md").write_text(
                "# 这个标题实在是太长了完全彻底超过了三十二个字的硬性限制肯定过不了关卡\n\n"
                "太短。\n\n![图](../escape.png)\n![图](imgs/miss.png)\n【插入示意图】\n",
                encoding="utf-8",
            )
            result = pipeline_runtime.cmd_check(self.args(job_path))
            job_after = pipeline_runtime.pipeline_job.load_job(job_path)
        self.assertEqual("fail", result["status"])
        joined = "；".join(result["problems"])
        self.assertIn("标题", joined)
        self.assertIn("正文", joined)
        self.assertIn("越界", joined)
        self.assertIn("占位符", joined)
        self.assertTrue(any("miss.png" in h for h in result["hints"]))
        self.assertEqual("pending", job_after["stages"]["write"]["status"])

    def test_check_passes_valid_article_with_digest_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertEqual("ok", result["status"])
        self.assertTrue(any("digest" in h for h in result["hints"]))

    def test_digest_that_repeats_the_title_is_flagged(self):
        """分享卡上标题和摘要并排出现，说同一句话等于只说了一句。"""
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            (job_path.parent / "digest.txt").write_text(
                "上线前那道验收，卡了我们整整三周的时间", encoding="utf-8")
            result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertTrue(any("复述标题" in h for h in result["hints"]))

    def test_digest_with_a_second_hook_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            (job_path.parent / "digest.txt").write_text(
                "五分钟能改完的配置，为什么拖成了一次需要人工介入的事故",
                encoding="utf-8")
            result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertFalse(any("复述标题" in h for h in result["hints"]))
        self.assertFalse(any("太短" in h for h in result["hints"]))

    def test_too_short_digest_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            (job_path.parent / "digest.txt").write_text("很短", encoding="utf-8")
            result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertTrue(any("太短" in h for h in result["hints"]))

    def test_writing_contract_carries_readability_gates(self):
        """体检判据必须提前告诉写作方，否则每篇都要多返工一轮。"""
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            contract = pipeline_runtime.cmd_begin(
                self.args(job_path))["writing_contract"]
        gates = contract["readability_gates"]
        for key in ("opening", "value_anchor", "hook", "paragraph",
                    "sentence", "takeaway", "banned_ending", "scored_by"):
            self.assertIn(key, gates)
        self.assertIn("300", gates["value_anchor"])
        self.assertIn("75", gates["scored_by"])
        self.assertIn("1500", contract["length_plan"])

    def test_check_carries_writing_health(self):
        """check 顺带跑写作体检：模型已经会跑 check，多一条命令就多一个会被忘掉的步骤。"""
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertIsNotNone(result["writing"])
        self.assertGreaterEqual(result["writing"]["score"], 75)
        self.assertEqual(75, result["writing"]["pass_line"])
        self.assertIn("score_draft.py", result["writing"]["report_command"])
        self.assertIn("hook", result["writing"]["dimensions"])

    def test_check_blocks_on_unreadable_article(self):
        """结构合法但没人读得下去的稿子，必须在 check 就被拦住而不是一路发出去。"""
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            (job_path.parent / "article.md").write_text(
                "# 关于行业发展的一些观察与思考\n\n"
                + "这件事情引发了广泛的关注，相关方面表示将持续推进后续工作。" * 60,
                encoding="utf-8",
            )
            result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("[写作" in p for p in result["problems"]))
        self.assertLess(result["writing"]["score"], 75)

    def test_check_survives_missing_scorer(self):
        """写作体检是软依赖：Skill 不在时 check 照常工作，只是少一段反馈。"""
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            with mock.patch.object(
                pipeline_runtime, "VIRAL_SCORER", Path(tmp) / "nope.py"
            ):
                result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertIsNone(result["writing"])
        self.assertEqual("ok", result["status"])

    def test_check_hands_out_a_runnable_cover_command(self):
        """封面是 finish 硬门禁：缺封面时必须给出一条可直接执行的命令。

        这条命令要覆盖整条降级链（用户图 → 生图 → 离线兜底）并自己记账。早期版本
        只给离线兜底那一档，等于把「生图怎么调」留给 agent 临场发挥——那是本次
        端到端跑通时实际卡住的一步。
        """
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            result = pipeline_runtime.cmd_check(self.args(job_path))
        cover_hints = [h for h in result["hints"] if "封面" in h]
        self.assertEqual(1, len(cover_hints))
        hint = cover_hints[0]
        self.assertIn("gen_cover_image.py", hint)
        self.assertIn("--job", hint)
        self.assertIn("--record-stage", hint)
        # 不再要求 agent 自己判断该走哪一档
        self.assertNotIn("render_cover_fallback.py", hint)
        self.assertEqual("ok", result["status"])

    def test_check_stays_silent_when_cover_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            cover = job_path.parent / "cover" / "cover.png"
            cover.parent.mkdir(parents=True, exist_ok=True)
            cover.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 2048)
            result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertFalse([h for h in result["hints"] if "封面" in h])

    def test_publish_draft_passes_optional_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            job, artifacts = pipeline_runtime.job_paths(job_path)
            artifacts["html"].write_text("<section>正文</section>", encoding="utf-8")
            (job_path.parent / "digest.txt").write_text(
                "一句话摘要钩子\n第二行会被合并  " + "长" * 80, encoding="utf-8"
            )
            result = {
                "account": "a", "action": "draft", "run_id": "run-test-1",
                "draft_media_id": "new-draft",
            }
            with mock.patch.object(
                pipeline_runtime, "run_json", return_value=result
            ) as run_json:
                pipeline_runtime.publish_draft(
                    self.args(job_path), job, artifacts,
                    pipeline_runtime.command_roots(job), False,
                    ROOT / "wechat-accounts.json",
                )
            command = run_json.call_args[0][0]
        self.assertIn("--digest", command)
        digest = command[command.index("--digest") + 1]
        self.assertTrue(digest.startswith("一句话摘要钩子 第二行会被合并"))
        self.assertLessEqual(len(digest), 64)

    def test_publish_draft_without_digest_file_omits_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            self.write_article(job_path)
            job, artifacts = pipeline_runtime.job_paths(job_path)
            artifacts["html"].write_text("<section>正文</section>", encoding="utf-8")
            result = {
                "account": "a", "action": "draft", "run_id": "run-test-1",
                "draft_media_id": "new-draft",
            }
            with mock.patch.object(
                pipeline_runtime, "run_json", return_value=result
            ) as run_json:
                pipeline_runtime.publish_draft(
                    self.args(job_path), job, artifacts,
                    pipeline_runtime.command_roots(job), False,
                    ROOT / "wechat-accounts.json",
                )
            command = run_json.call_args[0][0]
        self.assertNotIn("--digest", command)

    def test_finish_file_lock_serializes_same_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            active = 0
            maximum = 0
            guard = threading.Lock()

            def critical(_args):
                nonlocal active, maximum
                with guard:
                    active += 1
                    maximum = max(maximum, active)
                time.sleep(0.08)
                with guard:
                    active -= 1
                return {"status": "ok"}

            errors = []
            with mock.patch.object(pipeline_runtime, "_cmd_finish", side_effect=critical):
                threads = [threading.Thread(
                    target=lambda: pipeline_runtime.cmd_finish(self.args(job_path))
                ) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
        self.assertEqual([], errors)
        self.assertEqual(1, maximum)

    def test_job_paths_and_parser_keep_safety_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            job = pipeline_runtime.pipeline_job.load_job(job_path)
            job["artifacts"]["article"] = "/etc/passwd"
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            with self.assertRaisesRegex(Exception, "工作区"):
                pipeline_runtime.job_paths(job_path)
        parser = pipeline_runtime.build_parser()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["publish", "--job", "/tmp/job.json"])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args([
                "finish", "--job", "/tmp/job.json", "--dry-run", "--skip-draft",
            ])

    def test_count_body_chars_ignores_title_and_markdown_noise(self):
        article = "# 标题不计入\n\n## 小节\n\n这是**正文**内容。\n"
        self.assertEqual(
            len("小节这是正文内容。"),
            pipeline_runtime.count_body_chars(article),
        )

    def test_manuscript_check_skips_word_count_and_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            job = pipeline_runtime.pipeline_job.load_job(job_path)
            job["lane"] = "manuscript"
            job["switches"] = {"humanize": False}
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            (job_path.parent / "article.md").write_text(
                "# 用户自己写的短稿\n\n就这几句，不够一千五，也不该被拦。\n",
                encoding="utf-8",
            )
            result = pipeline_runtime.cmd_check(self.args(job_path))
        self.assertEqual("ok", result["status"])
        self.assertIsNone(result["writing"])
        self.assertLess(result["body_chars"], 1500)

    def test_manuscript_begin_skips_humanize_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            job = pipeline_runtime.pipeline_job.load_job(job_path)
            job["lane"] = "manuscript"
            job["switches"] = {"humanize": False}
            pipeline_runtime.pipeline_job.save_job(job_path, job)
            (job_path.parent / "article.md").write_text(
                "# 用户自己写的短稿\n\n保留原文，只做排版。\n",
                encoding="utf-8",
            )
            result = pipeline_runtime.cmd_begin(self.args(job_path))
            loaded = pipeline_runtime.pipeline_job.load_job(job_path)
        self.assertEqual("manuscript", result["lane"])
        self.assertFalse(result["humanize"])
        self.assertEqual("running", loaded["stages"]["write"]["status"])
        self.assertEqual("skipped", loaded["stages"]["humanize"]["status"])


if __name__ == "__main__":
    unittest.main()
