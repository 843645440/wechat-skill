<div align="center">

# wechat-skill · WeChat Content Skill Toolkit

**Layout an existing article, or write from a topic, then create a multi-account draft**

12 curated themes + theme generator · code blocks / images / GIFs · auto section numbers & keyword marks · two-gate quality checks

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blue.svg)](https://claude.ai/code)
[![Themes](https://img.shields.io/badge/themes-12%20+%20generator-31544A)](references/theme-index.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Agents](https://img.shields.io/badge/Claude%20Code%20·%20Codex%20·%20Cursor-supported-8b5cf6.svg)](#-quick-start)

English ｜ [中文](README.md)

</div>

---

A WeChat content toolkit for AI agents (Claude Code / Codex / Cursor …). It can:

- Turn Markdown / Word / PDF / plain text into **paste-safe, fully inlined** WeChat HTML
- Write from your topic and brief, de-AI the draft, add a cover, and create an account **draft**
- Lay out with 12 themes, or generate a new theme from a sentence or a reference image
- Handle multiple accounts; scheduling stays in your agent (this repo has no cron)

The pipeline **creates drafts only**. That is not public publishing, and not a follower broadcast. Review happens in the WeChat draft box. Generic hotspot picking is off by default.

## ✨ What this Skill does

- **12 curated themes** spanning card-rich layouts, low-noise long-form, news reporting, formal briefings, and vertical atmospheres; restrained gray body text with dark accents only. News-wire / solemn-gray / formal-brief are the formal pool only.
- **Add a theme** in `render_article.py` `THEMES`, register it in `references/theme-index.md`, add a gallery sample (see [CONTRIBUTING.md](CONTRIBUTING.md)). Do not write Markdown component libraries.
- **Full content support**: code blocks, images, GIFs, inline code, quotes, lists, product badges.
- **Smart layout**: auto section numbering, intro card, de-duplicated signature. Underlines come from `**key phrases**` in the manuscript. No auto TOC.
- **Two content lanes**: format an existing manuscript, or write from a topic. Same back half.
- **Optional images**: body images can be off; covers fall back from user art → exact-title HTML → optional generation → offline render.
- **Paste-safe**: all styles inlined, every text node wrapped in `<span leaf="">`.
- **Two-gate checks**: `component_lint.py` + `validate_gzh_html.py`.
- **One-click copy** preview page.
- **Multi-account drafts** via per-account environment variables.

## 👀 Previews

<table>
<tr>
<td width="33%" align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-moyu-green.png?v=1" width="250"><br><sub><b>Moyu Green (default)</b></sub></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-olive-journal.png?v=1" width="250"><br><sub><b>Olive Journal</b></sub></td>
</tr>
</table>

> 📚 **Theme guide → [docs/all-themes.md](docs/all-themes.md)** · or open `docs/gallery/index.html`.

## ✅ Good for / ❌ Not for

**✅ Good for**: opinion/analysis · tutorials · reviews · methodology · interviews · data recaps · essays · case studies — turning long-form into paste-ready WeChat HTML, generating custom themes, or writing from a topic into a draft.

**❌ Not for**: generic web/landing pages · slide decks · non-WeChat layout · automatic public publishing.

## 🎨 12 themes

| | Theme | Best for |
|---|---|---|
| ![](https://placehold.co/12/31544A/31544A.png) `#31544A` | Moyu Green (default) | Tutorials, reviews, checklists, tool roundups |
| ![](https://placehold.co/12/6B573F/6B573F.png) `#6B573F` | Olive Journal | Editorial notes, deep reviews, case recaps |
| ![](https://placehold.co/12/8C8378/8C8378.png) `#8C8378` | Plain White | Essays and low-noise long-form |
| ![](https://placehold.co/12/111111/111111.png) `#111111` | Ink Rule | Serious topics, reviews, historical recaps |
| ![](https://placehold.co/12/3E4C57/3E4C57.png) `#3E4C57` | Deep Pool | Investigations and industry observation |
| ![](https://placehold.co/12/1F1F1F/1F1F1F.png) `#1F1F1F` | Color Block | Strongly structured opinion pieces |
| ![](https://placehold.co/12/273746/273746.png) `#273746` | News Wire | News updates and fact checks |
| ![](https://placehold.co/12/712F38/712F38.png) `#712F38` | Solemn Gray | Fatal incidents and public-safety reviews |
| ![](https://placehold.co/12/234E70/234E70.png) `#234E70` | Formal Brief | Policy, institutional, and topical reports |
| ![](https://placehold.co/12/4A4458/4A4458.png) `#4A4458` | Aurora Violet | AIGC, product launches, frontier tools |
| ![](https://placehold.co/12/7A4A38/7A4A38.png) `#7A4A38` | Peach Soft | Lifestyle, books, food, essays |
| ![](https://placehold.co/12/7A6A45/7A6A45.png) `#7A6A45` | Noir Gold | Business, finance, career |

## 🚀 Quick start

**1. Full toolkit (recommended)**

```bash
git clone https://github.com/843645440/wechat-skill.git
cd wechat-skill
```

Then say: `Help me configure this WeChat skill`. The agent runs `python3 scripts/setup_status.py`. See [docs/setup.md](docs/setup.md).

**2. Ask any agent** to clone and load https://github.com/843645440/wechat-skill as the workspace. Do not copy only the root `SKILL.md`.

**3. Layout only:** `npx skills add https://github.com/843645440/wechat-skill`

## Two content lanes

| | 1. I already have the article | 2. I give a topic, AI writes |
|---|---|---|
| You provide | Manuscript (Markdown / Word / PDF) | Topic + brief, or an enabled series |
| Humanize | Optional, off by default | Always on |
| Length / score | Off | On (2500–5000 and the locked `body_band`, score ≥75) |
| Cron | No | Yes, via your agent |

A title without a manuscript is not lane 1. The default series is tech/AI. Personal series configs belong in `config/local/` and are not committed.

`prepare` locks the theme from the editorial pool (formal themes excluded) unless the piece is a casualty/case report. Body images count as user-provided only when the markdown cites existing files. Brief headings may be `思路` / `论点` / `时间线` / `大纲` / `要点` / `素材`.

Chinese [usage guide](docs/usage.md) covers credentials, IP allowlists, and pipeline commands. Free image key if needed: <https://platform.agnes-ai.cn>

## Disclaimer and license

You remain responsible for legality, facts, and review. Archive pieces only restate official conclusions and are not legal advice.

Licensed under **GNU AGPL-3.0**. Keep the original copyright notice in [LICENSE](LICENSE). Derivatives, forks, and network/SaaS use of a modified version must publish complete source under AGPL-3.0 (or compatible). No closed-source distribution.
