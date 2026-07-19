# 临时工作区与阶段契约

## 工作区

每个账号只维护一个当前工作区：

```text
work/<account>/current/
├── job.json
├── article.md
├── sources.md
├── inline-visuals.json
├── cover/
│   ├── cover.spec.json
│   ├── cover.html
│   └── cover.png
├── article.html
├── article_preview.html
└── draft-result.json
```

外部定时任务每次触发时重新初始化该账号的 `current/`。这里用于 Skill 间传递内容，不是文章档案库；正式审核和留存发生在微信公众号草稿箱。

## 阶段

固定阶段为：

1. `discover`：使用给定主题，或联网发现热点。
2. `write`：完成 `article.md`。
3. `fact-check`：完成 `sources.md` 和事实核验。
4. `humanize`：完成强制去 AI 味和事实回查。
5. `format`：随机选择主题并完成基础 `article.html`。
6. `inline-visuals`：从正文提取结构化信息，插入同主题公众号原生 HTML 模块；没有合适信息时以 0 个模块正常完成。
7. `cover`：通过确定性 HTML 渲染器生成封面，或确认账号默认封面可用。
8. `validate`：严格校验、预览和占位符检查通过。
9. `draft`：指定账号草稿创建成功。

状态只使用 `pending`、`running`、`completed`、`failed`、`skipped`。原生信息模块为空不是失败。封面不可用时标记 `skipped`，继续完成 HTML 校验，最后由草稿门禁判断是否有默认封面。`draft` 完成即为流水线成功，不存在 AI 审批或公开发布阶段。

正文流程不生成 PNG、SVG 或截图，不调用图片模型、图片上传或 AI 视觉检测。封面只依赖字段校验、PNG 签名和精确尺寸；只渲染一次，浏览器技术故障最多原命令重试一次。

## 正文和来源

`article.md` 第一行是唯一一级标题，不包含写作计划、来源清单或待办说明。Humanizer、排版 Skill 和原生信息模块 Skill 都不得改变事实与核心判断。

`inline-visuals.json` 只保存正文中可定位、可核验的信息模块计划，不是另一份正文。每个模块必须保留原文锚点和证据。

`sources.md` 是内部事实记录。当前信息需包含机构、标题、日期、链接和支撑事实；未使用时效性事实时也要明确说明。它不进入公众号正文。

## 重试与覆盖

- 同一轮执行失败时保留工作区，可从 `job.json` 继续。
- 新一轮 `init` 清空该账号旧的 `current/` 后重建。
- A、B 使用不同账号工作区，互不覆盖。
- 草稿创建成功后不再自动操作；覆盖本地工作区不影响微信草稿箱。
