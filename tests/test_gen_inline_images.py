import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    ROOT, ".agents", "skills", "wechat-content-pipeline", "scripts",
    "gen_inline_images.py",
)
RENDER_ARTICLE = os.path.join(
    ROOT, ".agents", "skills", "wechat-content-pipeline", "scripts",
    "render_article.py",
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = load_module("gen_inline_images", SCRIPT)
render_article = load_module("render_article_for_test", RENDER_ARTICLE)


SECTION_A = (
    "这一段专门用来撑到六十个字以上，讲的是机制层面的取舍：谁承担成本、"
    "谁享受收益，以及这件事在流程上具体是怎么转移的，读者需要一个直观的图来理解这套机制。"
)
SECTION_B = (
    "第二段同样足够长，用来讨论对比关系：旧流程和新流程在响应速度、复核成本"
    "和出错率上的差异，这里也值得配一张对比图帮助理解，而不是让读者自己脑补。"
)

ARTICLE_TEXT = f"""# 测试文章标题

## 机制拆解

{SECTION_A}

## 对比分析

{SECTION_B}

## 参考代码

```python
print("hello")
```

## 数据表

| 项目 | 数值 |
| --- | --- |
| A | 1 |
"""


def make_article(tmp_dir, text=ARTICLE_TEXT):
    article_dir = Path(tmp_dir)
    article_path = article_dir / "article.md"
    article_path.write_text(text, encoding="utf-8")
    imgs_dir = article_dir / "imgs"
    return article_path, imgs_dir


def make_args(article_path, imgs_dir, **overrides):
    values = dict(
        article=str(article_path), imgs_dir=str(imgs_dir), max=3,
        seed="", job="", timeout=5,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


class UserProvidedTest(unittest.TestCase):
    def test_existing_reference_in_article_wins_without_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(tmp)
            imgs_dir.mkdir()
            (imgs_dir / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
            text = article_path.read_text(encoding="utf-8")
            text = text.replace(
                "## 机制拆解\n",
                "## 机制拆解\n\n![用户配图](imgs/hero.png)\n",
            )
            article_path.write_text(text, encoding="utf-8")
            before = article_path.read_text(encoding="utf-8")

            called = []
            gen.call_image_backend = lambda *a, **kw: called.append(1) or True
            result = gen.run(make_args(article_path, imgs_dir))

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["backend"], "user_provided")
            self.assertEqual(result["inserted"], 0)
            self.assertEqual(called, [])
            self.assertEqual(article_path.read_text(encoding="utf-8"), before)

    def test_preexisting_images_in_imgs_dir_win_without_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(tmp)
            imgs_dir.mkdir()
            (imgs_dir / "already-there.jpg").write_bytes(b"fake-jpeg")
            before = article_path.read_text(encoding="utf-8")

            called = []
            gen.call_image_backend = lambda *a, **kw: called.append(1) or True
            result = gen.run(make_args(article_path, imgs_dir))

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["backend"], "user_provided")
            self.assertEqual(called, [])
            self.assertEqual(article_path.read_text(encoding="utf-8"), before)


class NoBackendTest(unittest.TestCase):
    def test_formal_report_uses_native_html_even_when_force_generate_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(tmp)
            job_path = Path(tmp) / "job.json"
            job_path.write_text(json.dumps({
                "job_dir": str(Path(tmp)),
                "topic": "某案判决复盘",
                "image_policy": {"inline_enabled": True},
            }), encoding="utf-8")
            (Path(tmp) / "source-dossier.json").write_text("{}", encoding="utf-8")
            called = []
            original = gen.call_image_backend
            gen.call_image_backend = lambda *a, **kw: called.append(1) or True
            try:
                result = gen.run(make_args(
                    article_path, imgs_dir, job=str(job_path), force_generate=True
                ))
            finally:
                gen.call_image_backend = original
            self.assertEqual("skipped", result["status"])
            self.assertEqual("native_html", result["backend"])
            self.assertEqual([], called)

    def test_disabled_job_policy_skips_before_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(tmp)
            job_path = Path(tmp) / "job.json"
            job_path.write_text(json.dumps({
                "image_policy": {"inline_enabled": False}
            }), encoding="utf-8")
            called = []
            gen.call_image_backend = lambda *a, **kw: called.append(1) or True
            result = gen.run(make_args(
                article_path, imgs_dir, job=str(job_path), force_generate=False
            ))
            self.assertEqual("skipped", result["status"])
            self.assertIn("inline_enabled=false", result["reason"])
            self.assertEqual([], called)

    def test_generation_failure_leaves_article_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(tmp)
            before = article_path.read_text(encoding="utf-8")

            gen.call_image_backend = lambda *a, **kw: False
            result = gen.run(make_args(article_path, imgs_dir))

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["backend"], "none")
            self.assertEqual(result["inserted"], 0)
            self.assertIn("reason", result)
            self.assertEqual(article_path.read_text(encoding="utf-8"), before)
            # 不留下任何指向不存在文件的图片引用
            for match in gen.INLINE_IMAGE_REF_RE.finditer(
                article_path.read_text(encoding="utf-8")
            ):
                self.fail("不应该插入任何图片引用: " + match.group(0))

    def test_no_candidate_sections_short_circuits_before_calling_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(
                tmp, text="# 标题\n\n太短了。\n"
            )
            called = []
            gen.call_image_backend = lambda *a, **kw: called.append(1) or True
            result = gen.run(make_args(article_path, imgs_dir))
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(called, [])

    def test_missing_agnes_key_skips_without_inserting(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(tmp)
            before = article_path.read_text(encoding="utf-8")
            env = {key: value for key, value in os.environ.items() if key != "AGNES_API_KEY"}
            with mock.patch.dict(os.environ, env, clear=True):
                result = gen.run(make_args(article_path, imgs_dir))
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["backend"], "none")
            self.assertIn("AGNES_API_KEY", result["reason"])
            self.assertEqual(article_path.read_text(encoding="utf-8"), before)


