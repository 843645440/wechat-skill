#!/usr/bin/env python3
"""正文配图一条命令：把「分析文章 → 选插图位 → 写 prompt → 调后端 → 插回
Markdown」这几步 agent 判断压成一次调用，防止弱模型在这一环走失。

降级链（语义固定，任何环境都一样）：

1. **用户已给图优先**：`article.md` 里已经引用了真实存在的本地图片，或
   `--imgs-dir` 里已经放了图片文件 → 直接 `backend=user_provided`，
   `status=completed`，不生图、不覆盖、不删用户的图。
2. **没有用户图 → 尝试生图**：用确定性启发式挑 0-3 个插入位，套同一个固定
   prompt 模板（不做美学分支决策），调用 xiaohu-gen 的 xiaoyi 后端生成 PNG。
3. **生成成功 → 用生成的**：成功几张就插几张，`backend=image_generate`。
4. **生成失败/没有后端 → 不配图**：`status=skipped`，`article.md` 原样不
   动，这是正常结果，不是失败——上游流水线不应该因为这个退出非 0。

退出码约定：只有命令行参数本身非法时才非 0（argparse 的默认行为）；
其余任何失败路径（没有 API key、超时、后端返回非图片……）都归一化成
`status=skipped` 并以 0 退出，避免这一步把整条流水线拖死。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _stage_record  # noqa: E402 - 同目录内部模块，必须在 sys.path 之后导入

SCRIPT_DIR = Path(__file__).resolve().parent
# 正文图固定为机制/流程/对比型信息图，按 xiaohu-gen 的路由契约应走 xiaoyi。
# 本脚本只负责选位置、写 prompt、插回 Markdown，绝不自己拼 HTTP 请求。
XIAOYI_GENERATE = (
    SCRIPT_DIR.parent.parent / "xiaohu-gen" / "scripts" / "xiaoyi_generate.py"
)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
# 必须能被 render_article.py 的 IMAGE_RE 解析：独占一行、路径不含空格。
INLINE_IMAGE_REF_RE = re.compile(r"!\[[^\]\n]*\]\(([^()\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^```")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
MD_STRIP_RE = re.compile(r"[#*`\[\]()_>]")

MIN_SECTION_CHARS = 60  # 少于这个字数的章节不值得配图
DEFAULT_TIMEOUT = 200  # 与 xiaohu-gen 的 xiaoyi 单 key 超时契约一致

# 单一固定 prompt 模板：弱模型不需要、也不应该做风格/美学分支决策。
PROMPT_TEMPLATE = """{title} — inline illustration {index}/{total}: {heading}

