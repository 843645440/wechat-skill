# 定时生产任务：配置与完成核验

适用于由 Hermes cron 触发、目标是将文章送入公众号草稿箱的生产任务。

## 1. 挂载 Skill 时使用唯一名称

若同名 skill 可能来自多个目录，cron 的 `skills` 不得使用裸名。为 monorepo 内置 humanize 与正文配图使用限定名：

```text
wechat-content-pipeline
wechat-skill/.agents/skills/humanizer-zh
wechat-skill/.agents/skills/baoyu-article-illustrator
```

裸 `humanizer-zh` 在同名副本共存时会被解析器拒绝；这不应被静默跳过。

## 2. cron 提示词必须匹配当前产物契约

提示词中禁止遗留 `sources.md`、`article_preview.html`、`image_count`、`fact-check`、`validate`、文件哈希或“HTML 零警告”等旧契约指令。当前必经顺序：

```text
init/topic（用户 brief，source=provided）→ history --rotation → shape
→ begin → article.md → humanize(strong, exactly once)
→ 正文配图 0—3 张（失败可 skipped）→ 封面（生图或默认）→ prepare → finish
```

正文图要求：完整提示词先保存至 `prompts/`，图像落在 `imgs/`，再作为 Markdown 图片引用插入 `article.md`。

## 3. 成功的唯一判定

cron 会话返回 `ok` 或模型返回 `[SILENT]` 不能证明文章已经生产。对外报告“草稿完成”前，必须回读工作区并同时确认：

1. `job.json.state == "drafted"`；
2. `stages.draft.status == "completed"`；
3. `draft-result.json` 中 `account` 是目标账号、`action == "draft"`、`run_id` 与 job 一致，且 `draft_media_id` 非空、非占位符；
4. `article.html` 与 `cover/cover.png`（或账号默认封面记录）实际存在；正文图以 `article.md` 实际引用为准（0—3 张均合法）。

任务失败时应将对应阶段标为 `failed` 并给出原因；不得保持 `running` 或静默返回。`draft` 为 `uncertain` 时停止，不自动重发。

## 4. 给定主题的真实生产验证

当需要验证整条流水线时，传入明确的用户主题与思路（`--source provided`）。真实验证至少检查：humanize 强度记录、正文图引用与 `imgs/` 实际文件一致（0—3 张）、`article.html` 存在且无未替换占位符，以及非空草稿 ID。
