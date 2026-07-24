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

提示词中禁止遗留 `inline-visuals.json`、信息模块、`module_count` 或纯正文降级指令。当前必经顺序：

```text
init/topic → begin → article.md + sources.md → humanize(strong, exactly once)
→ Baoyu illustrations (1–3) → prepare → finish
```

正文图要求：完整提示词先保存至 `prompts/`，图像落在 `imgs/`，再作为 Markdown 图片引用插入 `article.md`。

## 3. 成功的唯一判定

cron 会话返回 `ok` 或模型返回 `[SILENT]` 不能证明文章已经生产。对外报告“草稿完成”前，必须回读工作区并同时确认：

1. `job.json.state == "drafted"`；
2. `stages.draft.status == "completed"`；
3. `draft-result.json` 中 `account` 是目标账号、`action == "draft"`，且 `draft_media_id` 非空；
4. `article.html`、`article_preview.html`、封面和全部正文图均实际存在。

如果自动热点发现没有选出可靠主题，任务应将 `discover` 标为 `failed` 并给出原因；不得保持 `running` 或静默返回。

## 4. 给定主题的真实生产验证

当需要验证整个流水线而非热点发现能力时，传入一个已核验的明确主题，避免“无可靠热点”在 discover 阶段提前停止。真实验证至少检查：Humanize 强度记录、`image_count` 与文章 HTML 图片数一致、HTML 零错误零警告，以及非空草稿 ID。
