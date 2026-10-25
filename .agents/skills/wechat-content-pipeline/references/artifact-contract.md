# 临时工作区与阶段契约

## 工作区

每个账号维护一个当前工作区：

```text
work/<account>/current/
├── job.json
├── source-dossier.json # 可选；仅受控公共事件档案模式，存核验事实与来源映射
├── article.md
├── inline-visuals.json # 原生 HTML 信息模块计划；0—3 项，公共事件默认最多 1 项
├── digest.txt        # 可选：≤50 字摘要（分享卡副标题）；缺失时微信自动截正文
├── imgs/
├── prompts/
├── cover/
│   └── cover.png
├── article.html
└── draft-result.json
```

`current/` 用于本轮 Skill 间传递，不是文章档案库；正式审核和留存在微信公众号草稿箱。新一轮 `init` 可在安全状态下清空并重建工作区，每次生成不同 `run_id`。

## 阶段

固定阶段为：

1. `discover`：使用给定主题（`--source provided`）。自动热点默认关闭。
2. `write`：完成 `article.md`（声口服从 brief；写作前须 `shape`；陌生主体按需简介；避免新闻汇报腔和同质模具）。公共事件档案使用克制正式声口。
3. `humanize`：用 `humanizer-zh` 一轮改写；普通观点稿默认 strong，公共事件档案为 restrained。pending 可直接 `completed`；记账时写入 `article_sha256`。
4. `illustrations`：正文已引用且文件存在 → `user_provided`。否则 `prepare` 标 `skipped`，不调用生图。`imgs/` 未引用文件只告警。`inline-visuals.json` 是独立的原生 HTML 阅读辅助，不计入图片数。
5. `format`：`prepare` 按 `run_id` 哈希固定主题（编辑稿不含通报皮），再由 `build_inline_visuals.py` 生成/校验模块计划；`finish` 生成 `article.html`。
6. `cover`：写入 `cover/cover.png`；已有文件记 `user_provided`。正式报道走准确标题 HTML，普通观点稿可走无文字生图，随后降级到 HTML、Pillow、账号默认 thumb，全不可用才失败。
7. `draft`：创建指定账号草稿。`draft-result.json` 回填 `theme` / `cover_backend` / `content_mode` / `content_fingerprint`。内容指纹未变才复用旧草稿。

状态只使用 `pending`、`running`、`completed`、`failed`、`skipped`。每个阶段记录真实 `started_at`、`completed_at` 和 `duration_ms`。

不存在 `fact-check`、`validate` 阶段；不存在自由格式 `sources.md`、预览、leaf count 或文件哈希
checkpoint。`source-dossier.json` 只是公共事件档案的受控上游证据卡，不新增流水线阶段。

## `run_id`

- 每次新 `init` 生成随机 `run_id`。
- 草稿成功结果必须保存同一个 `run_id`。
- 同一 `run_id` 的已完成草稿可复用；新 `run_id` 可在同一天再建一篇。
- `draft=running` 或 `failed/uncertain` 时不得自动覆盖或重发。
- `finish` 对同一任务加文件锁，防止两个并发调用同时进入 `draft/add`。

## 正文与图片

`article.md` 第一行是唯一一级标题（≤32 字，信息锚点 + 点击钩子），不包含写作计划或待办。`job.json` 可含 `hook` / `tension` / `reader_stakes` 与 **`article_shape`**（`structure_id` / `opening_type` / `ending_type` / `felt_sense` / `tension_type` / `heading_count` / `body_band`）。写作必须吃进。账号 `topic-history.json` 同时服务事件去重与结构轮换。正文图片统一由 `gen_inline_images.py` 处理；原生流程/对比/观点模块由 `inline-visuals.json` 驱动，渲染器直接输出公众号 HTML，不经过生图与 OCR。

`begin` 会验证 provided 选题已有非空 `user-brief.md`（`## 思路` 或 论点/时间线/大纲/要点/素材）、`event_focus` 和完整 `article_shape`。
`prepare` 与 `finish` 都会重跑写作体检，要求 score ≥75 且 high/blocking 为 0，并核对 `body_band` 与小节个数；结果写入
`stages.write.details`。humanize 后又改正文时，`article_changed_after_humanize` 为 true。

正文允许 0—3 张图。缺失或损坏图片可删除对应引用/HTML 标签后继续；路径越界、微信认证失败、有效图片上传失败仍是硬错误。图片上传时以真实文件字节和解码结果决定 MIME 与文件名，不依赖扩展名。

封面同样按真实字节识别格式（`cover.png` 内含 JPEG/WebP 字节合法，上传时自动规范化扩展名与 MIME），但必须可完整解码；与正文图的区别在于**不可跳过**——封面生成失败时只允许回退到当前账号已配置的默认 `thumb_media_id`。
