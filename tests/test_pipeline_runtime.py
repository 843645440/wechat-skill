import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_PATH = os.path.join(
    ROOT, ".agents", "skills", "wechat-content-pipeline", "scripts", "pipeline_runtime.py"
)
SPEC = importlib.util.spec_from_file_location("wechat_pipeline_runtime", RUNTIME_PATH)
pipeline_runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline_runtime)


class PipelineRuntimeTests(unittest.TestCase):
    def make_job(self, tmp):
        job_dir = Path(tmp) / "a" / "current"
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
            "schema_version": 4,
            "created_at": created,
            "updated_at": created,
            "project_root": ROOT,
            "profiles_path": os.path.join(ROOT, "config", "wechat-content-profiles.json"),
            "job_dir": str(job_dir),
            "account": "a",
            "topic": "Google把代码执行接进研究工具",
            "topic_source": "provided",
            "state": "initialized",
            "artifacts": {
                "article": "article.md", "sources": "sources.md",
                "inline_visuals": "inline-visuals.json", "cover": "cover/cover.png",
                "html": "article.html", "preview": "article_preview.html",
                "draft_result": "draft-result.json",
            },
            "stages": stages,
        }
        path = job_dir / "job.json"
        path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        return path

    def test_begin_and_prepare_lock_runtime_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            pipeline_runtime.cmd_begin(type("Args", (), {"job": str(job_path)})())
            job = pipeline_runtime.pipeline_job.load_job(job_path)
            self.assertEqual("running", job["stages"]["write"]["status"])
            self.assertIsNotNone(job["stages"]["write"]["started_at"])

            job_dir = job_path.parent
            body = (
                "代码执行进入研究工具后，教师减少重复整理，也要核对结果。"
                "学生获得更快反馈，学校需要管理权限、日志与责任边界。"
            ) * 18
            (job_dir / "article.md").write_text(
                "# Google让研究工具运行代码，教师先承担核验责任\n\n"
                f"{body}\n\n"
                "## 工具进入真实流程\n\n"
                f"{body}\n",
                encoding="utf-8",
            )
            (job_dir / "sources.md").write_text(
                "测试使用非时效性示例，不包含外部数据。\n", encoding="utf-8"
            )
            result = pipeline_runtime.cmd_prepare(
                type("Args", (), {"job": str(job_path)})()
            )
            self.assertEqual("write-inline-plan", result["next"])
            self.assertGreaterEqual(result["body_chars"], pipeline_runtime.MIN_BODY_CHARS)
            self.assertLessEqual(result["body_chars"], pipeline_runtime.MAX_BODY_CHARS)
            self.assertEqual(
                {"version": 1, "theme": result["theme"], "modules": []},
                result["plan_schema"],
            )
            self.assertTrue(Path(result["plan"]).is_file())
            self.assertEqual(
                {"version": 1, "theme": result["theme"], "modules": []},
                json.loads(Path(result["plan"]).read_text(encoding="utf-8")),
            )
            self.assertIn(result["theme"], pipeline_runtime.pipeline_job.THEME_RE.findall(
                Path(ROOT, "references", "theme-index.md").read_text(encoding="utf-8")
            ))
            self.assertIn(
                result["template"],
                ("signal-editorial", "night-signal", "redaction-poster"),
            )
            self.assertTrue(Path(result["cover_spec"]).is_file())

    def test_prepare_rejects_short_article(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            pipeline_runtime.cmd_begin(type("Args", (), {"job": str(job_path)})())
            job_dir = job_path.parent
            (job_dir / "article.md").write_text(
                "# 标题足够具体且不超过三十二字限制\n\n正文太短。\n",
                encoding="utf-8",
            )
            (job_dir / "sources.md").write_text("来源\n", encoding="utf-8")
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "正文字数"):
                pipeline_runtime.cmd_prepare(type("Args", (), {"job": str(job_path)})())

    def test_prepare_rejects_overlong_article(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.make_job(tmp)
            pipeline_runtime.cmd_begin(type("Args", (), {"job": str(job_path)})())
            job_dir = job_path.parent
            body = "这是用于触发字数上限的填充正文。" * 300
            (job_dir / "article.md").write_text(
                f"# 标题足够具体且不超过三十二字限制\n\n{body}\n",
                encoding="utf-8",
            )
            (job_dir / "sources.md").write_text("来源\n", encoding="utf-8")
            with self.assertRaisesRegex(pipeline_runtime.RuntimeFailure, "正文字数"):
                pipeline_runtime.cmd_prepare(type("Args", (), {"job": str(job_path)})())

    def test_count_body_chars_ignores_title_and_markdown_noise(self):
        article = (
            "# 标题不计入\n\n"
            "## 小节\n\n"
            "这是**正文**内容，共若干汉字。\n"
        )
        self.assertEqual(
            pipeline_runtime.count_body_chars(article),
            len("小节这是正文内容，共若干汉字。"),
        )

    def test_runtime_only_exposes_draft_not_public_publish(self):
        parser = pipeline_runtime.build_parser()
        args = parser.parse_args(["finish", "--job", "/tmp/job.json", "--dry-run"])
        self.assertIs(args.dry_run, True)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["publish", "--job", "/tmp/job.json"])

    def test_relative_config_resolves_from_project_root(self):
        result = pipeline_runtime.resolve_config("wechat-accounts.json", ROOT)
        self.assertEqual(Path(ROOT, "wechat-accounts.json").resolve(), result)

    def test_transient_error_match_is_narrow(self):
        self.assertRegex("SSL unexpected EOF", pipeline_runtime.TRANSIENT_RE)
        self.assertNotRegex("HTML 校验失败", pipeline_runtime.TRANSIENT_RE)


if __name__ == "__main__":
    unittest.main()
