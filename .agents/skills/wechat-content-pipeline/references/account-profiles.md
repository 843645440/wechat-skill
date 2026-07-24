# 账号内容档案

读取项目根目录 `config/wechat-content-profiles.json`。该文件只保存受众、内容偏好、正文配图和封面偏好，不保存发布时间、AppID、AppSecret、access token 或素材 ID。

## 覆盖顺序

1. 当前触发请求中的明确要求。
2. 对应账号内容档案。
3. 专项 Skill 的安全默认值。

账号档案不能覆盖事实核查、安全边界、随机主题和只写入草稿箱这些流水线规则。

## 关键字段

- `audience`：账号主要读者。
- `writer_instructions`：长期内容侧重点与**声口**；当前默认期望为**第一人称主观 + 强情感 + 行业洞察**，不是中立新闻汇报。
- `voice`（可选）：`tone`、`emotion_level`、`narrator`、`title_style`、`allowed_emotions`、`banned_title_patterns`、`signature_moves`；写作与 humanize 必须遵守。
- `topic_discovery`：自动热点搜索的领域和时间窗口；`require_story_kernel: true` 时选题必须带 hook/tension/reader_stakes。
- `theme_strategy`：必须为 `random`，候选项来自根主题索引。
- `illustrations.enabled`：必须为 `true`。
- `illustrations.skill`：必须为 `baoyu-article-illustrator`。
- `illustrations.backend`：必须为 `image_generate`；正文图写入 `imgs/`，完整提示词写入 `prompts/`。
- `illustrations.max_images`：必须在 1—3 之间。当前流水线不生成 `inline-visuals.json`，也不使用原生 HTML 信息模块阶段。
- `cover.backend`：必须为 `image_generate`（**已停用 HTML/Chrome 封面**）。
- `cover.aspect`：建议 `16:9`（亦允许 `2.35:1` / `20:9` / `3:2`）。
- `cover.subject_focus`：为 true 时封面用**品牌名文字 + 品牌色 + 张力场景**识别主体（见 `ai-cover-generation.md`）；默认不画完整官方 Logo。
- `publishing.target`：必须为 `draft`。

正文图与封面均由生图能力生成：正文走 Baoyu/`image_generate`，封面由 Agent 按 `ai-cover-generation.md` 写入 `cover/cover.png`。`wechat-html-cover` 仅保留手工调试，流水线不调用。账号可有不同读者与热点方向；排版主题仍随机。Skill 不读取时间字段；定时任务只传账号别名和可选主题。
