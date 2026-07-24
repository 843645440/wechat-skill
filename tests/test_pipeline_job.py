import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/wechat-content-pipeline/scripts/pipeline_job.py"
SPEC = importlib.util.spec_from_file_location("pipeline_job", SCRIPT)
pipeline_job = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline_job)


class PipelineJobTests(unittest.TestCase):
    def init_job(self, tmp, topic="AI进入真实工作流程", force_new=False, **overrides):
        root = Path(tmp)
        (root / "config").mkdir(exist_ok=True)
        (root / "references").mkdir(exist_ok=True)
        profile = {
            "audience": "职场读者",
            "topic_discovery": {
                "max_age_hours": 48,
                "categories": ["人工智能", "就业变化"],
            },
            "theme_strategy": "random",
            "illustrations": {
                "enabled": True,
                "skill": "baoyu-article-illustrator",
                "backend": overrides.get("illustration_backend", "image_generate"),
                "max_images": overrides.get("max_images", 3),
            },
            "cover": {
                "enabled": True,
                "backend": overrides.get("cover_backend", "html"),
                "aspect": "2.35:1",
                "theme": "article",
                "text": "title-only",
            },
            "publishing": {"target": "draft"},
        }
        (root / "config/wechat-content-profiles.json").write_text(json.dumps({
            "version": 5, "profiles": {"a": profile},
        }, ensure_ascii=False), encoding="utf-8")
        (root / "references/theme-index.md").write_text(
            "# 主题索引\n\n## 已注册主题\n\n"
            "| 墨绿 | `references/theme-moyu-green.md` |\n\n"
            "## 新主题登记流程\n",
            encoding="utf-8",
        )
        argv = ["init", "--project-root", str(root), "--account", "a"]
        if topic is not None:
            argv.extend(("--topic", topic))
        if force_new:
            argv.append("--force-new")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            pipeline_job.cmd_init(pipeline_job.build_parser().parse_args(argv))
        return Path(output.getvalue().strip())

    def stage(self, job_path, name, status, details=()):
        if name in ("humanize", "illustrations") and status == "completed":
            self.stage(job_path, name, "running")
        argv = ["stage", "--job", str(job_path), "--name", name, "--status", status]
        for detail in details:
            argv.extend(("--detail", detail))
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline_job.cmd_stage(pipeline_job.build_parser().parse_args(argv))

    def complete_gate_stages(self, job_path, illustration_status="completed"):
        for name in ("write", "humanize", "format"):
            self.stage(job_path, name, "completed")
        self.stage(job_path, "illustrations", illustration_status)
        self.stage(job_path, "cover", "completed")

    def record_hotspot(self, job_path, published_at=None, category="人工智能", focus="机器人进入产线"):
        published_at = published_at or datetime.now(timezone.utc).isoformat()
        args = pipeline_job.build_parser().parse_args([
            "topic", "--job", str(job_path), "--value", "机器人进入汽车工厂",
            "--source", "auto-hotspot", "--category", category,
            "--published-at", published_at, "--event-focus", focus,
        ])
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline_job.cmd_topic(args)

    def test_init_creates_schema_five_run_id_and_simplified_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.init_job(tmp)
            first_job = pipeline_job.load_job(first)
            second = self.init_job(tmp, topic="第二篇")
            second_job = pipeline_job.load_job(second)
        self.assertEqual(5, second_job["schema_version"])
        self.assertNotEqual(first_job["run_id"], second_job["run_id"])
        self.assertNotIn("fact-check", second_job["stages"])
        self.assertNotIn("validate", second_job["stages"])
        self.assertNotIn("sources", second_job["artifacts"])
        self.assertNotIn("preview", second_job["artifacts"])

    def test_profiles_use_single_48_hour_window(self):
        config = json.loads((ROOT / "config/wechat-content-profiles.json").read_text(encoding="utf-8"))
        self.assertEqual(5, config["version"])
        for profile in config["profiles"].values():
            discovery = profile["topic_discovery"]
            self.assertEqual(48, discovery["max_age_hours"])
            self.assertNotIn("window_hours", discovery)
            self.assertNotIn("fallback_hours", discovery)

    def test_init_preserves_workspace_safety_and_force_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "work/a/current"
            current.mkdir(parents=True)
            marker = current / "article.md"
            marker.write_text("unfinished", encoding="utf-8")
            with self.assertRaisesRegex(pipeline_job.JobError, "缺少 job.json"):
                self.init_job(tmp)
            self.assertTrue(marker.is_file())
            replacement = self.init_job(tmp, force_new=True)
            self.assertTrue(replacement.is_file())
            self.assertFalse(marker.exists())

    def test_init_refuses_running_or_uncertain_workspace_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            self.stage(job_path, "draft", "running", ("run_id=attempt", "outcome=pending"))
            with self.assertRaisesRegex(pipeline_job.JobError, "未解决"):
                self.init_job(tmp, topic="新选题")

    def test_init_rejects_symlink_workdir_escape(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            (Path(tmp) / "work").mkdir()
            os.symlink(outside, Path(tmp) / "work/a")
            (Path(outside) / "current").mkdir()
            marker = Path(outside) / "current/keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(pipeline_job.JobError, "路径不安全"):
                self.init_job(tmp)
            self.assertTrue(marker.is_file())

    def test_init_rejects_invalid_profile_backends_and_image_count(self):
        cases = (
            ({"illustration_backend": "other"}, "Baoyu"),
            ({"cover_backend": "other"}, "HTML 封面"),
            ({"max_images": 4}, "Baoyu"),
        )
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(pipeline_job.JobError, message):
                    self.init_job(tmp, **kwargs)

    def test_auto_hotspot_accepts_category_timestamp_and_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            self.record_hotspot(job_path)
            job = pipeline_job.load_job(job_path)
            history = json.loads((Path(tmp) / "work/a/topic-history.json").read_text(encoding="utf-8"))
        self.assertEqual("completed", job["stages"]["discover"]["status"])
        self.assertEqual("机器人进入产线", history["topics"][-1]["event_focus"])
        self.assertEqual(2, history["version"])
        self.assertNotIn("evidence_urls", history["topics"][-1])

    def test_auto_hotspot_rejects_old_future_and_wrong_category(self):
        values = (
            ((datetime.now(timezone.utc) - timedelta(hours=49)).isoformat(), "人工智能", "48 小时"),
            ((datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), "人工智能", "48 小时"),
            (datetime.now(timezone.utc).isoformat(), "医疗", "账号类别"),
        )
        for published, category, message in values:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                job_path = self.init_job(tmp, topic=None)
                with self.assertRaisesRegex(pipeline_job.JobError, message):
                    self.record_hotspot(job_path, published, category)

    def test_history_returns_last_seven_days_without_mechanical_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            history_path = Path(tmp) / "work/a/topic-history.json"
            history_path.write_text(json.dumps({
                "version": 2, "account": "a", "topics": [
                    {"topic": "旧", "event_focus": "旧事件", "selected_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()},
                    {"topic": "近", "event_focus": "机器人进入产线", "selected_at": datetime.now(timezone.utc).isoformat()},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            output = io.StringIO()
            args = pipeline_job.build_parser().parse_args(["history", "--job", str(job_path)])
            with contextlib.redirect_stdout(output):
                pipeline_job.cmd_history(args)
            entries = json.loads(output.getvalue())
            self.record_hotspot(job_path, focus="机器人走进汽车制造现场")
        self.assertEqual(["机器人进入产线"], [entry["event_focus"] for entry in entries])

    def test_stage_requires_running_before_humanize_or_illustrations_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            for name in ("humanize", "illustrations"):
                args = pipeline_job.build_parser().parse_args([
                    "stage", "--job", str(job_path), "--name", name, "--status", "completed",
                ])
                with self.subTest(name=name), self.assertRaisesRegex(pipeline_job.JobError, "先标记 running"):
                    pipeline_job.cmd_stage(args)

    def test_stage_records_duration_and_theme_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            self.stage(job_path, "write", "running")
            running = pipeline_job.load_job(job_path)["stages"]["write"]
            self.stage(job_path, "write", "completed")
            completed = pipeline_job.load_job(job_path)["stages"]["write"]
            args = pipeline_job.build_parser().parse_args(["choose-theme", "--job", str(job_path)])
            first, second = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(first):
                pipeline_job.cmd_choose_theme(args)
            with contextlib.redirect_stdout(second):
                pipeline_job.cmd_choose_theme(args)
        self.assertEqual(running["started_at"], completed["started_at"])
        self.assertGreaterEqual(completed["duration_ms"], 0)
        self.assertEqual("moyu-green", first.getvalue().strip())
        self.assertEqual(first.getvalue(), second.getvalue())

    def test_gate_accepts_zero_images_and_rejects_pending_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            (job_path.parent / "article.html").write_text("<section><p>正文</p></section>", encoding="utf-8")
            self.complete_gate_stages(job_path, "skipped")
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", str(job_path)])
            with contextlib.redirect_stdout(io.StringIO()):
                pipeline_job.cmd_gate(gate)

        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            (job_path.parent / "article.html").write_text("<section><p>正文</p></section>", encoding="utf-8")
            for name in ("write", "humanize", "format"):
                self.stage(job_path, name, "completed")
            self.stage(job_path, "cover", "completed")
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", str(job_path)])
            with self.assertRaisesRegex(pipeline_job.JobError, "illustrations"):
                pipeline_job.cmd_gate(gate)

    def test_gate_keeps_placeholder_and_cover_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            (job_path.parent / "article.html").write_text("<section>{{作者名}}</section>", encoding="utf-8")
            self.complete_gate_stages(job_path)
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", str(job_path)])
            with self.assertRaisesRegex(pipeline_job.JobError, "占位"):
                pipeline_job.cmd_gate(gate)
            (job_path.parent / "article.html").write_text("<section>正文</section>", encoding="utf-8")
            self.stage(job_path, "cover", "skipped", ("default_thumb_media_id=false",))
            with self.assertRaisesRegex(pipeline_job.JobError, "封面"):
                pipeline_job.cmd_gate(gate)

    def test_old_schema_migrates_to_stable_legacy_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            raw = json.loads(job_path.read_text(encoding="utf-8"))
            raw["schema_version"] = 4
            raw.pop("run_id")
            raw["stages"]["fact-check"] = pipeline_job.stage_record("completed")
            raw["artifacts"]["sources"] = "sources.md"
            job_path.write_text(json.dumps(raw), encoding="utf-8")
            first = pipeline_job.load_job(job_path)
            second = pipeline_job.load_job(job_path)
        self.assertEqual(5, first["schema_version"])
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertNotIn("fact-check", first["stages"])
        self.assertNotIn("sources", first["artifacts"])


if __name__ == "__main__":
    unittest.main()
