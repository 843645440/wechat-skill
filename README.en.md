<div align="center">

# wechat-skill · WeChat Content Skill Toolkit

**Layout an existing article, or write from a topic, then create a multi-account draft**

11 curated themes + theme generator · code blocks / images / GIFs · auto section numbers & keyword marks · two-gate quality checks

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blue.svg)](https://claude.ai/code)
[![Themes](https://img.shields.io/badge/themes-11%20+%20generator-059669)](references/theme-index.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Agents](https://img.shields.io/badge/Claude%20Code%20·%20Codex%20·%20Cursor-supported-8b5cf6.svg)](#-quick-start)

English ｜ [中文](README.md)

</div>

---

A WeChat content toolkit for AI agents (Claude Code / Codex / Cursor …). It can:

- Turn Markdown / Word / PDF / plain text into **paste-safe, fully inlined** WeChat HTML
- Write from your topic and brief, de-AI the draft, add a cover, and create an account **draft**
- Lay out with 11 themes, or generate a new theme from a sentence or a reference image
- Handle multiple accounts; scheduling stays in your agent (this repo has no cron)

The pipeline **creates drafts only**. That is not public publishing, and not a follower broadcast. Review happens in the WeChat draft box. Generic hotspot picking is off by default.

## ✨ What this Skill does

- **11 curated themes** spanning card-rich layouts, low-noise long-form, news reporting, solemn coverage, and formal briefings.
- **Theme generator**: describe a style or drop a reference image (see `references/theme-generator.md`).
- **Full content support**: code blocks, images, GIFs, inline code, quotes, lists, product badges.
- **Smart layout**: auto section numbering, 1–3 keyword underlines per paragraph, intro card & TOC, de-duplicated signature.
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
<td width="33%" align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-red-white.png?v=1" width="250"><br><sub><b>Red & White</b></sub></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-moyu-ticket.png?v=1" width="250"><br><sub><b>Moyu Ticket</b></sub></td>
<td align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-olive-journal.png?v=1" width="250"><br><sub><b>Olive Journal</b></sub></td>
</tr>
</table>

> 📚 **Theme guide → [docs/all-themes.md](docs/all-themes.md)** · or open `docs/gallery/index.html`.

## ✅ Good for / ❌ Not for

**✅ Good for**: opinion/analysis · tutorials · reviews · methodology · interviews · data recaps · essays · case studies — turning long-form into paste-ready WeChat HTML, generating custom themes, or writing from a topic into a draft.

**❌ Not for**: generic web/landing pages · slide decks · non-WeChat layout · automatic public publishing.

## 🎨 11 themes

| | Theme | Best for |
|---|---|---|
| ![](https://placehold.co/12/059669/059669.png) `#059669` | Moyu Green (default) | Tutorials, reviews, checklists, tool roundups |
| ![](https://placehold.co/12/DC2626/DC2626.png) `#DC2626` | Red & White | Deep analysis, opinions, strong takes |
| ![](https://placehold.co/12/059669/059669.png) `#059669` | Moyu Ticket | Tool comparisons, creative reviews |
| ![](https://placehold.co/12/1e1f23/1e1f23.png) `#1e1f23` | Olive Journal | Editorial notes, deep reviews, case recaps |
| ![](https://placehold.co/12/8C8378/8C8378.png) `#8C8378` | Plain White | Essays and low-noise long-form |
| ![](https://placehold.co/12/111111/111111.png) `#111111` | Ink Rule | Serious topics, reviews, historical recaps |
| ![](https://placehold.co/12/2E7D8C/2E7D8C.png) `#2E7D8C` | Deep Pool | Investigations and industry observation |
| ![](https://placehold.co/12/1B5E8C/1B5E8C.png) `#1B5E8C` | Color Block | Strongly structured opinion pieces |
| ![](https://placehold.co/12/273746/273746.png) `#273746` | News Wire | News updates and fact checks |
| ![](https://placehold.co/12/712F38/712F38.png) `#712F38` | Solemn Gray | Fatal incidents and public-safety reviews |
| ![](https://placehold.co/12/234E70/234E70.png) `#234E70` | Formal Brief | Policy, institutional, and topical reports |

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
| Length / score | Off | On (1500–4000, score ≥75) |
| Cron | No | Yes, via your agent |

A title without a manuscript is not lane 1. The default series is tech/AI. Personal series configs belong in `config/local/` and are not committed. Free image key if needed: <https://platform.agnes-ai.cn>

Chinese [usage guide](docs/usage.md) covers credentials, IP allowlists, and pipeline commands.

## Disclaimer and license

You remain responsible for legality, facts, and review. Archive pieces only restate official conclusions and are not legal advice.

Licensed under **GNU AGPL-3.0**. Keep the original copyright notice in [LICENSE](LICENSE). Derivatives, forks, and network/SaaS use of a modified version must publish complete source under AGPL-3.0 (or compatible). No closed-source distribution.
