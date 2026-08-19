# 账号内容档案

读取项目根目录 `config/wechat-content-profiles.json`。该文件只保存受众、内容偏好、正文配图和封面偏好，不保存发布时间、AppID、AppSecret、access token 或素材 ID。

## 覆盖顺序

1. 当前触发请求中的明确要求。
2. 对应账号内容档案。
3. 专项 Skill 的安全默认值。

账号档案不能覆盖事实核查、安全边界、随机主题和只写入草稿箱这些流水线规则。

## 关键字段

- `audience`：账号主要读者。
- `input_mode`：默认 `user_brief_only`——**只接受用户主题+思路**，禁止自动选题。
- `writer_instructions`：长期内容侧重点与**声口**；须写明「遵循用户 brief、禁止自行选题」；默认**第一人称主观 + 强情感 + 行业洞察**。
- `voice`（可选）：`tone`、`emotion_level`、`narrator`、`title_style`、`allowed_emotions`、`banned_title_patterns`、`signature_moves`；写作与 humanize 必须遵守。
- `topic_discovery.enabled`：默认 `false`。仅 `true` 且用户明确要求时才允许 `auto-hotspot`。
- `topic_discovery.categories` / `max_age_hours`：仅自动选题例外路径使用。
- `theme_strategy`：必须为 `random`，候选项来自根主题索引。
- `illustrations`：`enabled=false` 默认无正文图；用户给图仍由 `gen_inline_images.py` 识别。用户明确要求生图时加 `--force-generate`，机制型图固定走 `xiaohu:xiaoyi`。
- `cover.backend`：`image_generate` 先走 `xiaohu:agnes` 再离线兜底；`offline_render` 直接离线兜底。流水线已停用 HTML/Chrome 封面。
- `cover.aspect`：建议 `16:9`。
- `cover.subject_focus`：生图时用品牌名文字 + 品牌色 + 场景；默认不画完整官方 Logo。
- `publishing.target`：必须为 `draft`。

主路径为用户命题（见 `user-brief.md`）。生图仅在用户未提供图片时启用。排版主题仍随机。
