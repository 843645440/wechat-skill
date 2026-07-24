# 账号内容档案

读取项目根目录 `config/wechat-content-profiles.json`。该文件只保存受众、内容偏好、正文配图和封面偏好，不保存发布时间、AppID、AppSecret、access token 或素材 ID。

## 覆盖顺序

1. 当前触发请求中的明确要求。
2. 对应账号内容档案。
3. 专项 Skill 的安全默认值。

账号档案不能覆盖事实核查、安全边界、随机主题和只写入草稿箱这些流水线规则。

## 关键字段

- `audience`：账号主要读者。
- `writer_instructions`：长期内容侧重点，不是单篇选题。
- `topic_discovery`：自动热点搜索的领域和时间窗口。
- `theme_strategy`：必须为 `random`，候选项来自根主题索引。
- `illustrations.enabled`：必须为 `true`。
- `illustrations.skill`：必须为 `baoyu-article-illustrator`。
- `illustrations.backend`：必须为 `image_generate`；正文图写入 `imgs/`，完整提示词写入 `prompts/`。
- `illustrations.max_images`：必须在 1—3 之间。当前流水线不生成 `inline-visuals.json`，也不使用原生 HTML 信息模块阶段。
- `cover.backend`：必须为 `html`，只用确定性 HTML/CSS 截图生成封面。
- `cover.theme`：`article` 表示跟随本轮文章主题。
- 封面模板现有 `signal-editorial`、`night-signal` 与 `redaction-poster` 三套，暂不在账号档案中绑定；以后可单独增加账号规则。
- `publishing.target`：必须为 `draft`。

浏览器只用于封面；正文图片由 Baoyu skill 调用 `image_generate` 生成，固定渲染器只负责把 Markdown 图片转成 HTML。封面失败不得自动改用 Agnes 或其他 AI 生图。账号可以有不同读者和热点方向，但排版主题不固定。Skill 不读取或执行时间字段；Agent 自带定时任务只需传账号别名和可选主题。
