# 账号内容档案

读取项目根目录 `config/wechat-content-profiles.json`。该文件只保存受众、内容偏好和图片偏好，不保存发布时间、AppID、AppSecret、access token 或素材 ID。

## 覆盖顺序

1. 当前触发请求中的明确要求。
2. 对应账号内容档案。
3. 专项 Skill 的安全默认值。

账号档案不能覆盖事实核查、安全边界、强制去 AI 味、随机主题和只写入草稿箱这些流水线规则。

## 关键字段

- `audience`：账号主要读者。
- `writer_instructions`：长期内容侧重点，不是单篇选题。
- `topic_discovery`：自动热点搜索的领域和时间窗口。
- `theme_strategy`：必须为 `random`；候选项来自根主题索引。
- `humanize.required`：必须为 `true`。
- `illustrations`、`cover`：图片密度和风格；空值表示让图片 Skill 自动选择。图片后端缺失只降级图片阶段，排版与校验仍要完成。
- `publishing.target`：必须为 `draft`。

账号可以有不同读者和热点方向，但排版主题不固定。Skill 本身不读取或执行时间字段，Agent 自带定时任务只需传账号别名和可选主题。
