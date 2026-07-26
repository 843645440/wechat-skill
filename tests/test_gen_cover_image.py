"""封面一条命令：降级链必须一直走到出图为止。

封面和正文图的区别是硬性的——正文图可以 skipped，封面不能，finish 把
`cover/cover.png` 当门禁。所以这里锁三件事：用户已给的封面绝不被覆盖；生图失败
必须自动落到离线兜底；两者都不可用时给出明确的 failed 而不是假装成功。
"""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    ROOT, ".agents", "skills", "wechat-content-pipeline", "scripts",
    "gen_cover_image.py",
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cover = load_module("gen_cover_image", SCRIPT)


def make_job(tmp, *, title="# 测试标题\n\n正文。\n"):
    job_dir = Path(tmp) / "current"
    job_dir.mkdir(parents=True)
    (job_dir / "article.md").write_text(title, encoding="utf-8")
    profiles = Path(tmp) / "profiles.json"
    profiles.write_text(
        json.dumps({"profiles": {"a": {"label": "熵增时刻"}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    job_path = job_dir / "job.json"
    job_path.write_text(json.dumps({
        "job_dir": str(job_dir),
        "profiles_path": str(profiles),
        "account": "a",
        "run_id": "run-cover-test",
        "topic": "测试选题",
        "event_focus": "测试核心",
        "artifacts": {"article": "article.md", "cover": "cover/cover.png"},
    }, ensure_ascii=False), encoding="utf-8")
    return job_path, job_dir


class Args:
    def __init__(self, job, **kw):
        self.job = str(job)
        self.ratio = kw.get("ratio", "16:9")
        self.timeout = kw.get("timeout", 30)
        self.skip_generate = kw.get("skip_generate", False)
        self.record_stage = False


class CoverFallbackChainTests(unittest.TestCase):
    def test_user_provided_cover_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path, job_dir = make_job(tmp)
            cover_path = job_dir / "cover" / "cover.png"
            cover_path.parent.mkdir(parents=True)
            cover_path.write_bytes(b"user-supplied-bytes")

            result = cover.run(Args(job_path))

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["backend"], "user_provided")
            # 关键：原字节一字不动
            self.assertEqual(cover_path.read_bytes(), b"user-supplied-bytes")

    def test_generation_failure_falls_back_to_offline_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path, job_dir = make_job(tmp)
            calls = []

            def failing_generate(*a, **kw):
                calls.append("generate")
                return False, "生图超时（>80s）"

            def ok_fallback(title, kicker, seed, cover_path, ratio):
                calls.append(("fallback", title, kicker))
                Path(cover_path).write_bytes(b"offline-png")
                return True

            orig_gen, orig_fb = cover.try_generate, cover.try_fallback
            cover.try_generate, cover.try_fallback = failing_generate, ok_fallback
            try:
                result = cover.run(Args(job_path))
            finally:
                cover.try_generate, cover.try_fallback = orig_gen, orig_fb

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["backend"], "offline_render")
            self.assertEqual(calls[0], "generate")
            # 兜底拿到的是文章 H1 和账号 label，不是占位符
            self.assertEqual(calls[1][1], "测试标题")
            self.assertEqual(calls[1][2], "熵增时刻")

    def test_both_backends_failing_reports_failed_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path, _ = make_job(tmp)
            orig_gen, orig_fb = cover.try_generate, cover.try_fallback
            cover.try_generate = lambda *a, **kw: (False, "生图超时（>80s）")
            cover.try_fallback = lambda *a, **kw: False
            try:
                result = cover.run(Args(job_path))
            finally:
                cover.try_generate, cover.try_fallback = orig_gen, orig_fb

            self.assertEqual(result["status"], "failed")
            self.assertIn("thumb_media_id", result["reason"])

    def test_skip_generate_goes_straight_to_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path, _ = make_job(tmp)
            calls = []
            orig_gen, orig_fb = cover.try_generate, cover.try_fallback
            cover.try_generate = lambda *a, **kw: (calls.append("generate"), True)[1]

            def ok_fallback(title, kicker, seed, cover_path, ratio):
                Path(cover_path).write_bytes(b"offline-png")
                return True

            cover.try_fallback = ok_fallback
            try:
                result = cover.run(Args(job_path, skip_generate=True))
            finally:
                cover.try_generate, cover.try_fallback = orig_gen, orig_fb

            self.assertEqual(result["backend"], "offline_render")
            self.assertEqual(calls, [], "--skip-generate 时不应调用生图后端")

    def test_title_falls_back_to_topic_when_h1_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path, _ = make_job(tmp, title="没有一级标题的正文\n")
            captured = {}

            def ok_fallback(title, kicker, seed, cover_path, ratio):
                captured["title"] = title
                Path(cover_path).write_bytes(b"png")
                return True

            orig_gen, orig_fb = cover.try_generate, cover.try_fallback
            cover.try_generate = lambda *a, **kw: (False, "生图超时（>80s）")
            cover.try_fallback = ok_fallback
            try:
                cover.run(Args(job_path))
            finally:
                cover.try_generate, cover.try_fallback = orig_gen, orig_fb

            self.assertEqual(captured["title"], "测试选题")


if __name__ == "__main__":
    unittest.main()
