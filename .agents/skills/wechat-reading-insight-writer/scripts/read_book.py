#!/usr/bin/env python3
"""按书签从 epub 取下一刀正文，供认知读书流水线当信源。

职责只到「切片 + 书签」。值不值得写由 agent 判断：没模型就 --skip 再取下一刀。
进度写在 work/library/，不进 work/<account>/current/——init 清空当期工作区不会丢书签。
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET


FRONT_HREF_RE = re.compile(
    r"titlepage|toc\.|nav\.|/nav|cover|copyright|colophon|dedication|contents",
    re.I,
)
FRONT_HEADING_RE = re.compile(
    r"^(目录|版权(?:信息|页)?|献词|出版说明|再版说明|译者(?:序|前言)|"
    r"编委会|作者简介|内容简介|封面|扉页|COPYRIGHT)",
    re.I,
)
SKIP_TAGS = frozenset({"script", "style", "head"})
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
MIN_BODY_CHARS = 80
MIN_SLICE_CHARS = 600
TARGET_SLICE_CHARS = 2500
MAX_SLICE_CHARS = 3500
PROGRESS_VERSION = 1
CATALOG_REL = "config/reading-books.json"


class BookError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def visible_len(text):
    return len(re.sub(r"\s+", "", text or ""))


def html_to_text(raw):
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        text = re.sub(r"<[^>]+>", "\n", raw)
        return re.sub(r"\n{3,}", "\n\n", html_lib.unescape(text)).strip()
    text = "".join(parser.parts)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def catalog_path(project_root):
    return Path(project_root) / CATALOG_REL


def load_catalog(project_root):
    path = catalog_path(project_root)
    if not path.is_file():
        return {"version": 1, "accounts": {}, "books": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BookError(f"无法读取读书配置 {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("books"), dict):
        raise BookError("读书配置格式不受支持：需要 books 对象")
    data.setdefault("accounts", {})
    return data


def account_book_id(catalog, account):
    accounts = catalog.get("accounts") or {}
    value = accounts.get(account)
    return value.strip() if isinstance(value, str) and value.strip() else None


def book_entry(catalog, book_id):
    if not book_id:
        return None
    books = catalog.get("books") or {}
    if book_id in books and isinstance(books[book_id], dict):
        return dict(books[book_id], book_id=book_id)
    for key, entry in books.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("title") == book_id or key in str(book_id):
            return dict(entry, book_id=key)
    return None


def resolve_under_root(project_root, rel):
    if not rel:
        return None
    path = Path(rel)
    if not path.is_absolute():
        path = Path(project_root) / rel
    return path if path.is_file() else None


def catalog_assets(project_root, book_id):
    catalog = load_catalog(project_root)
    entry = book_entry(catalog, book_id)
    if not entry:
        return None
    intro_path = resolve_under_root(project_root, entry.get("intro"))
    cover_path = resolve_under_root(project_root, entry.get("cover"))
    intro_text = intro_path.read_text(encoding="utf-8") if intro_path else ""
    return {
        "book_id": entry.get("book_id") or book_id,
        "title": entry.get("title") or book_id,
        "author": entry.get("author") or "",
        "english_title": entry.get("english_title") or "",
        "cover": str(cover_path) if cover_path else "",
        "intro_file": str(intro_path) if intro_path else "",
        "intro_text": intro_text,
    }


def book_id_from_path(path):
    stem = Path(path).stem
    stem = re.sub(r"_clean$", "", stem)
    stem = re.sub(r"^\d{4}-\d{2}", "", stem)
    stem = re.sub(r"-?\d{10,13}$", "", stem)
    stem = stem.replace("《", "").replace("》", "")
    parts = [p.strip() for p in re.split(r"[-_,，、.]+", stem) if p.strip()]
    cjk_parts = [p for p in parts if CJK_RE.search(p)]
    if cjk_parts:
        return min(cjk_parts, key=len)[:48]
    return (parts[-1] if parts else "book")[:48]


def library_dir(project_root):
    path = Path(project_root) / "work" / "library"
    path.mkdir(parents=True, exist_ok=True)
    return path


def progress_path(project_root, book_id):
    return library_dir(project_root) / f"{book_id}.json"


def extract_cache_path(project_root, book_id):
    return library_dir(project_root) / f"{book_id}.extract.json"


def discover_epubs(project_root):
    root = Path(project_root)
    found = []
    for folder in (root, root / "books"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.epub")):
            if path.name.startswith("."):
                continue
            found.append(path)
    # 同书的 _clean 优先，去掉非 clean 双胞胎
    by_id = {}
    for path in found:
        key = book_id_from_path(path)
        current = by_id.get(key)
        if current is None or "_clean" in path.stem and "_clean" not in current.stem:
            by_id[key] = path
    return by_id


def resolve_book(project_root, book):
    if not book:
        return None
    raw = Path(book)
    if raw.is_file():
        return raw.resolve()
    candidate = Path(project_root) / book
    if candidate.is_file():
        return candidate.resolve()
    catalog = discover_epubs(project_root)
    if book in catalog:
        return catalog[book].resolve()
    matches = [path for key, path in catalog.items() if book in key or book in path.name]
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        available = "、".join(sorted(catalog)) or "（工作区没有 epub）"
        raise BookError(f"找不到书 {book!r}。已登记：{available}")
    names = "、".join(path.name for path in matches)
    raise BookError(f"书名 {book!r} 匹配到多本：{names}")


def _local_name(tag):
    return tag.rsplit("}", 1)[-1] if tag else ""


def parse_epub(epub_path):
    path = Path(epub_path)
    if not path.is_file():
        raise BookError(f"不是文件：{path}")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise BookError(f"不是合法 epub：{path}") from exc
    with archive:
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
        except (KeyError, ET.ParseError) as exc:
            raise BookError("epub 缺少 META-INF/container.xml") from exc
        opf_href = None
        for item in container.iter():
            if _local_name(item.tag) == "rootfile":
                opf_href = item.get("full-path")
                break
        if not opf_href:
            raise BookError("container.xml 没有 rootfile")
        opf_dir = str(Path(opf_href).parent)
        if opf_dir == ".":
            opf_dir = ""
        try:
            package = ET.fromstring(archive.read(opf_href))
        except (KeyError, ET.ParseError) as exc:
            raise BookError(f"无法读取 {opf_href}") from exc

        title = ""
        author = ""
        manifest = {}
        spine = []
        for item in package.iter():
            name = _local_name(item.tag)
            if name == "title" and not title:
                title = "".join(item.itertext()).strip()
            elif name == "creator" and not author:
                author = "".join(item.itertext()).strip()
            elif name == "item":
                manifest[item.get("id")] = item.get("href") or ""
            elif name == "itemref":
                spine.append(item.get("idref"))

        items = []
        for index, item_id in enumerate(spine):
            href = manifest.get(item_id) or ""
            if not href:
                continue
            full = href if not opf_dir else str(Path(opf_dir) / href)
            full = full.replace("\\", "/")
            media = (href or "").lower()
            if not media.endswith((".xhtml", ".html", ".htm")):
                continue
            try:
                raw = archive.read(full).decode("utf-8", "ignore")
            except KeyError:
                continue
            text = html_to_text(raw)
            heading = _first_heading(text)
            items.append({
                "index": index,
                "id": item_id,
                "href": href,
                "heading": heading,
                "text": text,
                "chars": visible_len(text),
                "front_matter": is_front_matter(href, item_id, heading, text),
            })
    return {
        "title": title or path.stem,
        "author": author,
        "source": str(path),
        "items": items,
    }


def _first_heading(text):
    for line in text.splitlines():
        line = line.strip()
        if 2 <= visible_len(line) <= 40:
            return line
    return ""


def is_front_matter(href, item_id, heading, text):
    blob = f"{href} {item_id}"
    if FRONT_HREF_RE.search(blob):
        return True
    if heading and FRONT_HEADING_RE.match(re.sub(r"\s+", "", heading)):
        return True
    if visible_len(text) < MIN_BODY_CHARS:
        return True
    return False


def load_or_build_extract(project_root, epub_path):
    book_id = book_id_from_path(epub_path)
    cache = extract_cache_path(project_root, book_id)
    source = str(Path(epub_path).resolve())
    mtime = os.path.getmtime(source)
    if cache.is_file():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        if (
            isinstance(data, dict)
            and data.get("source") == source
            and data.get("mtime") == mtime
            and data.get("items")
        ):
            return data
    extracted = parse_epub(source)
    extracted["book_id"] = book_id
    extracted["mtime"] = mtime
    cache.write_text(
        json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return extracted


def empty_progress(book_id, source, title, author):
    return {
        "version": PROGRESS_VERSION,
        "book_id": book_id,
        "title": title,
        "author": author,
        "source": source,
        "spine_index": 0,
        "char_offset": 0,
        "finished": False,
        "intro_done": False,
        "used_claims": [],
        "skipped": [],
        "updated_at": "",
    }


def load_progress(project_root, book_id, extracted):
    path = progress_path(project_root, book_id)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BookError(f"进度文件损坏：{path}") from exc
        if isinstance(data, dict) and data.get("book_id") == book_id:
            return data
    return empty_progress(
        book_id, extracted["source"], extracted["title"], extracted.get("author") or "",
    )


def save_progress(project_root, progress):
    import datetime as dt
    progress["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    path = progress_path(project_root, progress["book_id"])
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def next_body_item(items, spine_index):
    for item in items:
        if (
            item["index"] >= spine_index
            and not item["front_matter"]
            and item["chars"] >= MIN_SLICE_CHARS
        ):
            return item
    return None


def take_slice(extracted, progress, *, skip=False):
    items = extracted["items"]
    spine = int(progress.get("spine_index") or 0)
    offset = int(progress.get("char_offset") or 0)
    if skip:
        current = next_body_item(items, spine)
        if current is None:
            progress["finished"] = True
            return None, progress, "finished"
        progress.setdefault("skipped", []).append({
            "spine_index": current["index"],
            "heading": current.get("heading") or "",
            "reason": "no_model",
        })
        nxt = next_body_item(items, current["index"] + 1)
        if nxt is None:
            progress["spine_index"] = current["index"] + 1
            progress["char_offset"] = 0
            progress["finished"] = True
            return None, progress, "finished"
        spine, offset = nxt["index"], 0
        progress["spine_index"] = spine
        progress["char_offset"] = 0

    if progress.get("finished"):
        return None, progress, "finished"

    item = next_body_item(items, spine)
    if item is None:
        progress["finished"] = True
        return None, progress, "finished"
    if item["index"] != spine:
        offset = 0
        spine = item["index"]

    text = item["text"]
    # offset 按可见字符计，映射回原文切片
    compact_prefix = 0
    start = 0
    if offset > 0:
        for index, char in enumerate(text):
            if not char.isspace():
                compact_prefix += 1
                if compact_prefix >= offset:
                    start = index + 1
                    break
    remainder = text[start:].lstrip()
    if visible_len(remainder) < MIN_BODY_CHARS:
        nxt = next_body_item(items, item["index"] + 1)
        if nxt is None:
            progress["finished"] = True
            progress["spine_index"] = item["index"] + 1
            progress["char_offset"] = visible_len(text)
            return None, progress, "finished"
        progress["spine_index"] = nxt["index"]
        progress["char_offset"] = 0
        return take_slice(extracted, progress, skip=False)

    chunk, consumed = _cut_unit(remainder)
    end_offset = offset + consumed
    reached_end = visible_len(remainder) <= consumed + 8

    if reached_end:
        nxt = next_body_item(items, item["index"] + 1)
        next_spine = nxt["index"] if nxt else item["index"] + 1
        next_offset = 0
        finished = nxt is None
    else:
        next_spine = item["index"]
        next_offset = end_offset
        finished = False

    slice_info = {
        "spine_index": item["index"],
        "href": item["href"],
        "heading": item.get("heading") or "",
        "text": chunk,
        "chars": visible_len(chunk),
        "start_offset": offset,
        "end_offset": end_offset,
        "next_spine_index": next_spine,
        "next_char_offset": next_offset,
        "would_finish": finished,
        "stop_reason": "chapter_end" if reached_end else "max_unit",
    }
    return slice_info, progress, "ok"


def _visible_prefix(text, limit):
    count = 0
    out = []
    for char in text:
        out.append(char)
        if not char.isspace():
            count += 1
            if count >= limit:
                break
    return "".join(out).rstrip()


def _cut_unit(text):
    """取一个论证单元：优先在目标字数附近的段落边界切开，硬上限 MAX。"""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    gathered = []
    chars = 0
    for para in paragraphs:
        extra = visible_len(para)
        if gathered and chars >= TARGET_SLICE_CHARS:
            break
        if extra > MAX_SLICE_CHARS:
            need = max(TARGET_SLICE_CHARS - chars, MIN_SLICE_CHARS)
            gathered.append(_visible_prefix(para, min(need, MAX_SLICE_CHARS)))
            break
        if gathered and chars + extra > MAX_SLICE_CHARS:
            if chars < MIN_SLICE_CHARS:
                gathered.append(_visible_prefix(para, MIN_SLICE_CHARS - chars))
            break
        gathered.append(para)
        chars += extra
        if chars >= TARGET_SLICE_CHARS:
            break
    if not gathered:
        gathered = [_visible_prefix(text, MAX_SLICE_CHARS)]
    chunk = "\n\n".join(gathered).strip()
    return chunk, visible_len(chunk)


def render_slice_markdown(extracted, slice_info):
    title = extracted.get("title") or ""
    author = extracted.get("author") or ""
    heading = slice_info.get("heading") or ""
    lines = [
        f"# 切片 · {title}",
        "",
        f"- 书：《{title}》",
        f"- 作者：{author}",
        f"- 书脊：{slice_info['spine_index']}（{slice_info.get('href') or ''}）",
        f"- 本节标题：{heading}",
        f"- 字符：{slice_info['start_offset']}–{slice_info['end_offset']}（{slice_info['chars']} 字）",
        "",
        "以下正文是本篇唯一允许引用的书内原文。不许编书里没有的原话。",
        "",
        "## 正文",
        "",
        slice_info["text"].rstrip(),
        "",
    ]
    return "\n".join(lines)


def render_brief_skeleton(extracted, slice_info):
    title = extracted.get("title") or ""
    return "\n".join([
        "# Brief",
        "",
        "## 主题",
        f"（用自己的判断写，不要写成「读《{title}》」）",
        "",
        "## 思路",
        "- 我原来默认：",
        "- 这段给出的机制/命名（引用原句）：",
        "- 我会在哪个具体场合用错：",
        "",
        "## 必须保留",
        "- 至少一句来自下方切片的原话",
        "",
        "## 不要写",
        "- 不要写成书评、读后感、全书导读、章节串讲、作者生平、推荐指数",
        "- 不要用「这本书告诉我们」开场",
        "",
        f"## 切片",
        f"- 书：《{title}》 / 书脊 {slice_info['spine_index']} / {slice_info.get('heading') or ''}",
        "",
    ])


def apply_catalog_to_job(job, project_root, book_id, progress=None):
    """把配置里的固定简介/封面写进 job.reading，并落盘 book-intro.md。"""
    reading = job.setdefault("reading", {})
    assets = catalog_assets(project_root, book_id) or {}
    if assets:
        reading["book_id"] = assets["book_id"]
        reading["catalog_title"] = assets["title"]
        reading["catalog_author"] = assets["author"]
        reading["english_title"] = assets["english_title"]
        if assets.get("cover"):
            reading["cover"] = assets["cover"]
        if assets.get("intro_file"):
            reading["intro_file"] = assets["intro_file"]
        job_dir = job.get("job_dir")
        if job_dir and assets.get("intro_text"):
            intro_rel = "book-intro.md"
            Path(job_dir).mkdir(parents=True, exist_ok=True)
            (Path(job_dir) / intro_rel).write_text(
                assets["intro_text"], encoding="utf-8"
            )
            reading["intro_work_file"] = intro_rel
            job.setdefault("artifacts", {})["book_intro"] = intro_rel
    intro_done = bool((progress or {}).get("intro_done"))
    reading["piece"] = "serial" if intro_done else "intro"
    return reading


def attach_slice_to_job(job_path, extracted, slice_info, progress_file):
    path = Path(job_path)
    job = json.loads(path.read_text(encoding="utf-8"))
    job_dir = Path(job["job_dir"])
    slice_rel = "reading-slice.md"
    brief_rel = "user-brief.skeleton.md"
    (job_dir / slice_rel).write_text(
        render_slice_markdown(extracted, slice_info), encoding="utf-8"
    )
    (job_dir / brief_rel).write_text(
        render_brief_skeleton(extracted, slice_info), encoding="utf-8"
    )
    job["genre"] = "reading"
    job["reading"] = {
        "book_id": extracted["book_id"],
        "title": extracted.get("title"),
        "author": extracted.get("author"),
        "source": extracted.get("source"),
        "slice": slice_info,
        "slice_file": slice_rel,
        "progress_file": str(progress_file),
        "committed": False,
    }
    project_root = job.get("project_root") or str(path.parents[2])
    apply_catalog_to_job(job, project_root, extracted["book_id"])
    artifacts = job.setdefault("artifacts", {})
    artifacts["reading_slice"] = slice_rel
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return job


def pick_default_book(project_root):
    catalog = discover_epubs(project_root)
    if not catalog:
        raise BookError("工作区根目录和 books/ 下都没有 .epub")
    unfinished = []
    for book_id, path in catalog.items():
        extracted = load_or_build_extract(project_root, path)
        progress = load_progress(project_root, book_id, extracted)
        if not progress.get("finished"):
            unfinished.append((book_id, path, progress))
    if len(unfinished) == 1:
        return unfinished[0][1]
    if len(unfinished) > 1:
        names = "、".join(item[0] for item in unfinished)
        raise BookError(f"有多本未读完（{names}），请用 --book 指定一本")
    names = "、".join(sorted(catalog))
    raise BookError(f"登记的书都读完了。已有：{names}。换一本或指定 --book")


def cmd_catalog(args):
    catalog = discover_epubs(args.project_root)
    rows = []
    for book_id, path in catalog.items():
        extracted = load_or_build_extract(args.project_root, path)
        progress = load_progress(args.project_root, book_id, extracted)
        rows.append({
            "book_id": book_id,
            "title": extracted.get("title"),
            "author": extracted.get("author"),
            "path": str(path),
            "finished": bool(progress.get("finished")),
            "spine_index": progress.get("spine_index", 0),
            "used_claims": len(progress.get("used_claims") or []),
        })
    print(json.dumps({"books": rows}, ensure_ascii=False, indent=2))


def _require_book(args):
    if args.book:
        return resolve_book(args.project_root, args.book)
    if args.job:
        job = json.loads(Path(args.job).read_text(encoding="utf-8"))
        reading = job.get("reading") or {}
        source = reading.get("source")
        if source and Path(source).is_file():
            return Path(source)
        if reading.get("book_id"):
            return resolve_book(args.project_root, reading["book_id"])
    return pick_default_book(args.project_root)


def cmd_next(args):
    epub = _require_book(args)
    extracted = load_or_build_extract(args.project_root, epub)
    book_id = extracted["book_id"]
    progress = load_progress(args.project_root, book_id, extracted)
    slice_info, progress, status = take_slice(extracted, progress, skip=args.skip)
    progress_file = save_progress(args.project_root, progress)
    payload = {
        "status": status,
        "book_id": book_id,
        "title": extracted.get("title"),
        "author": extracted.get("author"),
        "progress_file": str(progress_file),
        "finished": bool(progress.get("finished")),
    }
    if status == "finished" or slice_info is None:
        payload["next"] = "这本书已经读完。换一本再 init --book，或结束本轮。"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    payload["slice"] = {
        "spine_index": slice_info["spine_index"],
        "heading": slice_info.get("heading"),
        "chars": slice_info["chars"],
        "start_offset": slice_info["start_offset"],
        "end_offset": slice_info["end_offset"],
        "stop_reason": slice_info["stop_reason"],
    }
    if args.job:
        job = attach_slice_to_job(args.job, extracted, slice_info, progress_file)
        job_dir = job["job_dir"]
        payload["slice_path"] = os.path.join(job_dir, "reading-slice.md")
        payload["brief_skeleton"] = os.path.join(job_dir, "user-brief.skeleton.md")
        payload["next"] = (
            f"读 {payload['slice_path']}。"
            "有可反驳主张 + 论证 + 你会用错的场合 → 按 brief_skeleton 写 user-brief.md；"
            "没有就再跑本命令并加 --skip。"
        )
    else:
        payload["text"] = slice_info["text"]
        payload["next"] = "把这段当信源。没模型就 --skip。"
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_commit(args):
    claim = (args.claim or "").strip()
    if not claim:
        raise BookError("commit 必须带 --claim（本篇用过的那个主张，一句话）")
    if args.job:
        job_path = Path(args.job)
        job = json.loads(job_path.read_text(encoding="utf-8"))
        reading = job.get("reading") or {}
        slice_info = reading.get("slice") or {}
        source = reading.get("source")
        book_id = reading.get("book_id")
        piece = reading.get("piece") or "serial"
        if piece == "intro":
            if not book_id:
                raise BookError("job 里没有 book_id，无法记下简介已写")
            progress = {"version": PROGRESS_VERSION, "book_id": book_id}
            existing = progress_path(args.project_root, book_id)
            if existing.is_file():
                try:
                    progress = json.loads(existing.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            progress["intro_done"] = True
            claims = progress.setdefault("used_claims", [])
            if claim not in claims:
                claims.append(claim)
            progress_file = save_progress(args.project_root, progress)
        else:
            if not source:
                raise BookError("job 里没有 reading 切片，先跑 next")
            extracted = load_or_build_extract(args.project_root, source)
            progress = load_progress(args.project_root, extracted["book_id"], extracted)
            progress["spine_index"] = slice_info.get(
                "next_spine_index", progress.get("spine_index", 0)
            )
            progress["char_offset"] = slice_info.get("next_char_offset", 0)
            progress["finished"] = bool(slice_info.get("would_finish"))
            claims = progress.setdefault("used_claims", [])
            if claim not in claims:
                claims.append(claim)
            progress_file = save_progress(args.project_root, progress)
        reading["committed"] = True
        reading["claim"] = claim
        job["reading"] = reading
        job_path.write_text(
            json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        epub = _require_book(args)
        extracted = load_or_build_extract(args.project_root, epub)
        progress = load_progress(args.project_root, extracted["book_id"], extracted)
        claims = progress.setdefault("used_claims", [])
        if claim not in claims:
            claims.append(claim)
        progress_file = save_progress(args.project_root, progress)
    print(json.dumps({
        "status": "ok",
        "claim": claim,
        "progress_file": str(progress_file),
        "spine_index": progress.get("spine_index"),
        "char_offset": progress.get("char_offset"),
        "finished": bool(progress.get("finished")),
        "used_claims": progress.get("used_claims"),
    }, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description="按书签从 epub 取下一刀正文")
    parser.add_argument("--project-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="列出工作区内的书和进度")
    catalog.set_defaults(func=cmd_catalog)

    nxt = sub.add_parser("next", help="从书签取下一刀；--skip 丢掉当前刀再取")
    nxt.add_argument("--book", help="epub 路径或 book_id")
    nxt.add_argument("--job", help="写入 reading-slice.md 并回写 job.json")
    nxt.add_argument("--skip", action="store_true", help="当前刀没有可写的模型，往后推")
    nxt.set_defaults(func=cmd_next)

    commit = sub.add_parser("commit", help="成稿后推进书签并记下用过的主张")
    commit.add_argument("--book")
    commit.add_argument("--job")
    commit.add_argument("--claim", required=True, help="本篇用过的主张，一句话")
    commit.set_defaults(func=cmd_commit)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.project_root = os.path.abspath(args.project_root)
    try:
        args.func(args)
    except BookError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