Single-page hand-drawn editorial infographic in a clean presentation style.
Warm cream paper background (#F5F0E8), black hand-drawn outlines with a
slight wobble (#1A1A1A), soft pastel color blocks (light blue #A8D8EA, mint
green #B5E5CF, lavender #D5C6E0, peach #FFD5C2), coral red (#E8655A) used
sparingly for a single emphasis point. Diagram-style visual ONLY — no
photographic or realistic imagery, no watermark, no logo, no signature.

TOPIC: {summary}
LAYOUT: one clear focal diagram that helps a reader understand the idea
        above (mechanism / comparison / flow preferred over decoration).
        Minimal short labels only if essential; never long sentences.
ASPECT: 16:9
"""


class PathEscapeError(ValueError):
    pass


def safe_join(base_dir, *parts):
    """在 base_dir 内部拼路径；一旦结果跑出 base_dir 就拒绝（防 .. 逃逸）。"""
    base = Path(base_dir).resolve()
    candidate = base.joinpath(*parts).resolve()
    if candidate != base and base not in candidate.parents:
        raise PathEscapeError(f"路径逃逸出 imgs-dir：{Path(*parts)}")
    return candidate


def plain_text(value):
    return MD_STRIP_RE.sub("", value).strip()


# ---------------------------------------------------------------------------
# 1. 用户已给图检测
# ---------------------------------------------------------------------------

def find_user_provided(article_text, article_dir, imgs_dir):
    """返回 True 当用户已经提供了图（正文引用 或 imgs-dir 里已有文件）。"""
    for match in INLINE_IMAGE_REF_RE.finditer(article_text):
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:")):
            continue
        candidate = (article_dir / src).resolve()
        if candidate.is_file():
            return True
    if imgs_dir.is_dir():
        for entry in imgs_dir.iterdir():
            if entry.is_file() and entry.suffix.lower() in IMAGE_EXTS:
                return True
    return False


# ---------------------------------------------------------------------------
# 2. 确定性挑位启发式
# ---------------------------------------------------------------------------

def parse_h2_sections(lines):
    """按二级标题切段，返回每段的正文特征，用于挑插图位。

    只看二级标题（章节数）；每段的正文字数（段落长度）；是否含代码块/表格
    （含则跳过，不在技术性区块里插图）。三个信号都是启发式意义上的
    「确定性」——同一篇文章、同一份代码，永远算出同一个结果。
    """
    title = None
    sections = []
    current = None
    in_fence = False

    for idx, raw in enumerate(lines):
        line = raw.rstrip("\n")
        stripped = line.strip()
        if FENCE_RE.match(stripped):
            in_fence = not in_fence
            if current is not None:
                current["has_code"] = True
                current["body_end"] = idx + 1
            continue
        if not in_fence:
            match = HEADING_RE.match(stripped)
            if match:
                level = len(match.group(1))
                if level == 1 and title is None:
                    title = plain_text(match.group(2))
                    continue
                if level == 2:
                    if current is not None:
                        current["end"] = idx
                    current = {
                        "heading": plain_text(match.group(2)),
                        "heading_line": idx,
                        "start": idx + 1,
                        "end": len(lines),
                        "body_end": idx + 1,
                        "has_code": False,
                        "has_table": False,
                        "first_blank_after_para": None,
                    }
                    sections.append(current)
                    continue
        if current is None:
            continue
        current["body_end"] = idx + 1
        if TABLE_ROW_RE.match(stripped) and stripped.count("|") >= 2:
            current["has_table"] = True
        if (
            current["first_blank_after_para"] is None
            and stripped == ""
            and idx > current["heading_line"] + 1
        ):
            current["first_blank_after_para"] = idx

    text_by_section = []
    for sec in sections:
        body_lines = lines[sec["start"]:sec["end"]]
        prose = [ln for ln in body_lines if ln.strip() and not FENCE_RE.match(ln.strip())]
        text = plain_text(" ".join(prose))
        sec["text_len"] = len(text)
        first_para_lines = []
        for ln in body_lines:
            if ln.strip() == "":
                if first_para_lines:
                    break
                continue
            if HEADING_RE.match(ln.strip()):
                break
            first_para_lines.append(ln.strip())
        sec["summary"] = plain_text(" ".join(first_para_lines))[:120] or sec["heading"]
        text_by_section.append(sec)
    return title, text_by_section


def choose_positions(article_text, max_images):
    """纯函数：只依赖文章内容和 max，天然满足「同 seed 两次一致」。"""
    lines = article_text.splitlines()
    title, sections = parse_h2_sections(lines)
    candidates = [
        s for s in sections
        if not s["has_code"] and not s["has_table"] and s["text_len"] >= MIN_SECTION_CHARS
    ]
    if not candidates:
        return title or "", []

    target = min(max(max_images, 0), 3, len(candidates))
    if target == 0:
        return title or "", []

    ranked = sorted(candidates, key=lambda s: (-s["text_len"], s["heading_line"]))
    chosen = ranked[:target]
    chosen.sort(key=lambda s: s["heading_line"])  # 恢复文档阅读顺序

    for i, sec in enumerate(chosen, start=1):
        insertion_line = sec["first_blank_after_para"]
        if insertion_line is None:
            insertion_line = sec["body_end"]
        sec["insertion_line"] = insertion_line
        sec["index"] = i
    return title or "", chosen


# ---------------------------------------------------------------------------
# 3. 生图后端调用（唯一允许调用外部命令的地方）
# ---------------------------------------------------------------------------

def call_image_backend(prompt_path, output_path, timeout=DEFAULT_TIMEOUT):
    """调用 xiaohu-gen/scripts/xiaoyi_generate.py；失败一律返回 False。

    测试里会整体 monkeypatch 这个函数，不打真实网络请求。
    """
    if not XIAOYI_GENERATE.is_file():
        return False
    cmd = [
        sys.executable, str(XIAOYI_GENERATE),
        "--prompt-file", str(prompt_path),
        "--output", str(output_path),
        "--size", "16:9",
        "--timeout", str(max(5, timeout - 5)),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return False
    if proc.returncode != 0:
        return False
    try:
        last_line = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1]
        data = json.loads(last_line)
    except (IndexError, ValueError):
        return False
    if data.get("status") != "ok":
        return False
    return output_path.is_file() and output_path.stat().st_size > 0


def generate_one(prompt_path, output_path, timeout):
    """单张失败只重试一次；仍失败则跳过该图。"""
    for _ in range(2):
        if call_image_backend(prompt_path, output_path, timeout=timeout):
            return True
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
    return False


# ---------------------------------------------------------------------------
# 4. 主流程
# ---------------------------------------------------------------------------

def resolve_seed(args):
    if args.seed:
        return args.seed
    if args.job:
        return Path(args.job).stem
    return Path(args.article).stem


def run(args):
    article_path = Path(args.article).resolve()
    imgs_dir = Path(args.imgs_dir).resolve()
    article_dir = article_path.parent

    if not article_path.is_file():
        return {"status": "skipped", "backend": "none", "inserted": 0,
                "reason": f"article 不存在：{article_path}"}

    article_text = article_path.read_text(encoding="utf-8")

    if find_user_provided(article_text, article_dir, imgs_dir):
        return {"status": "completed", "backend": "user_provided",
                "inserted": 0, "positions": []}

    if args.job and not getattr(args, "force_generate", False):
        try:
            job = json.loads(Path(args.job).read_text(encoding="utf-8"))
            inline_enabled = (job.get("image_policy") or {}).get("inline_enabled")
        except (OSError, ValueError):
            inline_enabled = None
        if inline_enabled is False:
            return {
                "status": "skipped", "backend": "none", "inserted": 0,
                "reason": "按账号策略 inline_enabled=false 跳过正文生图",
            }

    title, chosen = choose_positions(article_text, args.max)
    if not chosen:
        return {"status": "skipped", "backend": "none", "inserted": 0,
                "reason": "没有找到合适的插图位（章节太短/都是代码或表格）"}

    seed = resolve_seed(args)
    try:
        imgs_dir.mkdir(parents=True, exist_ok=True)
        prompts_dir = safe_join(imgs_dir, "prompts")
        prompts_dir.mkdir(parents=True, exist_ok=True)
    except PathEscapeError as exc:
        return {"status": "skipped", "backend": "none", "inserted": 0,
                "reason": str(exc)}

    total = len(chosen)
    inserted = []
    for sec in chosen:
        idx = sec["index"]
        try:
            prompt_path = safe_join(imgs_dir, "prompts", f"{idx:02d}-inline.md")
            output_path = safe_join(imgs_dir, f"{idx:02d}-inline.png")
        except PathEscapeError:
            continue
        prompt_text = PROMPT_TEMPLATE.format(
            title=title or "文章", index=idx, total=total,
            heading=sec["heading"], summary=sec["summary"] or sec["heading"],
        )
        prompt_path.write_text(prompt_text, encoding="utf-8")
        if not generate_one(prompt_path, output_path, args.timeout):
            continue
        rel_path = os.path.relpath(output_path, article_dir)
        alt = sec["heading"].replace("[", "").replace("]", "")[:60] or "配图"
        sec["rel_path"] = rel_path
        sec["alt"] = alt
        inserted.append(sec)

    if not inserted:
        return {"status": "skipped", "backend": "none", "inserted": 0,
                "reason": "生图后端不可用或全部失败（无 key/超时/非图片响应）"}

    lines = article_text.splitlines()
    keep_trailing_newline = article_text.endswith("\n")
    for sec in sorted(inserted, key=lambda s: s["insertion_line"], reverse=True):
        md_line = f"![{sec['alt']}]({sec['rel_path']})"
        block = ["", md_line, ""]
        pos = min(sec["insertion_line"], len(lines))
        lines[pos:pos] = block
    new_text = "\n".join(lines)
    if keep_trailing_newline and not new_text.endswith("\n"):
        new_text += "\n"
    article_path.write_text(new_text, encoding="utf-8")

    positions = [
        {"heading": sec["heading"], "image": sec["rel_path"]}
        for sec in sorted(inserted, key=lambda s: s["index"])
    ]
    return {"status": "completed", "backend": "image_generate",
            "provider": "xiaohu:xiaoyi",
            "inserted": len(inserted), "positions": positions}


def build_parser():
    parser = argparse.ArgumentParser(
        description="正文配图一条命令：用户已给图优先，否则挑位生图，生不出来就不配图",
    )
    parser.add_argument("--article", required=True, help="article.md 路径")
    parser.add_argument("--imgs-dir", required=True, help="正文图片目录（只在这里面写文件）")
    parser.add_argument("--max", type=int, default=3, help="最多插入几张，0-3")
    parser.add_argument("--seed", default="", help="确定性种子，建议用 run_id")
    parser.add_argument("--job", default="", help="job.json 路径，缺省 seed 时用它兜底")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="单张生图超时秒数")
    parser.add_argument(
        "--force-generate", action="store_true",
        help="用户明确要求生图时覆盖账号 inline_enabled=false；用户给图不需要此参数",
    )
    parser.add_argument(
        "--record-stage", action="store_true",
        help="连同 illustrations 阶段一起记账（running → completed/skipped），"
             "需要 --job；用了它就不必再手动跑 pipeline_job.py stage",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    def produce():
        try:
            return run(args)
        except Exception as exc:  # noqa: BLE001 - 这一步绝不能把流水线拖垮
            return {"status": "skipped", "backend": "none", "inserted": 0,
                    "reason": f"{type(exc).__name__}: {exc}"}

    if args.record_stage and args.job:
        result = _stage_record.record_around(args.job, "illustrations", produce)
    else:
        result = produce()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
