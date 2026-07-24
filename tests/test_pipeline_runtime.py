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
            "topic_source": "provided",
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
        return path

    def complete_agent_stages(self, job_path, illustration_status="completed"):
        job = pipeline_runtime.pipeline_job.load_job(job_path)
        job["stages"]["humanize"] = pipeline_runtime.pipeline_job.stage_record(
            "completed", job["created_at"], "humanize complete", {"intensity": "strong"}
        )
        job["stages"]["illustrations"] = pipeline_runtime.pipeline_job.stage_record(
            illustration_status, job["created_at"], "illustrations handled"
        )
        pipeline_runtime.pipeline_job.save_job(job_path, job)

    def write_article(self, job_path, image_refs=()):
        body = "这是经过核实的完整正文，用于验证公众号流水线的实际运行边界。" * 65
        images = "\n".join(f"![配图]({ref})" for ref in image_refs)
        (job_path.parent / "article.md").write_text(
            f"# 明确主体进入真实工作流程\n\n{body}\n\n{images}\n",
            encoding="utf-8",
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

    def test_prepare_accepts_zero_images_and_no_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            pipeline_runtime.cmd_begin(self.args(job_path))
            self.complete_agent_stages(job_path, "skipped")
            self.write_article(job_path)
            result = pipeline_runtime.cmd_prepare(self.args(job_path))
        self.assertEqual(0, result["image_count"])
        self.assertEqual("finish", result["next"])
        self.assertFalse((job_path.parent / "sources.md").exists())

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


if __name__ == "__main__":
    unittest.main()
