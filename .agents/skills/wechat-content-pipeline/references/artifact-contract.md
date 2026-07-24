# 临时工作区与阶段契约

## 工作区

每个账号维护一个当前工作区：

```text
work/<account>/current/
├── job.json
├── article.md
├── imgs/
├── prompts/
├── cover/
│   ├── cover.spec.json
│   ├── cover.html
│   └── cover.png
├── article.html
└── draft-result.json
```

`current/` 用于本轮 Skill 间传递，不是文章档案库；正式审核和留存在微信公众号草稿箱。新一轮 `init` 可在安全状态下清空并重建工作区，每次生成不同 `run_id`。

## 阶段

固定阶段为：

1. `discover`：使用给定主题，或发现并记录 48 小时内热点。
2. `write`：完成 `article.md`。
3. `humanize`：用 `humanizer-zh` 对正文执行一轮改写，默认 strong。
4. `format`：固定随机主题并生成 `article.html`。
5. `illustrations`：尝试生成 0—3 张正文图；成功为 `completed`，失败降级为 `skipped`。
6. `cover`：生成确定性 HTML 封面，或确认账号默认封面可用。
7. `draft`：创建指定账号草稿。

状态只使用 `pending`、`running`、`completed`、`failed`、`skipped`。`humanize` 和 `illustrations` 完成前必须先标记 `running`。每个阶段记录真实 `started_at`、`completed_at` 和 `duration_ms`。

不存在 `fact-check`、`validate` 阶段；不存在 `sources.md`、预览、leaf count 或文件哈希 checkpoint。

## `run_id`

- 每次新 `init` 生成随机 `run_id`。
- 草稿成功结果必须保存同一个 `run_id`。
- 同一 `run_id` 的已完成草稿可复用；新 `run_id` 可在同一天再建一篇。
- `draft=running` 或 `failed/uncertain` 时不得自动覆盖或重发。
- `finish` 对同一任务加文件锁，防止两个并发调用同时进入 `draft/add`。

## 正文与图片

`article.md` 第一行是唯一一级标题，不包含写作计划或待办。正文图由 Baoyu skill 调用当前 Hermes `image_generate` 后端生成，提示词保存在 `prompts/`，图片保存在 `imgs/`。

正文允许 0—3 张图。缺失或损坏图片可删除对应引用/HTML 标签后继续；路径越界、微信认证失败、有效图片上传失败仍是硬错误。图片上传时以真实文件字节和解码结果决定 MIME 与文件名，不依赖扩展名。

封面不使用正文图降级规则：显式封面必须是可解码且声明格式一致的有效图片；封面生成失败时只允许回退到当前账号已配置的默认 `thumb_media_id`。
