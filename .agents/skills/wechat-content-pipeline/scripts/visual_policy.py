#!/usr/bin/env python3
"""Small, deterministic visual policy shared by the pipeline media scripts.

The optional visual skills contain the full design manuals.  Runtime code must
not load those manuals on every article, so this module keeps only the routing
decisions and the compact cover-art dimensions the pipeline actually needs.
"""

import hashlib
import json
from pathlib import Path


FORMAL_BRIEF_MARKERS = (
    "公共事件档案模式",
    "克制、正式、事实优先",
    "克制正式",
    "正式报道",
    "权威发布",
    "不消费苦难",
)
FORMAL_TOPIC_MARKERS = (
    "枪击",
    "伤亡",
    "遇难",
    "事故调查",
    "案件通报",
    "抓捕",
    "落网",
    "判决",
    "宣判",
    "贪腐案",
    "诈骗案",
    "涉黑",
    "扫黑除恶",
)


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def content_mode(job, job_dir=None):
    """Return ``formal-report`` for verified/serious event coverage.

    A validated public-event job is unambiguous because it carries a dossier.
    Explicit brief markers come next.  Topic markers are deliberately narrow:
    they bias violent/criminal cases toward the safer formal renderer without
    turning every historical or business article into a news report.
    """
    base = Path(job_dir or job.get("job_dir") or ".")
    if (base / "source-dossier.json").is_file():
        return "formal-report"
    brief = _read(base / "user-brief.md")
    if any(marker in brief for marker in FORMAL_BRIEF_MARKERS):
        return "formal-report"
    subject = " ".join(
        str(job.get(key) or "") for key in ("topic", "event_focus")
    )
    if any(marker in subject for marker in FORMAL_TOPIC_MARKERS):
        return "formal-report"
    return "editorial"


def selected_theme(job, fallback="plain-white"):
    details = (job.get("stages", {}).get("format", {}).get("details") or {})
    return details.get("theme") or fallback


def _contains(text, words):
    lowered = text.lower()
    return any(word.lower() in lowered for word in words)


def editorial_art_direction(title, context):
    """Distill Baoyu's design dimensions into a no-text cover prompt.

    The generated cover is intentionally visual-only.  Chinese title text is
    left to WeChat's article card; this avoids generated gibberish and avoids
    pretending that an image model can typeset an exact headline reliably.
    """
    subject = " ".join((title, context)).strip()
    if _contains(subject, ("AI", "模型", "芯片", "机器人", "算法", "软件", "科技")):
        direction = {
            "type": "conceptual",
            "palette": "cool",
            "rendering": "digital illustration",
            "style": "technical-schematic editorial",
            "mood": "restrained, precise, forward-looking",
        }
    elif _contains(subject, ("就业", "职场", "公司", "企业", "裁员", "工作流")):
        direction = {
            "type": "metaphor",
            "palette": "elegant",
            "rendering": "editorial collage",
            "style": "human-scale conceptual editorial",
            "mood": "thoughtful, tense, humane",
        }
    elif _contains(subject, ("历史", "复盘", "发展史", "沉浮", "人物", "创业")):
        direction = {
            "type": "scene",
            "palette": "retro",
            "rendering": "screen print",
            "style": "archival editorial poster",
            "mood": "reflective, textured, unsentimental",
        }
    else:
        # Stable rotation keeps unrelated articles from receiving one house
        # style while remaining reproducible for retries of the same article.
        variants = (
            ("conceptual", "elegant", "flat vector", "minimal editorial", "clear, calm, analytical"),
            ("metaphor", "warm", "paper cut collage", "editorial collage", "human, focused, candid"),
            ("scene", "cool", "screen print", "contemporary magazine", "observant, balanced, confident"),
        )
        index = hashlib.sha256(subject.encode("utf-8")).digest()[0] % len(variants)
        kind, palette, rendering, style, mood = variants[index]
        direction = {
            "type": kind,
            "palette": palette,
            "rendering": rendering,
            "style": style,
            "mood": mood,
        }

    prompt = f"""WeChat editorial cover artwork, ultra-wide 2.35:1 landscape.

SUBJECT: {title}
CONTEXT: {context or title}

ART DIRECTION:
- Type: {direction['type']}
- Palette: {direction['palette']}
- Rendering: {direction['rendering']}
- Style: {direction['style']}
- Mood: {direction['mood']}
- Composition: one unmistakable focal metaphor, strong silhouette, generous negative space,
  readable at mobile thumbnail size, sophisticated Chinese magazine art direction.

HARD CONSTRAINTS:
- Visual artwork only: absolutely no text, letters, numbers, captions, logos, watermarks, or signatures.
- Do not imitate an official announcement poster or reproduce a trademark.
- No generic pastel presentation template, no stock-photo collage, no glossy 3D advertising render.
"""
    return {**direction, "text": "none", "ratio": "2.35:1", "prompt": prompt}


def write_art_direction(path, value):
    """Persist a compact, reproducible record beside the generated prompt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: item for key, item in value.items() if key != "prompt"}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
