import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    ROOT, ".agents", "skills", "wechat-content-pipeline", "scripts", "pipeline_job.py"
)
SPEC = importlib.util.spec_from_file_location("pipeline_job", SCRIPT)
pipeline_job = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline_job)


class PipelineJobTests(unittest.TestCase):
    def init_job(
        self,
        tmp,
        topic="AI 如何改变初级程序员的工作",
        inline_mode="native-html",
        max_blocks=3,
        cover_backend="html",
    ):
        config_dir = os.path.join(tmp, "config")
        references_dir = os.path.join(tmp, "references")
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(references_dir, exist_ok=True)
        with open(
            os.path.join(config_dir, "wechat-content-profiles.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                {
                    "version": 4,
                    "profiles": {
                        "a": {
                            "theme_strategy": "random",
                            "inline_visuals": {
                                "enabled": True,
                                "mode": inline_mode,
                                "max_blocks": max_blocks,
                            },
                            "cover": {
                                "enabled": True,
                                "backend": cover_backend,
                                "aspect": "2.35:1",
                                "theme": "article",
                                "text": "title-only",
                            },
                            "publishing": {"target": "draft"},
                        }
                    },
                },
                f,
            )
        with open(
            os.path.join(references_dir, "theme-index.md"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(
                "# 主题索引\n\n"
                "## 已注册主题\n\n"
                "| 摸鱼绿 | `references/theme-moyu-green.md` |\n"
                "| 石墨 | `references/theme-graphite-minimal.md` |\n\n"
                "## 新主题登记流程\n\n"
                "生成器见 `references/theme-generator.md`。\n"
            )
        argv = [
            "init", "--project-root", tmp, "--work-dir", "work", "--account", "a",
        ]
        if topic is not None:
            argv.extend(("--topic", topic))
        args = pipeline_job.build_parser().parse_args(argv)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            pipeline_job.cmd_init(args)
        return output.getvalue().strip()

    def update_stage(self, job_path, name, status, details=None):
        argv = ["stage", "--job", job_path, "--name", name, "--status", status]
        for item in details or []:
            argv.extend(("--detail", item))
        args = pipeline_job.build_parser().parse_args(argv)
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline_job.cmd_stage(args)

    def complete_required_stages(self, job_path):
        for name in (
            "write",
            "fact-check",
            "format",
            "inline-visuals",
            "validate",
        ):
            self.update_stage(job_path, name, "completed")

    def test_init_uses_account_current_workspace_and_given_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            with open(job_path, encoding="utf-8") as f:
                job = json.load(f)
            self.assertEqual(job["schema_version"], 4)
            self.assertEqual(job["account"], "a")
            self.assertEqual(job["topic_source"], "provided")
            self.assertEqual(job["stages"]["discover"]["status"], "completed")
            self.assertEqual(
                os.path.normpath(os.path.dirname(job_path)),
                os.path.normpath(os.path.join(tmp, "work", "a", "current")),
            )
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(job_path), "illustrations")))
            self.assertTrue(os.path.isdir(os.path.join(os.path.dirname(job_path), "cover")))

    def test_account_profiles_enforce_native_html_modules_and_html_cover(self):
        profile_path = os.path.join(ROOT, "config", "wechat-content-profiles.json")
        with open(profile_path, encoding="utf-8") as f:
            profiles = json.load(f)["profiles"]
        self.assertEqual({"a", "b"}, set(profiles))
        for profile in profiles.values():
            self.assertEqual(profile["theme_strategy"], "random")
            self.assertIs(profile["inline_visuals"]["enabled"], True)
            self.assertEqual(profile["inline_visuals"]["mode"], "native-html")
            self.assertLessEqual(profile["inline_visuals"]["max_blocks"], 3)
            self.assertIs(profile["cover"]["enabled"], True)
            self.assertEqual(profile["cover"]["backend"], "html")
            self.assertEqual(profile["publishing"]["target"], "draft")
            self.assertNotIn("schedule", profile)
            self.assertNotIn("publish", profile["publishing"])

    def test_init_rejects_non_native_body_visual_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(pipeline_job.JobError, "原生 HTML 信息模块"):
                self.init_job(tmp, inline_mode="png")

    def test_init_rejects_non_html_cover_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(pipeline_job.JobError, "HTML 封面"):
                self.init_job(tmp, cover_backend="agnes")

    def test_init_rejects_more_than_three_native_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(pipeline_job.JobError, "原生 HTML 信息模块"):
                self.init_job(tmp, max_blocks=4)

    def test_status_alias_shows_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            args = pipeline_job.build_parser().parse_args(["status", "--job", job_path])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                pipeline_job.cmd_show(args)
            self.assertEqual(json.loads(output.getvalue())["account"], "a")

    def test_reinitializing_account_clears_previous_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            marker = os.path.join(os.path.dirname(job_path), "old-article.md")
            with open(marker, "w", encoding="utf-8") as f:
                f.write("old")
            second_job_path = self.init_job(tmp, topic="新的选题")
            self.assertEqual(job_path, second_job_path)
            self.assertFalse(os.path.exists(marker))

    def test_missing_topic_requires_discovery_then_records_hotspot(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            with open(job_path, encoding="utf-8") as f:
                job = json.load(f)
            self.assertIsNone(job["topic"])
            self.assertEqual(job["stages"]["discover"]["status"], "pending")

            args = pipeline_job.build_parser().parse_args([
                "topic", "--job", job_path, "--value", "机器人进入汽车工厂",
                "--source", "auto-hotspot",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                pipeline_job.cmd_topic(args)
            with open(job_path, encoding="utf-8") as f:
                job = json.load(f)
            self.assertEqual(job["topic_source"], "auto-hotspot")
            self.assertEqual(job["stages"]["discover"]["status"], "completed")
            self.assertIsNotNone(job["stages"]["discover"]["started_at"])
            self.assertIsNotNone(job["stages"]["discover"]["completed_at"])
            self.assertGreaterEqual(job["stages"]["discover"]["duration_ms"], 0)

    def test_stage_records_precise_start_completion_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            self.update_stage(job_path, "write", "running")
            with open(job_path, encoding="utf-8") as f:
                running = json.load(f)["stages"]["write"]
            self.assertIsNotNone(running["started_at"])
            self.assertIsNone(running["completed_at"])
            self.assertIsNone(running["duration_ms"])

            self.update_stage(job_path, "write", "completed")
            with open(job_path, encoding="utf-8") as f:
                completed = json.load(f)["stages"]["write"]
            self.assertEqual(running["started_at"], completed["started_at"])
            self.assertIsNotNone(completed["completed_at"])
            self.assertGreaterEqual(completed["duration_ms"], 0)

    def test_random_theme_is_registered_candidate_and_stable_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            argv = [
                "choose-theme", "--job", job_path,
            ]
            args = pipeline_job.build_parser().parse_args(argv)
            first = io.StringIO()
            second = io.StringIO()
            with contextlib.redirect_stdout(first):
                pipeline_job.cmd_choose_theme(args)
            with contextlib.redirect_stdout(second):
                pipeline_job.cmd_choose_theme(args)
            selected = first.getvalue().strip()
            self.assertIn(selected, {"moyu-green", "graphite-minimal"})
            self.assertEqual(selected, second.getvalue().strip())

    def test_draft_gate_requires_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            job_dir = os.path.dirname(job_path)
            with open(os.path.join(job_dir, "article.html"), "w", encoding="utf-8") as f:
                f.write('<section><p><span leaf="">正文。</span></p></section>')
            self.complete_required_stages(job_path)
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", job_path])
            self.update_stage(
                job_path, "cover", "skipped", ["default_thumb_media_id=false"]
            )
            with self.assertRaisesRegex(pipeline_job.JobError, "封面"):
                pipeline_job.cmd_gate(gate)

            self.update_stage(
                job_path, "cover", "skipped", ["default_thumb_media_id=true"]
            )
            with contextlib.redirect_stdout(io.StringIO()):
                pipeline_job.cmd_gate(gate)

    def test_gate_rejects_unresolved_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            job_dir = os.path.dirname(job_path)
            with open(os.path.join(job_dir, "article.html"), "w", encoding="utf-8") as f:
                f.write('<section><span leaf="">{{作者名}}</span></section>')
            self.complete_required_stages(job_path)
            self.update_stage(job_path, "cover", "completed")
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", job_path])
            with self.assertRaisesRegex(pipeline_job.JobError, "占位"):
                pipeline_job.cmd_gate(gate)

    def test_gate_accepts_one_attempt_inline_degradation_with_empty_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            job_dir = os.path.dirname(job_path)
            choose = pipeline_job.build_parser().parse_args([
                "choose-theme", "--job", job_path, "--theme", "moyu-green",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                pipeline_job.cmd_choose_theme(choose)
            with open(os.path.join(job_dir, "article.html"), "w", encoding="utf-8") as f:
                f.write('<section><p><span leaf="">正文。</span></p></section>')
            with open(os.path.join(job_dir, "inline-visuals.json"), "w", encoding="utf-8") as f:
                json.dump({"version": 1, "theme": "moyu-green", "modules": []}, f)
            for name in ("write", "fact-check", "format", "validate"):
                self.update_stage(job_path, name, "completed")
            self.update_stage(
                job_path,
                "inline-visuals",
                "skipped",
                ["degraded=true", "module_count=0", "reason=anchor-not-found"],
            )
            self.update_stage(job_path, "cover", "completed")
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", job_path])
            with contextlib.redirect_stdout(io.StringIO()):
                pipeline_job.cmd_gate(gate)

    def test_gate_rejects_unverified_inline_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            job_dir = os.path.dirname(job_path)
            with open(os.path.join(job_dir, "article.html"), "w", encoding="utf-8") as f:
                f.write('<section><p><span leaf="">正文。</span></p></section>')
            for name in ("write", "fact-check", "format", "validate"):
                self.update_stage(job_path, name, "completed")
            self.update_stage(job_path, "inline-visuals", "skipped")
            self.update_stage(job_path, "cover", "completed")
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", job_path])
            with self.assertRaisesRegex(pipeline_job.JobError, "未按规则降级"):
                pipeline_job.cmd_gate(gate)


if __name__ == "__main__":
    unittest.main()
