# 临时工作区与阶段契约

## 工作区

每个账号只维护一个当前工作区：

```text
work/<account>/current/
├── job.json
├── article.md
├── sources.md
├── illustrations/
├── cover/
│   ├── source.md
│   ├── prompts/cover.md
│   └── cover.png
├── article.html
├── article_preview.html
└── draft-result.json
```

外部定时任务每次触发时重新初始化该账号的 `current/`。这里是技能之间传递内容的临时空间，不是文章档案库；草稿创建成功后，正式审核和留存发生在微信公众号草稿箱。

## 阶段

固定阶段为：

1. `discover`：使用给定主题，或联网发现热点。
2. `write`：完成 `article.md`。
3. `fact-check`：完成 `sources.md` 和事实核验。
4. `humanize`：完成强制去 AI 味和事实回查。
5. `illustrate`：生成正文图片并更新 Markdown；后端不可用时标为 `skipped` 并继续。
6. `cover`：生成封面，或确认账号默认封面可用；不可用时标为 `skipped`，但继续排版与校验。
7. `format`：随机选主题并完成 `article.html`。
8. `validate`：严格校验、预览和占位符检查通过。
9. `draft`：指定账号草稿创建成功。

状态只使用 `pending`、`running`、`completed`、`failed`、`skipped`。图片能力缺失属于可降级的 `skipped`，不是提前终止任务的 `failed`；没有可用封面时由草稿门禁统一阻止上传。`draft` 完成即为流水线成功，不存在 AI 审批或公开发布阶段。

## 正文和来源

`article.md` 第一行是唯一一级标题，正文图片使用相对路径，不包含写作计划、来源清单或待办说明。Humanizer 和配图 Skill 都不得改变事实与核心判断。

`sources.md` 是内部事实记录。当前信息需包含机构、标题、日期、链接和支撑事实；未使用时效性事实时也要明确说明。它不进入公众号正文。

## 重试与覆盖

- 同一轮执行失败时保留工作区，可从 `job.json` 继续。
- 新一轮 `init` 会清空该账号旧的 `current/` 后重建。
- A、B 使用不同账号工作区，互不覆盖。
- 草稿创建成功后不再自动操作；下一轮覆盖本地工作区不影响微信草稿箱中的文章。
