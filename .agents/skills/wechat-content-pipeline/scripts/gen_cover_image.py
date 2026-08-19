#!/usr/bin/env python3
"""封面一条命令：按内容类型路由，再走完整降级链。

封面和正文配图有一个根本区别：**正文图可以没有，封面不能没有**。finish 把
`cover/cover.png` 当硬门禁，所以这里的降级链必须一直走到能出图为止：

1. **用户已给封面**：`cover/cover.png` 已存在且非空 → `backend=user_provided`，
   原样保留，绝不覆盖。
2. **正式报道/公共事件**：用 HTML 模板准确排标题，绝不生成案件现场插画 →
   `backend=html_render`。
3. **普通观点稿**：把 Baoyu 的封面维度压成确定性艺术指导，调 xiaohu-gen 的
   Agnes 后端生成无文字的 2.35:1 主视觉 → `backend=image_generate`。
4. **前路由失败 → 离线兜底**：先尝试准确标题 HTML，再用
   `render_cover_fallback.py` 排一张确定性
   封面 → `backend=offline_render`。这一步不需要网络、不需要 API key、不需要浏览器。
5. 兜底也失败才 `status=failed`，此时只有账号配了默认 `thumb_media_id` 才能继续。

之所以要有这个脚本：这条链原本散在 ai-cover-generation.md 和 check 的 hints 里，
需要 agent 自己判断走到第几档、自己拼 prompt、自己在失败后想起还有兜底命令。这些
都是可以由代码固定下来的判断，不该留给模型临场发挥。

退出码恒为 0（除非命令行参数非法）；结果看 stdout 那行 JSON 的 status 字段。
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
import visual_policy  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
AGNES_GENERATE = (
    SCRIPT_DIR.parent.parent / "xiaohu-gen" / "scripts" / "agnes_generate.py"
)
COVER_FALLBACK = SCRIPT_DIR / "render_cover_fallback.py"
PROJECT_ROOT = SCRIPT_DIR.parents[3]
HTML_COVER_DIR = PROJECT_ROOT / "optional-skills" / "wechat-html-cover"
BUILD_HTML_SPEC = HTML_COVER_DIR / "scripts" / "build_cover_spec.py"
RENDER_HTML_COVER = HTML_COVER_DIR / "scripts" / "render_cover.py"

H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
MD_STRIP_RE = re.compile(r"[#*`\[\]()_>]")
# 固定 80s：生图快就用生图，超了就走离线兜底，不为了多抢一张图把整条流水线拖长。
# 降级是正常结果，不是故障——但降级原因会写进结果的 generate_failed_because。
DEFAULT_TIMEOUT = 80

def plain_text(value):
    return MD_STRIP_RE.sub("", value).strip()


def read_title(article_path, fallback):
    """封面文案来源：article.md 的一级标题；读不到就用 job 的 topic。"""
    try:
        text = Path(article_path).read_text(encoding="utf-8")
    except OSError:
        return fallback
    match = H1_RE.search(text)
    return plain_text(match.group(1)) if match else fallback


def account_label(job):
    """取账号档案里的 label 当眉标（kicker）；取不到就用账号别名。"""
    account = job.get("account", "")
    try:
        profiles = json.loads(
            Path(job["profiles_path"]).read_text(encoding="utf-8")
        )
        label = profiles.get("profiles", {}).get(account, {}).get("label")
        if isinstance(label, str) and label.strip():
            return label.strip()
    except (OSError, ValueError, KeyError):
        pass
    return account


def has_usable_cover(cover_path):
    return cover_path.is_file() and cover_path.stat().st_size > 0


def try_generate(prompt_text, cover_path, prompts_dir, ratio, timeout):
    """走生图后端。返回 (ok, reason)。

    reason 在失败时必须说清「为什么」——超时、没配 key、后端非零退出是三种完全
    不同的处置：超时该放宽 --timeout 或重试，没 key 该去配环境变量，后端报错该看
    它的 stderr。早期版本这里只返回 bool，失败原因被整个吞掉，结果是降级到离线
    兜底之后没人知道生图那条路到底出了什么事。
    """
    if not AGNES_GENERATE.is_file():
        return False, f"生图后端脚本不存在：{AGNES_GENERATE}"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompts_dir / "cover.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    cmd = [
        sys.executable, str(AGNES_GENERATE),
        "--prompt-file", str(prompt_path),
        "--output", str(cover_path),
        "--ratio", ratio,
        "--timeout", str(max(10, timeout - 10)),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, (
            f"生图超时（>{timeout}s）。实测单张封面常在 40–60s，网络慢时会更久；"
            f"用 --timeout 放宽后重试"
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"调用生图后端失败：{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        tail = detail[-1][:200] if detail else "无输出"
        return False, f"生图后端退出码 {proc.returncode}：{tail}"
    if not has_usable_cover(cover_path):
        return False, "生图后端报告成功但没有产出可用文件"
    return True, ""


def try_fallback(title, kicker, seed, cover_path, ratio):
    """离线兜底：确定性排版，不依赖网络与 API key。"""
    if not COVER_FALLBACK.is_file():
        return False
    cmd = [
        sys.executable, str(COVER_FALLBACK),
        "--title", title,
        "--kicker", kicker,
        "--seed", seed,
        "--output", str(cover_path),
        "--ratio", ratio,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return False
    if proc.returncode != 0:
        return False
    return has_usable_cover(cover_path)


def try_html_cover(article_path, title, kicker, theme, cover_path, timeout):
    """Render an exact-title cover through the compact optional renderer.

    Calling its deterministic scripts does not load the optional Skill manual
    into model context.  The manual stays opt-in; the reliable renderer is a
    normal runtime dependency with a Pillow fallback.
    """
    if not BUILD_HTML_SPEC.is_file() or not RENDER_HTML_COVER.is_file():
        return False, "HTML 封面渲染器未安装", {}
    cover_dir = cover_path.parent
    cover_dir.mkdir(parents=True, exist_ok=True)
    spec_path = cover_dir / "cover.spec.json"
    html_path = cover_dir / "cover.html"
    build_cmd = [
        sys.executable, str(BUILD_HTML_SPEC),
        "--article", str(article_path),
        "--theme", theme,
        "--template", "signal-editorial",
        "--eyebrow", kicker or "专题报道",
        "--output", str(spec_path),
    ]
    try:
        built = subprocess.run(
            build_cmd, capture_output=True, text=True, timeout=min(timeout, 30)
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"HTML 封面规格生成失败：{type(exc).__name__}: {exc}", {}
    if built.returncode != 0:
        detail = (built.stderr or built.stdout).strip().splitlines()
        return False, "HTML 封面规格失败：" + (detail[-1][:200] if detail else "无输出"), {}
    render_cmd = [
        sys.executable, str(RENDER_HTML_COVER),
        "--spec", str(spec_path),
        "--output", str(cover_path),
        "--html-output", str(html_path),
        "--timeout", str(max(5, min(timeout, 60))),
    ]
    try:
        rendered = subprocess.run(
            render_cmd, capture_output=True, text=True, timeout=max(10, min(timeout + 5, 70))
        )
    except subprocess.TimeoutExpired:
        return False, f"HTML 封面渲染超时（>{timeout}s）", {}
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"HTML 封面渲染失败：{type(exc).__name__}: {exc}", {}
    if rendered.returncode != 0 or not has_usable_cover(cover_path):
        detail = (rendered.stderr or rendered.stdout).strip().splitlines()
        return False, "HTML 封面渲染失败：" + (detail[-1][:200] if detail else "无输出"), {}
    return True, "", {
        "template": "signal-editorial",
        "theme": theme,
        "spec": str(spec_path),
        "html": str(html_path),
        "title": title,
    }


def run(args):
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    job_dir = Path(job["job_dir"]).resolve()
    artifacts = job.get("artifacts", {})
    article_path = job_dir / artifacts.get("article", "article.md")
    cover_path = job_dir / artifacts.get("cover", "cover/cover.png")
    cover_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. 用户已给封面 —— 最高优先级，绝不覆盖
    if has_usable_cover(cover_path):
        return {"status": "completed", "backend": "user_provided",
                "cover": str(cover_path)}

    title = read_title(article_path, job.get("topic", "") or "封面")
    kicker = account_label(job)
    seed = str(job.get("run_id", "") or "seed")
    mode = visual_policy.content_mode(job, job_dir)
    theme = visual_policy.selected_theme(
        job, "formal-brief" if mode == "formal-report" else "plain-white"
    )

    # 2. 正式事件只走准确标题封面，不虚构现场视觉。
    if mode == "formal-report":
        ok, html_reason, meta = try_html_cover(
            article_path, title, kicker, theme, cover_path, args.timeout
        )
        if ok:
            return {
                "status": "completed", "backend": "html_render",
                "cover": str(cover_path), "content_mode": mode, **meta,
            }
        generate_reason = "正式报道禁用 AI 插画；" + html_reason
    else:
        generate_reason = "尚未尝试生成"

    # 3. 普通观点稿按紧凑艺术指导生图。offline_render/--skip-generate 跳过。
    policy = job.get("image_policy") or {}
    backend = policy.get("cover_backend", "image_generate")
    skip_generate = (
        mode == "formal-report"
        or args.skip_generate
        or backend == "offline_render"
    )
    if backend == "offline_render" and mode != "formal-report":
        generate_reason = "按账号策略 cover_backend=offline_render 跳过"
    elif args.skip_generate and mode != "formal-report":
        generate_reason = "按 --skip-generate 跳过"
    if not skip_generate:
        direction = visual_policy.editorial_art_direction(
            title, job.get("event_focus") or job.get("topic") or title
        )
        visual_policy.write_art_direction(
            job_dir / "prompts" / "cover-direction.json", direction
        )
        ok, generate_reason = try_generate(
            direction["prompt"], cover_path, job_dir / "prompts", "2.35:1", args.timeout
        )
        if ok:
            return {"status": "completed", "backend": "image_generate",
                    "provider": "xiaohu:agnes",
                    "cover": str(cover_path), "title": title,
                    "content_mode": mode,
                    "art_direction": {
                        key: value for key, value in direction.items() if key != "prompt"
                    }}

    # 4. 生图或正式路由失败时，先尝试准确标题 HTML。
    if mode != "formal-report":
        ok, html_reason, meta = try_html_cover(
            article_path, title, kicker, theme, cover_path, args.timeout
        )
        if ok:
            return {
                "status": "completed", "backend": "html_render",
                "cover": str(cover_path), "content_mode": mode,
                "generate_failed_because": generate_reason, **meta,
            }
        generate_reason = f"{generate_reason}；{html_reason}"

    # 5. Pillow 离线兜底 —— 封面是硬门禁，这一步不能省。
    #    降级本身是正常结果，但一定要把「为什么降级」带出来：静默降级会让
    #    「今天生图挂了」和「这台机器根本没配 key」看起来一模一样。
    if try_fallback(title, kicker, seed, cover_path, args.ratio):
        return {"status": "completed", "backend": "offline_render",
                "cover": str(cover_path), "title": title,
                "content_mode": mode,
                "note": "已用离线兜底渲染",
                "generate_failed_because": generate_reason}

    # 4. 全失败
    return {
        "status": "failed", "backend": "none",
        "reason": "生图与离线兜底都失败；只有账号配置了默认 thumb_media_id 才能继续 finish",
        "generate_failed_because": generate_reason,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="封面一条命令：用户图优先 → 生图 → 离线兜底，保证 finish 有封面可用",
    )
    parser.add_argument("--job", required=True, help="job.json 路径")
    parser.add_argument("--ratio", default="2.35:1",
                        choices=["16:9", "2.35:1", "20:9", "3:2"])
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="生图超时秒数")
    parser.add_argument("--skip-generate", action="store_true",
                        help="跳过生图直接用离线兜底（无网络/无 key 时用）")
    parser.add_argument(
        "--record-stage", action="store_true",
        help="连同 cover 阶段一起记账（running → completed/failed），"
             "用了它就不必再手动跑 pipeline_job.py stage",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    def produce():
        try:
            return run(args)
        except Exception as exc:  # noqa: BLE001 - 失败也要给出结构化结果
            return {"status": "failed", "backend": "none",
                    "reason": f"{type(exc).__name__}: {exc}"}

    if args.record_stage:
        result = _stage_record.record_around(args.job, "cover", produce)
    else:
        result = produce()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
