# Repository Guidelines

## Project Structure & Module Organization

This repository packages a WeChat content toolchain. Root `SKILL.md` handles formatting and publishing; automatically discovered writing, image, and orchestration skills live in `.agents/skills/`. Standalone extensions that are not part of the default pipeline live in `optional-skills/` and must be installed explicitly. The full pipeline entry is `.agents/skills/wechat-content-pipeline/SKILL.md`. Theme definitions and shared components live in `references/`; treat `references/theme-index.md` as the theme registry. Non-secret account content profiles live in `config/`, while credentials remain environment-backed. Deterministic Python utilities are in `scripts/`, with offline tests in `tests/`. The pipeline reuses `work/<account>/current/` as an internal handoff workspace; never commit generated articles, source notes, images, or draft IDs. Superseded v1/v2 assets are available from Git history, not the active branch.

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

The first command scans all HTML blocks in `references/` and must report zero errors. The second checks generated HTML. The third creates a copy-enabled preview; validate the unwrapped article, not the preview shell. The DOCX command normalizes input, and the final command runs offline publishing and orchestration tests without live APIs.

## Runtime Pipeline Contract

For a normal topic-to-draft task, the user must supply a topic and brief (see `wechat-content-pipeline/references/user-brief.md`). The only automated-topic exception is `.agents/skills/wechat-public-event-archive/`: the user must have explicitly authorized the series and `config/public-event-archive.json` must be enabled; that skill must produce a verified `source-dossier.json` and synthetic `user-brief.md`, then hand the topic to the normal pipeline as `provided`. Do not auto-pick generic hotspots unless the account profile explicitly enables discovery and the user asks; the standalone hot-topic radar (`.agents/skills/wechat-viral-writer/scripts/hot_radar.py`) is likewise off by default and never selects a topic on its own. Read the applicable skill and use only `pipeline_job.py init/topic/history/shape/choose-theme/stage/show` plus `pipeline_runtime.py begin/check/prepare/finish`.

Before writing body copy, read `.agents/skills/wechat-viral-writer/references/writing-checklist.md`. After writing, `pipeline_runtime.py check` automatically runs the writing health scorer (`wechat-viral-writer/scripts/score_draft.py`) and reports it under `writing`; high-severity findings and a sub-75 score both block `status=ok`. Never pad an article with invented numbers, cases, or first-hand experience to raise that score. Do not create per-article renderers, temporary workflow scripts, custom cover JSON, or visual-review loops. The Agent may write only the declared `work/<account>/current/` content artifacts; the archive skill may additionally update its gitignored `state/public-event-archive.sqlite3` ledger. Public publishing is outside this workflow.

## Coding Style & Naming Conventions

Use four-space indentation and standard-library-first Python. Keep command-line tools small, deterministic, and executable through `python3`. Theme files follow `references/theme-<kebab-case-id>.md`; register each new theme in `theme-index.md` and add its gallery sample as `docs/gallery/<id>.html`. In component HTML, use inline styles and semantic elements such as `<section>` and `<p>`. Do not introduce `<div>`, `class`, `id`, `<style>`, CSS variables, grid, or unsupported positioning. Wrap visible text in `<span leaf="">`.

## Testing Guidelines

The two validators gate theme changes. For theme or workflow changes, lint the repository, format `assets/sample-article.md`, then validate the generated HTML. Require zero errors; investigate warnings, especially half-width Chinese punctuation. Run the offline `unittest` suite for publishing changes; never connect tests to a real account. Check visual changes in a browser and add regression scenarios to `references/eval-cases.md`.

## Commit & Pull Request Guidelines

Use concise Conventional Commit-style subjects (`feat:`, `fix:`, `docs:`, `refactor:`) and explain what changed and why. Keep each pull request focused on one theme, fix, or documentation change. Include a clear description, linked issue when applicable, validation output, and a generated preview for visual changes. Do not commit root-level generated HTML or screenshots; `.gitignore` excludes local artifacts.
