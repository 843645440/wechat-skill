#!/usr/bin/env python3
"""Build a valid cover specification from the final article title."""

import argparse
import hashlib
import itertools
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import render_cover


BREAK_AFTER = set("，。！？：；、—")
BAD_LINE_START = set("，。！？：；、）】》」』—")
ASCII_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")
CJK_RUN = re.compile(r"[\u3400-\u9fff]{2,}")
TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
SENTENCE_RE = re.compile(r".+?[。！？；](?:\s|$)|.+$")


class BuildError(RuntimeError):
    pass


def normalized(value):
    return " ".join(value.split())


def split_title(title):
    title = normalized(title)
    if not title:
        raise BuildError("标题不能为空")
    if len(title) > 32:
        raise BuildError("标题超过 32 字，请先改短正文一级标题，再生成封面规格")
    line_count = 3 if render_cover.text_units(title) > 25 else 2
    candidates = []
    for breaks in itertools.combinations(range(1, len(title)), line_count - 1):
        points = (0, *breaks, len(title))
        lines = [title[points[index]:points[index + 1]] for index in range(line_count)]
        if any(len(line) > 18 or render_cover.text_units(line) > 16 for line in lines):
            continue
        if any(line[0] in BAD_LINE_START for line in lines[1:]):
            continue
        units = [render_cover.text_units(line) for line in lines]
        average = sum(units) / line_count
        score = sum((value - average) ** 2 for value in units) * 4
        for index in breaks:
            left, right = title[index - 1], title[index]
            if left in BREAK_AFTER:
                score -= 10
            if left.isascii() and left.isalnum() and right.isascii() and right.isalnum():
                score += 30
        if min(units) < 4:
            score += 18
        candidates.append((score, max(units) - min(units), lines))
    if not candidates:
        raise BuildError("标题无法安全拆行；每行需不超过 18 字且不能拆开英文单词")
    return min(candidates, key=lambda item: (item[0], item[1]))[2]


def choose_highlight(line):
    ascii_tokens = [item.group(0) for item in ASCII_TOKEN.finditer(line)]
    for token in ascii_tokens:
        if 2 <= len(token) <= 8 and token.upper() not in {"AI", "API"}:
            return token
    for match in CJK_RUN.finditer(line):
        value = match.group(0)
        if value:
            return value[: min(4, len(value))]
    for token in ascii_tokens:
        if 2 <= len(token) <= 8:
            return token
    return ""


def choose_template(title):
    digest = hashlib.sha256(normalized(title).encode("utf-8")).digest()
    return render_cover.TEMPLATES[digest[0] % len(render_cover.TEMPLATES)]


def article_fields(source):
    match = TITLE_RE.search(source)
    if not match:
        raise BuildError("article.md 缺少一级标题")
    title = normalized(match.group(1))
    body_lines = [
        normalized(line)
        for line in source.splitlines()
        if normalized(line) and not normalized(line).startswith("#")
    ]
    for line in body_lines:
        for sentence in SENTENCE_RE.findall(line):
            sentence = normalized(sentence)
            if 8 <= len(sentence) <= 40:
                return title, sentence
    return title, "聚焦技术变化如何进入真实工作流程"


def build_spec(title, theme, template, eyebrow, subtitle):
    lines = split_title(title)
    highlights = []
    if template == "redaction-poster":
        highlight = choose_highlight(lines[0])
        if highlight:
            highlights.append(highlight)
    raw = {
        "template": template,
        "theme": theme,
        "eyebrow": normalized(eyebrow),
        "title": normalized(title),
        "title_lines": lines,
        "highlights": highlights,
        "subtitle": normalized(subtitle),
    }
    return render_cover.validate_spec(raw)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def parse_args():
    parser = argparse.ArgumentParser(description="从最终标题生成合法的 HTML 封面规格")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--article")
    source.add_argument("--title")
    parser.add_argument("--theme", choices=tuple(render_cover.PALETTES), required=True)
    parser.add_argument(
        "--template", choices=("auto", *render_cover.TEMPLATES), default="auto"
    )
    parser.add_argument("--eyebrow", default="科技与产业观察")
    parser.add_argument("--subtitle")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        if args.article:
            title, inferred_subtitle = article_fields(
                Path(args.article).read_text(encoding="utf-8")
            )
        else:
            title, inferred_subtitle = args.title, "聚焦技术变化如何进入真实工作流程"
        template = choose_template(title) if args.template == "auto" else args.template
        spec = build_spec(
            title,
            args.theme,
            template,
            args.eyebrow,
            args.subtitle or inferred_subtitle,
        )
        atomic_json(Path(args.output), spec)
    except (BuildError, render_cover.CoverError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"status": "ok", "output": str(Path(args.output)), "title_lines": spec["title_lines"], "highlights": spec["highlights"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
