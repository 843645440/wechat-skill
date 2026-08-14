"""认知读书：epub 切片与书签。"""

import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/wechat-reading-insight-writer/scripts/read_book.py"
SPEC = importlib.util.spec_from_file_location("read_book", SCRIPT)
read_book = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(read_book)


def _xhtml(body, title="章"):
    return (
        "<?xml version='1.0' encoding='utf-8'?>"
        "<html xmlns='http://www.w3.org/1999/xhtml'><head><title>"
        + title
        + "</title></head><body>"
        + body
        + "</body></html>"
    )


def write_epub(path, chapters):
    """chapters: list of (filename, html body). First file can be front matter."""
    container = (
        "<?xml version='1.0'?>"
        "<container version='1.0' xmlns='urn:oasis:names:tc:opendocument:xmlns:container'>"
        "<rootfiles><rootfile full-path='content.opf' "
        "media-type='application/oebps-package+xml'/></rootfiles></container>"
    )
    opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="id" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>测试之书</dc:title>
    <dc:creator>测试作者</dc:creator>
  </metadata>
  <manifest>
"""
    for index, (name, _) in enumerate(chapters):
        opf += f'    <item id="item{index}" href="{name}" media-type="application/xhtml+xml"/>\n'
    opf += "  </manifest>\n  <spine>\n"
    for index, _ in enumerate(chapters):
        opf += f'    <itemref idref="item{index}"/>\n'
    opf += "  </spine>\n</package>\n"

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("content.opf", opf)
        for name, body in chapters:
            archive.writestr(name, _xhtml(body, title=name))


def long_para(seed, n=400):
    return seed * n


class ReadBookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.epub = self.root / "锤子与钉子_clean.epub"
        write_epub(self.epub, [
            ("titlepage.xhtml", "<p>封面</p>"),
            ("toc.xhtml", "<p>目录</p><p>第一章</p>"),
            ("ch1.xhtml", "<h1>第一章 锤子</h1><p>" + long_para("手里拿着锤子看什么都是钉子。") + "</p>"),
            ("ch2.xhtml", "<h1>第二章 边界</h1><p>" + long_para("这个模型在复杂系统里会失效。") + "</p>"),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_skips_front_matter_and_returns_first_chapter(self):
        extracted = read_book.parse_epub(self.epub)
        fronts = [item for item in extracted["items"] if item["front_matter"]]
        bodies = [item for item in extracted["items"] if not item["front_matter"]]
        self.assertGreaterEqual(len(fronts), 2)
        self.assertGreaterEqual(len(bodies), 2)
        progress = read_book.empty_progress("锤子与钉子", str(self.epub), "测试之书", "测试作者")
        slice_info, _, status = read_book.take_slice(extracted, progress)
        self.assertEqual("ok", status)
        self.assertIn("锤子", slice_info["text"])
        self.assertGreaterEqual(slice_info["chars"], 600)
        self.assertNotIn("目录", slice_info["text"])

    def test_skip_advances_to_next_chapter(self):
        extracted = read_book.parse_epub(self.epub)
        extracted["book_id"] = "锤子与钉子"
        progress = read_book.empty_progress("锤子与钉子", str(self.epub), "测试之书", "测试作者")
        first, progress, _ = read_book.take_slice(extracted, progress)
        second, progress, status = read_book.take_slice(extracted, progress, skip=True)
        self.assertEqual("ok", status)
        self.assertNotEqual(first["spine_index"], second["spine_index"])
        self.assertIn("失效", second["text"])
        self.assertEqual(1, len(progress["skipped"]))

    def test_catalog_and_next_cli(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = read_book.main(["--project-root", str(self.root), "catalog"])
        self.assertEqual(0, rc)
        data = json.loads(buf.getvalue())
        self.assertEqual(1, len(data["books"]))
        self.assertEqual("锤子与钉子", data["books"][0]["book_id"])

    def test_catalog_assets_and_intro_commit(self):
        catalog_dir = self.root / "config"
        (catalog_dir / "reading/covers").mkdir(parents=True)
        (catalog_dir / "reading/intros").mkdir(parents=True)
        (catalog_dir / "reading/covers/锤子与钉子.png").write_bytes(b"x")
        (catalog_dir / "reading/intros/锤子与钉子.md").write_text(
            "这是固定简介。\n", encoding="utf-8"
        )
        (catalog_dir / "reading-books.json").write_text(
            json.dumps({
                "version": 1,
                "accounts": {"a": "锤子与钉子"},
                "books": {
                    "锤子与钉子": {
                        "title": "锤子与钉子",
                        "author": "测试作者",
                        "cover": "config/reading/covers/锤子与钉子.png",
                        "intro": "config/reading/intros/锤子与钉子.md",
                    }
                },
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        catalog = read_book.load_catalog(self.root)
        self.assertEqual("锤子与钉子", read_book.account_book_id(catalog, "a"))
        assets = read_book.catalog_assets(self.root, "锤子与钉子")
        self.assertIn("固定简介", assets["intro_text"])
        self.assertTrue(assets["cover"].endswith("锤子与钉子.png"))

        job_dir = self.root / "work/a/current"
        job_dir.mkdir(parents=True)
        job_path = job_dir / "job.json"
        job_path.write_text(json.dumps({
            "job_dir": str(job_dir),
            "project_root": str(self.root),
            "account": "a",
            "reading": {"book_id": "锤子与钉子", "piece": "intro"},
        }, ensure_ascii=False), encoding="utf-8")
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            rc = read_book.main([
                "--project-root", str(self.root), "commit",
                "--job", str(job_path), "--claim", "总介绍",
            ])
        self.assertEqual(0, rc)
        progress = json.loads(
            (self.root / "work/library/锤子与钉子.json").read_text(encoding="utf-8")
        )
        self.assertTrue(progress["intro_done"])

    def test_commit_records_claim(self):
        with redirect_stdout(io.StringIO()):
            read_book.main([
                "--project-root", str(self.root), "next", "--book", str(self.epub),
            ])
        with redirect_stdout(io.StringIO()):
            rc = read_book.main([
                "--project-root", str(self.root), "commit",
                "--book", str(self.epub), "--claim", "手里只有锤子时看什么都是钉子",
            ])
        self.assertEqual(0, rc)
        progress = json.loads(
            (self.root / "work/library/锤子与钉子.json").read_text(encoding="utf-8")
        )
        self.assertIn("手里只有锤子时看什么都是钉子", progress["used_claims"])


if __name__ == "__main__":
    unittest.main()
