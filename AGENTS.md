# Repository Guidelines

## Project Structure & Module Organization

This repository packages a WeChat content toolchain. Root `SKILL.md` handles formatting and publishing; project-level writing, image, cover, and orchestration skills live in `.agents/skills/`. The full pipeline entry is `.agents/skills/wechat-content-pipeline/SKILL.md`. Theme definitions and shared components live in `references/`; treat `references/theme-index.md` as the theme registry. Non-secret account content profiles live in `config/`, while credentials remain environment-backed. Deterministic Python utilities are in `scripts/`, with offline tests in `tests/`. The pipeline reuses `work/<account>/current/` as an internal handoff workspace; never commit generated articles, source notes, images, or draft IDs. `archive/` contains superseded v1 assets; do not update it for current features.

## Build, Test, and Development Commands

Scripts use Python 3's standard library; there is no build step.

```bash
python3 scripts/component_lint.py .
python3 scripts/validate_gzh_html.py output.html
python3 scripts/wrap_preview.py output.html output_preview.html
python3 scripts/extract_docx.py article.docx
python3 -m unittest discover -s tests -v
```

The first command scans all HTML blocks in `references/` and must report zero errors. The second checks generated HTML. The third creates a copy-enabled preview; validate the unwrapped article, not the preview shell. The DOCX command normalizes input, and the final command runs offline publishing and orchestration tests without live APIs.

## Runtime Pipeline Contract

For a full topic-to-draft task, read `.agents/skills/wechat-content-pipeline/SKILL.md` and use only `pipeline_job.py init/topic/show` plus `pipeline_runtime.py begin/prepare/finish`. Do not create per-article renderers, temporary workflow scripts, custom cover JSON, image-generation fallbacks, or visual-review loops. The Agent may write only the declared `work/<account>/current/` content artifacts. If a bundled step fails, follow its documented degradation or stop condition; never replace it with an improvised implementation. Public publishing is outside this workflow.

## Coding Style & Naming Conventions

Use four-space indentation and standard-library-first Python. Keep command-line tools small, deterministic, and executable through `python3`. Theme files follow `references/theme-<kebab-case-id>.md`; register each new theme in `theme-index.md` and add its gallery sample as `docs/gallery/<id>.html`. In component HTML, use inline styles and semantic elements such as `<section>` and `<p>`. Do not introduce `<div>`, `class`, `id`, `<style>`, CSS variables, grid, or unsupported positioning. Wrap visible text in `<span leaf="">`.

## Testing Guidelines

The two validators gate theme changes. For theme or workflow changes, lint the repository, format `assets/sample-article.md`, then validate the generated HTML. Require zero errors; investigate warnings, especially half-width Chinese punctuation. Run the offline `unittest` suite for publishing changes; never connect tests to a real account. Check visual changes in a browser and add regression scenarios to `references/eval-cases.md`.

## Commit & Pull Request Guidelines

Use concise Conventional Commit-style subjects (`feat:`, `fix:`, `docs:`, `refactor:`) and explain what changed and why. Keep each pull request focused on one theme, fix, or documentation change. Include a clear description, linked issue when applicable, validation output, and a generated preview for visual changes. Do not commit root-level generated HTML or screenshots; `.gitignore` excludes local artifacts.