class DeterminismTest(unittest.TestCase):
    def test_same_article_same_seed_yields_same_positions(self):
        title1, chosen1 = gen.choose_positions(ARTICLE_TEXT, 3)
        title2, chosen2 = gen.choose_positions(ARTICLE_TEXT, 3)
        self.assertEqual(title1, title2)
        headings1 = [(s["heading"], s["insertion_line"]) for s in chosen1]
        headings2 = [(s["heading"], s["insertion_line"]) for s in chosen2]
        self.assertEqual(headings1, headings2)
        # 代码块 / 表格章节必须被排除
        self.assertNotIn("参考代码", [h for h, _ in headings1])
        self.assertNotIn("数据表", [h for h, _ in headings1])
        self.assertLessEqual(len(chosen1), 3)

    def test_max_zero_yields_no_positions(self):
        _, chosen = gen.choose_positions(ARTICLE_TEXT, 0)
        self.assertEqual(chosen, [])


class PathEscapeTest(unittest.TestCase):
    def test_parent_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            imgs_dir = Path(tmp) / "imgs"
            imgs_dir.mkdir()
            with self.assertRaises(gen.PathEscapeError):
                gen.safe_join(imgs_dir, "..", "..", "evil.png")

    def test_normal_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            imgs_dir = Path(tmp) / "imgs"
            imgs_dir.mkdir()
            result = gen.safe_join(imgs_dir, "prompts", "01-inline.md")
            self.assertTrue(str(result).startswith(str(imgs_dir.resolve())))


class SuccessfulGenerationTest(unittest.TestCase):
    def test_generated_image_is_inserted_and_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(tmp)

            def fake_backend(prompt_path, output_path, timeout=None):
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(b"\x89PNG\r\n\x1a\nfake-image-bytes")
                return True

            gen.call_image_backend = fake_backend
            result = gen.run(make_args(article_path, imgs_dir))

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["backend"], "image_generate")
            self.assertEqual(result.get("provider"), "agnes")
            self.assertGreaterEqual(result["inserted"], 1)
            self.assertEqual(len(result["positions"]), result["inserted"])

            new_text = article_path.read_text(encoding="utf-8")
            title, sections = render_article.parse_article(new_text)
            image_blocks = [
                block
                for section in sections
                for block in section["blocks"]
                if block["kind"] == "image"
            ]
            self.assertEqual(len(image_blocks), result["inserted"])
            for block in image_blocks:
                image_path = (article_path.parent / block["src"]).resolve()
                self.assertTrue(image_path.is_file())
                self.assertTrue(str(image_path).startswith(str(imgs_dir.resolve())))

            # 至多 3 张，且没有越权写到 imgs-dir 之外
            self.assertLessEqual(result["inserted"], 3)


class CliTest(unittest.TestCase):
    def test_missing_required_args_exit_nonzero(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT], capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_cli_skips_cleanly_when_no_candidate_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            article_path, imgs_dir = make_article(
                tmp, text="# 标题\n\n这篇文章太短，没有任何值得配图的章节。\n"
            )
            proc = subprocess.run(
                [sys.executable, SCRIPT,
                 "--article", str(article_path),
                 "--imgs-dir", str(imgs_dir)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertEqual(payload["status"], "skipped")
            self.assertEqual(payload["backend"], "none")


if __name__ == "__main__":
    unittest.main()
