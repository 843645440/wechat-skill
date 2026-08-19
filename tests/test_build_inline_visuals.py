import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/wechat-content-pipeline/scripts/build_inline_visuals.py"
SPEC = importlib.util.spec_from_file_location("build_inline_visuals_for_test", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


ARTICLE = """# 某案公开事实复盘

这篇文章只根据公开材料整理。

## 案件背景

公开材料显示，相关问题在多年经营过程中逐步形成。

## 调查与抓捕

有关机关发布的通报记录了调查推进和人员到案过程。

## 审理与判决

人民法院公开材料载明了审理结果和已经确认的法律责任。

## 治理影响

后续治理措施针对公开材料中暴露的制度问题展开。
"""


def make_job(tmp, formal=True):
    job_dir = Path(tmp) / "current"
    job_dir.mkdir()
    (job_dir / "article.md").write_text(ARTICLE, encoding="utf-8")
    if formal:
        (job_dir / "source-dossier.json").write_text("{}", encoding="utf-8")
    stages = {
        name: builder.pipeline_job.stage_record("pending")
        for name in builder.pipeline_job.STAGES
    }
    stages["format"]["details"] = {"theme": "formal-brief" if formal else "plain-white"}
    stages["write"] = builder.pipeline_job.stage_record("running")
    stages["humanize"] = builder.pipeline_job.stage_record("completed")
    job = {
        "schema_version": 5,
        "created_at": "2026-08-19T00:00:00+00:00",
        "updated_at": "2026-08-19T00:00:00+00:00",
        "job_dir": str(job_dir),
        "account": "b",
        "run_id": "inline-test",
        "topic": "某案判决复盘" if formal else "普通观点文章",
        "event_focus": "公开事实整理" if formal else "普通观点文章核心",
        "article_shape": {
            "structure_id": "mechanism-ladder",
            "opening_type": "scene",
            "ending_type": "unresolved-question",
        },
        "artifacts": {
            "article": "article.md",
            "inline_visuals": "inline-visuals.json",
            "cover": "cover/cover.png",
            "illustrations": "imgs",
            "html": "article.html",
            "draft_result": "draft-result.json",
        },
        "stages": stages,
    }
    job_path = job_dir / "job.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    return job_path, job_dir


class BuildInlineVisualsTests(unittest.TestCase):
    def test_formal_report_builds_one_evidence_bound_process_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path, job_dir = make_job(tmp, formal=True)
            result = builder.run(job_path)
            plan = json.loads((job_dir / "inline-visuals.json").read_text(encoding="utf-8"))

            self.assertEqual("formal-report", result["content_mode"])
            self.assertEqual(1, result["module_count"])
            self.assertEqual(["process"], result["kinds"])
            module = plan["modules"][0]
            self.assertEqual("公开事实脉络", module["title"])
            for evidence in module["evidence"]:
                self.assertIn(evidence, " ".join(ARTICLE.split()))
            validation = builder.load_validator().validate_plan(
                plan, ARTICLE, set(builder.render_article.THEMES)
            )
            self.assertEqual(1, validation["module_count"])

            title, sections = builder.render_article.parse_article(ARTICLE)
            html = builder.render_article.render_document(
                title, sections, plan, builder.render_article.THEMES["formal-brief"]
            )
            self.assertIn("公开事实脉络", html)

    def test_ordinary_article_gets_empty_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path, job_dir = make_job(tmp, formal=False)
            result = builder.run(job_path)
            plan = json.loads((job_dir / "inline-visuals.json").read_text(encoding="utf-8"))
            self.assertEqual("editorial", result["content_mode"])
            self.assertEqual([], plan["modules"])
            self.assertIn("gen_inline_images.py", result["next_command"])

    def test_formal_plan_flows_through_renderer_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path, job_dir = make_job(tmp, formal=True)
            builder.run(job_path)
            output = job_dir / "article.html"
            renderer_path = (
                ROOT / ".agents/skills/wechat-content-pipeline/scripts/render_article.py"
            )
            proc = subprocess.run(
                [
                    sys.executable, str(renderer_path),
                    "--article", str(job_dir / "article.md"),
                    "--theme", "formal-brief",
                    "--inline-plan", str(job_dir / "inline-visuals.json"),
                    "--output", str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(1, payload["module_count"])
            self.assertEqual(["process"], payload["module_kinds"])
            self.assertIn("公开事实脉络", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
