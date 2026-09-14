# Repository Guidelines

## Project Structure & Module Organization

This repository packages a WeChat content toolchain. Root `SKILL.md` handles formatting and publishing; automatically discovered writing, image, and orchestration skills live in `.agents/skills/`. Standalone Skill manuals that are not part of the default catalog live in `optional-skills/` and must be installed explicitly for direct invocation; the pipeline may still call their deterministic render/validation scripts without loading those manuals. The full pipeline entry is `.agents/skills/wechat-content-pipeline/SKILL.md`. Theme definitions live in `render_article.py` `THEMES`; treat `references/theme-index.md` as the human registry. Non-secret account content profiles live in `config/`, while credentials remain environment-backed. Deterministic Python utilities are in `scripts/`, with offline tests in `tests/`. The pipeline reuses `work/<account>/current/` as an internal handoff workspace; never commit generated articles, source notes, images, or draft IDs. Superseded v1/v2 assets are available from Git history, not the active branch.

## Build, Test, and Development Commands

Scripts use Python 3's standard library; there is no build step.

```bash
python3 scripts/component_lint.py .
python3 scripts/validate_gzh_html.py output.html
python3 scripts/wrap_preview.py output.html output_preview.html
python3 scripts/extract_docx.py article.docx
python3 -m unittest discover -s tests -v
python3 .agents/skills/wechat-viral-writer/scripts/score_draft.py --article work/a/current/article.md --markdown
python3 .agents/skills/wechat-viral-writer/scripts/hot_radar.py --markdown
```

The first command scans HTML blocks in `references/` and must report zero errors. The second checks generated HTML. The third creates a copy-enabled preview; validate the unwrapped article, not the preview shell. The DOCX command normalizes input, and unittest runs offline publishing and orchestration tests without live APIs. Prefer `os.makedirs(..., exist_ok=True)` over `Path.mkdir(exist_ok=True)` so directory creation stays valid under Agent pathlib shims.

## Runtime Pipeline Contract

Two lanes share one back half. `manuscript` is a user-supplied article: skip writing, word-count, and score gates; humanize is off unless the user turns it on. `brief` is topic-to-draft: the user supplies a topic and brief (see `wechat-content-pipeline/references/user-brief.md`); humanize is mandatory; score ≥75 and high/blocking=0 still gate `prepare`/`finish`. `begin` accepts `## 思路` or `论点` / `时间线` / `大纲` / `要点` / `素材`. Brief-lane body length must sit in the locked `body_band` (short 2500–3300, mid 3300–4200, long 4200–5000; boundary values may belong to either adjacent band). Heading count must be at least `max(2, heading_count-1)`.

The default series preset is tech/AI (`config/public-event-archive.json`). The official-case curator in `.agents/skills/wechat-public-event-archive/` only runs when a gitignored `config/local/public-event-archive.json` sets `preset=public-event` and `enabled=true`; it must then produce a verified `source-dossier.json` and synthetic `user-brief.md`, and hand the topic over as `provided`. Do not auto-pick generic hotspots. First-run setup is `docs/setup.md` plus `python3 scripts/setup_status.py`. Use only `pipeline_job.py init/topic/history/shape/stage/show` plus `pipeline_runtime.py begin/check/prepare/finish`. `show` includes a `summary` object. `prepare` auto-selects the theme and builds inline visuals.

Theme selection hashes `run_id`. Editorial articles use registered themes minus `FORMAL_THEMES` (`solemn-gray`, `news-wire`, `formal-brief`). Formal-report (dossier, brief markers, or casualty/case topic markers) uses only that formal pool. Do not pick a theme by article style except this safety routing.

Before writing body copy on the `brief` lane, read `.agents/skills/wechat-viral-writer/references/writing-checklist.md`. Never pad an article with invented numbers, cases, or first-hand experience to raise that score. Do not re-run `choose-theme` or `build_inline_visuals.py` after `prepare`. Humanize is one `stage --name humanize --status completed` from pending; the stage stores `article_sha256`. Cited local images mark illustrations `user_provided`; unreferenced files in `imgs/` do not. Prefer the runtime's native image tool; if none exists and `AGNES_API_KEY` is unset, skip body images. Do not name an image vendor in prompts. Cover files already at `cover/cover.png` are `user_provided`. `finish` reuses a draft only when `content_fingerprint` still matches. The Agent may write only the declared `work/<account>/current/` content artifacts; the archive skill may additionally update its gitignored `state/public-event-archive.sqlite3` ledger. Public publishing is outside this workflow.

## Coding Style & Naming Conventions

Use four-space indentation and standard-library-first Python. Keep command-line tools small, deterministic, and executable through `python3`. Register each new theme in `theme-index.md` and add its gallery sample as `docs/gallery/<id>.html`. In component HTML, use inline styles and semantic elements such as `<section>` and `<p>`. Do not introduce `<div>`, `class`, `id`, `<style>`, CSS variables, grid, or unsupported positioning. Wrap visible text in `<span leaf="">`.

## Testing Guidelines

The two validators gate theme changes. For theme or workflow changes, lint the repository, format `assets/sample-article.md`, then validate the generated HTML. Require zero errors; investigate warnings, especially half-width Chinese punctuation. Run the offline `unittest` suite for publishing changes; never connect tests to a real account. Check visual changes in a browser and add regression scenarios to `references/eval-cases.md`.

## Commit & Pull Request Guidelines

Use concise Conventional Commit-style subjects (`feat:`, `fix:`, `docs:`, `refactor:`) and explain what changed and why. Keep each pull request focused on one theme, fix, or documentation change. Include a clear description, linked issue when applicable, validation output, and a generated preview for visual changes. Do not commit root-level generated HTML or screenshots; `.gitignore` excludes local artifacts.
