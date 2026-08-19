> 🤝 **A joint project by Jiamu × [Moyu Xiaoli (摸鱼小李)](https://mp.weixin.qq.com/s/EMahAzgfAbRQrYukWE7_IQ)**. Special thanks to Xiaoli.

<div align="center">

# wechat-skill · WeChat Content Skill

An Agent toolkit that turns a manuscript or a topic into paste-safe WeChat HTML and a **draft** in a chosen account.

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
English ｜ [中文](README.md)

</div>

The pipeline **creates drafts only**. It does not publish, and publishing is not the same as broadcasting to followers. Review happens in the WeChat draft box.

## After install

```bash
git clone https://github.com/843645440/wechat-skill.git
cd wechat-skill
```

Tell the agent:

> Help me configure this WeChat skill

It runs `python3 scripts/setup_status.py` and only asks for missing items. See [docs/setup.md](docs/setup.md). Do not copy only the root `SKILL.md`.

## Two ways to use it

| | 1. I already have the article | 2. I give a topic, AI writes |
|---|---|---|
| You provide | The manuscript | Topic + brief, or an enabled series |
| Writing | No rewrite | Required |
| De-AI pass | Optional, off by default | Always on |
| Length / score gates | Off | On (1500–4000 chars, score ≥75) |
| Cron | No | Yes, via your agent’s scheduler |

A title without a manuscript is not mode 1.

Series topics (organized crime, corruption, major fraud, …) are a mode-2 preset, not a trending-news scanner. They require an effective judgment or a stable official conclusion, plus an authority source and official Chinese media. Enable `config/public-event-archive.json`. This repo has no built-in cron.

## Images

- Body images are off by default. User images win. If enabled: use the agent’s native image tool; else `AGNES_API_KEY`; else skip.
- Covers cannot be empty: user image → exact-title HTML for formal reports → optional generation → HTML/Pillow → account default thumb.
- Do not name a vendor in prompts. Free key: <https://platform.agnes-ai.cn>

## Drafts need

Copy `assets/wechat-accounts.example.json` to `wechat-accounts.json`. Put AppID/AppSecret in environment variables. Never commit secrets. The host IP must be on the official-account whitelist. `--dry-run` cannot verify credentials or the draft API.

## Disclaimer and license

You remain responsible for legality, facts, and review. Archive pieces only restate official conclusions and are not legal advice.

**AGPL-3.0 © 2026 Jiamu × Moyu Xiaoli.** Attribution required. Derivatives, forks, and network/SaaS use of a modified version must publish complete source under AGPL-3.0 (or compatible). No closed-source distribution. See [LICENSE](LICENSE).
