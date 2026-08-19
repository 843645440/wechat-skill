#!/usr/bin/env python3
"""Build a small, evidence-bound native HTML visual plan.

Formal/public-event articles get at most one process module assembled only from
their final article text.  It is a reading aid, not a generated illustration:
no new fact, number, scene, or allegation can enter through this step.
"""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline_job  # noqa: E402
import render_article  # noqa: E402
import visual_policy  # noqa: E402


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
VALIDATOR_PATH = (
    PROJECT_ROOT / "optional-skills" / "wechat-inline-visuals"
    / "scripts" / "validate_plan.py"
)
TIMELINE_WORDS = (
    "背景", "形成", "发生", "调查", "侦破", "抓捕", "落网", "审理",
    "宣判", "判决", "处理", "追责", "治理", "结论", "边界", "影响",
)


def load_validator():
    if not VALIDATOR_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("pipeline_inline_validator", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact(value, maximum):
    value = " ".join(str(value).split())
    return value if len(value) <= maximum else value[:maximum]


def block_text(block):
    kind = block.get("kind")
    if kind in {"paragraph", "quote", "subheading"}:
        return compact(block.get("text", ""), 160)
    if kind == "list":
        return compact("；".join(block.get("items", [])), 160)
    return ""


def section_fact(section):
    for block in section.get("blocks", []):
        value = block_text(block)
        if value:
            return value
    return ""


def build_formal_plan(article_text, theme):
    _, sections = render_article.parse_article(article_text)
    usable = []
    for section in sections:
        heading = compact(section.get("heading", ""), 40)
        fact = section_fact(section)
        if heading and fact:
            usable.append({
                "heading": heading,
                "fact": fact,
            })
    preferred = [
        item for item in usable
        if any(word in item["heading"] for word in TIMELINE_WORDS)
    ]
    chosen = (preferred if len(preferred) >= 3 else usable)[:5]
    if len(chosen) < 3:
        return {"version": 1, "theme": theme, "modules": []}

    anchor_item = chosen[-1]
    steps = [
        {
            "label": compact(item["heading"], 10),
            "text": compact(item["fact"], 28),
        }
        for item in chosen
    ]
    evidence = [compact(item["fact"], 160) for item in chosen[:4]]
    return {
        "version": 1,
        "theme": theme,
        "modules": [{
            "id": "inline-01",
            "kind": "process",
            "title": "公开事实脉络",
            "placement": {
                "after_heading": anchor_item["heading"],
                "after_text": compact(anchor_item["fact"], 120),
            },
            "evidence": evidence,
            "steps": steps,
        }],
    }


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def validate_or_degrade(plan, article_text, theme):
    validator = load_validator()
    if validator is None:
        # The builder emits the strict canonical schema.  Keep rendering
        # available in slim deployments even if the optional validator was
        # omitted; render_article still defensively degrades invalid plans.
        return plan, False, "validator_not_installed", {
            "theme": theme,
            "module_count": len(plan.get("modules", [])),
            "kinds": [item.get("kind") for item in plan.get("modules", [])],
        }
    raw = validator.coerce_plan(plan, fallback_theme=theme)
    try:
        result = validator.validate_plan(raw, article_text, set(render_article.THEMES))
        return raw, False, "", result
    except validator.PlanError as exc:
        return {"version": 1, "theme": theme, "modules": []}, True, str(exc), {
            "theme": theme, "module_count": 0, "kinds": []
        }


def run(job_path):
    job = pipeline_job.load_job(job_path)
    job_dir = Path(job["job_dir"]).resolve()
    artifacts = job.setdefault("artifacts", {})
    article_path = Path(pipeline_job.artifact_path(
        str(job_path), artifacts.get("article", "article.md")
    )[0])
    plan_path = Path(pipeline_job.artifact_path(
        str(job_path), artifacts.get("inline_visuals", "inline-visuals.json")
    )[0])
    article_text = article_path.read_text(encoding="utf-8")
    mode = visual_policy.content_mode(job, job_dir)
    theme = visual_policy.selected_theme(
        job, "formal-brief" if mode == "formal-report" else "plain-white"
    )

    if plan_path.is_file():
        try:
            proposed = json.loads(plan_path.read_text(encoding="utf-8"))
            source = "existing"
        except (OSError, json.JSONDecodeError):
            proposed = {"version": 1, "theme": theme, "modules": []}
            source = "invalid-existing"
    elif mode == "formal-report":
        proposed = build_formal_plan(article_text, theme)
        source = "formal-auto"
    else:
        proposed = {"version": 1, "theme": theme, "modules": []}
        source = "none"

    plan, degraded, reason, detail = validate_or_degrade(
        proposed, article_text, theme
    )
    atomic_json(plan_path, plan)
    result = {
        "status": "ok",
        "content_mode": mode,
        "source": source,
        "output": str(plan_path),
        "degraded": degraded,
        "degrade_reason": reason,
        **detail,
    }
    refreshed = pipeline_job.load_job(job_path)
    result["next_command"] = pipeline_job.suggest_next_command(refreshed, job_path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成或校验公众号原生信息模块计划")
    parser.add_argument("--job", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.job)
    except (OSError, ValueError, pipeline_job.JobError, render_article.RenderError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
