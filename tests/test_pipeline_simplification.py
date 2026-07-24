import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
JOB_PATH = ROOT / ".agents/skills/wechat-content-pipeline/scripts/pipeline_job.py"
RUNTIME_PATH = ROOT / ".agents/skills/wechat-content-pipeline/scripts/pipeline_runtime.py"

JOB_SPEC = importlib.util.spec_from_file_location("simplified_pipeline_job", JOB_PATH)
pipeline_job = importlib.util.module_from_spec(JOB_SPEC)
JOB_SPEC.loader.exec_module(pipeline_job)

RUNTIME_SPEC = importlib.util.spec_from_file_location("simplified_pipeline_runtime", RUNTIME_PATH)
pipeline_runtime = importlib.util.module_from_spec(RUNTIME_SPEC)
RUNTIME_SPEC.loader.exec_module(pipeline_runtime)


class SimplifiedPipelineTests(unittest.TestCase):
    def init_job(self, tmp, topic=None):
        root = Path(tmp)
        (root / "config").mkdir(exist_ok=True)
        (root / "references").mkdir(exist_ok=True)
        (root / "config/wechat-content-profiles.json").write_text(json.dumps({
            "version": 5,
            "profiles": {"a": {
                "audience": "读者",
                "topic_discovery": {
                    "max_age_hours": 48,
                    "categories": ["人工智能"],
                },
                "theme_strategy": "random",
                "illustrations": {
                    "enabled": True,
                    "skill": "baoyu-article-illustrator",
                    "backend": "image_generate",
                    "max_images": 3,
                },
                "cover": {
                    "enabled": True,
                    "backend": "html",
                    "aspect": "2.35:1",
                    "theme": "article",
                    "text": "title-only",
                },
                "publishing": {"target": "draft"},
            }},
        }, ensure_ascii=False), encoding="utf-8")
        (root / "references/theme-index.md").write_text(
            "# 主题索引\n\n## 已注册主题\n\n"
            "| 墨绿 | `references/theme-moyu-green.md` |\n\n## 新主题登记流程\n",
            encoding="utf-8",
        )
        argv = ["init", "--project-root", str(root), "--account", "a"]
        if topic:
            argv.extend(("--topic", topic))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            pipeline_job.cmd_init(pipeline_job.build_parser().parse_args(argv))
        return Path(output.getvalue().strip())

    def record_hotspot(self, job_path, published_at, focus, value="机器人进入汽车工厂"):
        args = pipeline_job.build_parser().parse_args([
            "topic", "--job", str(job_path), "--value", value,
            "--source", "auto-hotspot", "--category", "人工智能",
            "--published-at", published_at, "--event-focus", focus,
        ])
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline_job.cmd_topic(args)

    def test_init_uses_run_id_and_omits_deleted_stages_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.init_job(tmp, "第一篇")
            first_job = pipeline_job.load_job(first)
            second = self.init_job(tmp, "第二篇")
            second_job = pipeline_job.load_job(second)
        self.assertNotEqual(first_job["run_id"], second_job["run_id"])
        self.assertNotIn("fact-check", second_job["stages"])
        self.assertNotIn("validate", second_job["stages"])
        self.assertNotIn("sources", second_job["artifacts"])
        self.assertNotIn("preview", second_job["artifacts"])

    def test_hotspot_accepts_one_timestamp_and_records_event_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            self.record_hotspot(
                job_path,
                (datetime.now(timezone.utc) - timedelta(hours=47)).isoformat(),
                "某机器人公司把机器人部署到汽车总装线",
            )
            history = json.loads(
                (Path(tmp) / "work/a/topic-history.json").read_text(encoding="utf-8")
            )
        self.assertEqual(
            "某机器人公司把机器人部署到汽车总装线",
            history["topics"][-1]["event_focus"],
        )
        self.assertNotIn("evidence", history["topics"][-1])

    def test_hotspot_rejects_older_than_48_hours_and_future_time(self):
        for published_at in (
            datetime.now(timezone.utc) - timedelta(hours=49),
            datetime.now(timezone.utc) + timedelta(minutes=5),
        ):
            with self.subTest(published_at=published_at), tempfile.TemporaryDirectory() as tmp:
                job_path = self.init_job(tmp)
                with self.assertRaisesRegex(pipeline_job.JobError, "48 小时"):
                    self.record_hotspot(job_path, published_at.isoformat(), "事件重点")

    def test_recent_history_is_exposed_without_mechanical_similarity_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            now = datetime.now(timezone.utc).isoformat()
            self.record_hotspot(job_path, now, "WAIC机器人进入汽车产线", "WAIC机器人进入产线")
            second = self.init_job(tmp)
            output = io.StringIO()
            args = pipeline_job.build_parser().parse_args([
                "history", "--job", str(second), "--days", "7",
            ])
            with contextlib.redirect_stdout(output):
                pipeline_job.cmd_history(args)
            history = json.loads(output.getvalue())
            self.assertEqual("WAIC机器人进入汽车产线", history[0]["event_focus"])
            self.record_hotspot(
                second, now, "WAIC机器人进入汽车制造流程", "WAIC机器人走进制造现场"
            )

    def test_prepare_allows_no_sources_and_zero_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, "测试主题")
            job = pipeline_job.load_job(job_path)
            for name, status in (("humanize", "completed"), ("illustrations", "skipped")):
                job["stages"][name] = pipeline_job.stage_record(status, job["created_at"])
            pipeline_job.save_job(job_path, job)
            body = "这是经过核实的完整正文，用来验证无来源文件和无正文图片时仍可继续。" * 65
            (job_path.parent / "article.md").write_text(
                f"# 测试主题进入真实流程\n\n{body}\n", encoding="utf-8"
            )
            result = pipeline_runtime.cmd_prepare(type("Args", (), {"job": str(job_path)})())
        self.assertEqual("finish", result["next"])
        self.assertEqual(0, result["image_count"])

    def test_completed_draft_is_reused_by_run_id_without_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, "测试主题")
            job = pipeline_job.load_job(job_path)
            job["stages"]["draft"] = pipeline_job.stage_record(
                "completed", job["created_at"], details={"run_id": job["run_id"]}
            )
            job["state"] = "drafted"
            pipeline_job.save_job(job_path, job)
            (job_path.parent / "draft-result.json").write_text(json.dumps({
                "account": "a", "action": "draft", "run_id": job["run_id"],
                "draft_media_id": "existing-id",
            }), encoding="utf-8")
            loaded, artifacts = pipeline_runtime.job_paths(job_path)
            result = pipeline_runtime.verified_draft_result(loaded, artifacts)
        self.assertEqual("existing-id", result["draft_media_id"])
        self.assertNotIn("input_sha256", job["stages"]["draft"]["details"])


if __name__ == "__main__":
    unittest.main()
