# 贡献指南 · Contributing

欢迎为 wechat-skill 贡献新主题、工作流、排版修复或文档改进。

## 项目结构速览

- `SKILL.md` — 排版工作流主文档（Agent 入口）
- `.agents/skills/` — 写作、去 AI 味、图片后端和完整内容流水线 Skill
- `optional-skills/` — 不进默认目录的独立封面 / 信息模块手册
- `config/` — 可提交的账号内容档案，不得放凭证
- `references/` — 主题索引、正式主题说明、多账号发布、评测用例
- `scripts/` — HTML 校验、DOCX 提取、去水印与多账号发布脚本
- `tests/` — 离线 unittest，禁止连接真实公众号
- `assets/` — 演示输入文章
- `docs/gallery/` — 主题风格的浏览器预览

主题的单一真相源是 `.agents/skills/wechat-content-pipeline/scripts/render_article.py` 的 `THEMES`。不要再新建 Markdown 组件库。

## 可验证循环（改动前后都要跑）

任何改动主题、渲染器或 SKILL 后，按这个双关卡闭环自检，两关全绿才提 PR：

```bash
python3 scripts/component_lint.py .
python3 scripts/validate_gzh_html.py <生成的.html>
python3 -m unittest discover -s tests -v
```

- `component_lint.py` 须 **0 ERROR**
- `validate_gzh_html.py` 须 **0 ERROR、半角标点 0 WARN**
- unittest 须全部通过；测试里创建目录用 `os.makedirs(..., exist_ok=True)`，不要用 `Path.mkdir(exist_ok=True)`（部分 Agent 沙箱的 pathlib shim 会把已存在目录当成错误）

细节见 `references/eval-cases.md`。

发布脚本改动还须运行离线测试，禁止在测试中连接真实公众号。完整流水线复用 `work/<account>/current/` 作为内部交接区；不要提交真实文章、来源记录、封面、草稿 ID 或发布结果。定时由外部 Agent 配置，不要在 Skill 中加入 cron 或固定发布时间。

## 新增一套主题风格

1. 在 `THEMES` 里加一项（复用现有 `layout` 只改色值最省事），按需给 `render_hero` / `render_heading` / `render_follow_cta` / `render_end` 加分支。
2. 硬性约束：所有样式内联、文字用 `<span leaf="">` 包裹、禁 `div/class/id/<style>/grid/position/var/@media`、代码块用「每行一个 `<p>`」而**非 `white-space:pre`**。不要加「看点 / 目录」区块。
3. 在 `references/theme-index.md` 登记一行（主色 + 适用场景）。流水线 `prepare` 按 `run_id` 哈希轮换：编辑稿只用非通报主题；伤亡/案件才进 `solemn-gray` / `news-wire` / `formal-brief`。不要按题材选皮。
4. 用 `assets/sample-article.md` 渲染并 `validate_gzh_html.py` 到 0 ERROR，再跑 `python3 -m unittest tests.test_article_renderer`。
5. 把预览放到 `docs/gallery/<id>.html`，并更新 `docs/gallery/index.html`。

## 提交规范

- 一个 PR 只做一件事（一套新主题 / 一处修复 / 一处文档）。
- commit 信息说清「改了什么 + 为什么」，建议 Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:`）。
- 不要提交本地排版产物（`.gitignore` 已忽略 `*_排版_*.html`、`/work/`、凭证）。
