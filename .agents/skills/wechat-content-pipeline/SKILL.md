---
name: wechat-content-pipeline
description: 编排中文微信公众号文章从给定选题或 48 小时内热点，到写作、humanize、可降级正文配图、生图 API 封面、随机主题和指定公众号草稿箱。用于定时自动生产或给定主题的一条龙草稿任务；不公开发布。
---

# 微信公众号内容生产流水线

外部 Agent 负责触发时间；本 Skill 以指定账号的微信公众号草稿箱为终点。

## 每次必读

- [references/artifact-contract.md](references/artifact-contract.md)：工作区、阶段和 `run_id`。
- [references/account-profiles.md](references/account-profiles.md)：账号内容偏好。
- 无给定主题时读 [references/hotspot-discovery.md](references/hotspot-discovery.md)。
- 写作前读 [references/structure-rotation.md](references/structure-rotation.md)：结构池与近文轮换，防同质限流。
- 写完正文、prepare 前读 [references/humanize-pass.md](references/humanize-pass.md)，加载 `humanizer-zh`，默认 `strong`。
- 正文配图读 `../baoyu-article-illustrator/SKILL.md` + [references/baoyu-illustrations-integration.md](references/baoyu-illustrations-integration.md)：**baoyu 负责分析与提示词，出图用当前环境自有后端**。
- 封面读 [references/ai-cover-generation.md](references/ai-cover-generation.md)：**品牌名+品牌色+场景**，禁止默认画完整商标 Logo。
- 失败时读 [references/pipeline-failure-triage.md](references/pipeline-failure-triage.md)。
- 修改阶段、产物、门禁、图片降级、草稿幂等或 cron 契约时，先读 [references/contract-simplification-migration.md](references/contract-simplification-migration.md)，按跨层清单和离线双运行探针验收。

项目根目录通常是本 Skill 向上三级；固定入口为：

```text
pipeline_job.py init/topic/history/shape/stage/show
pipeline_runtime.py begin/prepare/finish
```

不得为单篇文章新建临时渲染脚本，不得公开发布。

## 固定工作流

### 1. 初始化

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py init \
  --project-root <PROJECT_ROOT> --account <ACCOUNT> [--topic "给定主题"]
```

每次 `init` 生成新的 `run_id`。同账号使用 `work/<account>/current/`；存在 `running`、`failed` 或 `draft outcome=uncertain` 时不得覆盖。只有人工对账并明确丢弃旧任务时使用 `--force-new`。

不得因为同账号当天已经 `drafted` 而退出。新的 `run_id` 可以在同一天继续创建另一篇草稿。

### 2. 自动选题

先读取最近 7 天历史（**带结构轮换计划**）：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py history \
  --job <WORK_DIR>/job.json --days 7 --rotation
```

Agent 比较历史 `event_focus`，判断是否为同一核心事件。明确重复则换题；拿不准时放行。代码不做关键词、bigram 或阈值相似度判断。  
同时阅读 `rotation.blocked_*` / `preferred_*`，供写作前 `shape` 选型（结构轮换与事件去重同等重要）。

选题必须同时具备故事核：`event_focus`、`hook`、`tension`、`reader_stakes`。写不出矛盾与点击理由的“纯发布说明书”应换题或 `discover=failed`。细则见 [references/hotspot-discovery.md](references/hotspot-discovery.md)。

确定主题后：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name discover --status running

python3 <PIPELINE_ROOT>/scripts/pipeline_job.py topic \
  --job <WORK_DIR>/job.json \
  --value "最终选题" \
  --source auto-hotspot \
  --category "<账号 categories 内类别>" \
  --published-at "<热点发布时间，ISO 8601 且含时区>" \
  --event-focus "<一句话核心事件>" \
  --hook "<为什么要点开>" \
  --tension "<核心矛盾>" \
  --reader-stakes "<读者切身代价>"
```

写入时校验：类别、48 小时时效、`event_focus`，以及 **hook / tension / reader_stakes**。后续 prepare/finish 不重复检查热点年龄。

### 3. 锁定文章结构（防同质）

在 `begin`/写作前，根据 `history --rotation` 选择不在 blocked 列表中的形状并锁定：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py shape \
  --job <WORK_DIR>/job.json \
  --structure-id <preferred 中的 id> \
  --opening-type <preferred opening> \
  --ending-type <preferred ending> \
  --felt-sense "<主情绪>" \
  --tension-type <tension 类型> \
  --heading-count 3 \
  --body-band mid
```

`shape` 会写入 `job.article_shape` 并合并进 `topic-history.json`。冲突则换型重锁，禁止默认总用 `felt_essay` + 同一种开头。细则见 [references/structure-rotation.md](references/structure-rotation.md)。

### 4. 写作

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py begin \
  --job <WORK_DIR>/job.json
```

加载 `wechat-tech-insight-writer`，读取账号 `writer_instructions` / `voice`（默认**强情感主观**）、job 的 `hook`/`tension`/`reader_stakes` 与 **`article_shape`**。生成 `article.md`：

- 叙述人：第一人称「我」；主导情绪具体，且与近文 `felt_sense` 不雷同。
- 标题 ≤32 字，信息锚点 + 情感刺点；禁止周报体。
- **严格按已锁定 structure_id / opening / ending / heading_count / body_band 组织**，不是篇篇同一七段。
- 国内读者可能陌生的主体先 1—3 句简介再展开。
- **必须有读者带走物**（清单/判断标准/误读对照等），禁止白看一场。
- 正文 1500—4000；情绪钉在机制上；禁止编造亲历。中立简报、同质模具、纯情绪空文视为失败。
- 不创建 `sources.md`，不创建 `fact-check` 阶段。

### 5. Humanize

将 `humanize` 标为 `running`，按 `humanizer-zh` + [references/humanize-pass.md](references/humanize-pass.md) 就地改写，默认 `intensity=strong`，不新增事实。目标是**懂行者带强情感说话**，禁止抹平成中立 briefing；不得删掉清单与可执行段落。完成后标为 `completed`。

### 6. 正文配图（baoyu 分析 + 自有后端出图）

将 `illustrations` 标为 `running`。按 [references/baoyu-illustrations-integration.md](references/baoyu-illustrations-integration.md)：

1. 加载 **`baoyu-article-illustrator`**：分析插图位、Type×Style×Palette、**先写 `prompts/` 再出图**。流水线默认跳过向用户确认（全自动）。  
2. **出图**使用当前环境**自有**生图后端（`image_generate` / Imagine / Agnes 等），保存到 `imgs/`，插入 Markdown。  
3. 禁止跳过 baoyu、随手一句 prompt 直接出图。  
4. 0—3 张；失败可 `skipped`；**禁止视觉审图**。  
5. detail 示例：`analyzer=baoyu;backend=image_generate;count=N;visual_check=none`。

### 7. 封面（品牌名 + 品牌色 + 场景）

将 `cover` 标为 `running`。按 [references/ai-cover-generation.md](references/ai-cover-generation.md)：

- 主识别：**品牌/产品名文字** + **品牌色**；辅以文章张力场景。  
- **默认禁止**完整官方 Logo/注册商标图形；禁止官方海报误导体。  
- 用当前环境自有生图后端；`prompts/cover.txt`；输出 `cover/cover.png`。  
- **禁止** HTML 封面与视觉审图。  
- 成功：`visual_check=none`。

### 8. Prepare

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py prepare \
  --job <WORK_DIR>/job.json
```

`prepare` 检查标题、1500—4000 字、humanize、正文图最多 3 张与路径安全，固定随机主题。**不再生成 HTML 封面规格。** 不读 `sources.md`，不重复检查热点时效。

### 9. Finish

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py finish \
  --job <WORK_DIR>/job.json \
  --config <PROJECT_ROOT>/wechat-accounts.json
```

`finish` 重建正文 HTML，**验收** `cover/cover.png`（不渲染 HTML 封面），轻量门禁后 `send --action draft`：

- 不生成 preview，不做独立 validate，不记 leaf/哈希。
- 生图封面缺失且无默认 thumb → 失败。
- 正文坏图可跳过；微信 API 故障不得伪装成图片降级。
- 同一任务 `finish` 文件锁防双草稿。

## 草稿幂等与恢复

- 同一 `run_id` 已成功：`job.json` 和 `draft-result.json` 的账号、动作、`run_id`、`draft_media_id` 全部匹配时，直接返回原结果。
- 新 `run_id`：允许同账号当天继续创建新草稿。
- 正式 `draft/add` 前先落盘 `draft=running`、`run_id`、attempts 和 outcome。
- timeout、EOF、连接重置、响应字段不完整或遗留 `running`：记录 `outcome=uncertain`、`retry_safe=false`，禁止自动重发，先人工核对草稿箱。
- 明确发生在请求前的凭证或账号配置错误：记录 `preflight-failed`、`retry_safe=true`。

**Cron 恢复失败任务**：当 `job.state=failed` 且 `draft.status=running` 时，**不得提前结束**。必须用 `pipeline_job.py stage` 将 format/draft 重置为 pending，确保 `article.md` 满足“标题≤32字、正文1500-4000字”契约，然后依次执行 prepare → finish，直到 `state=drafted` + `draft-result.json` 存在并通过完成核验。始终继续现有 worktree，禁止 init 新 job。

**Cron 恢复运行中任务**（write/humanize/illustrations 未完成）：当 `job.state=running` 且 `write.status=running` 时，先用 `pipeline_job.py stage` 将 write/humanize/illustrations 标记为 completed 或 skipped（无图时用 skipped），再将 format/draft 重置为 pending。缺少 `article.md` 或字数不足时直接写入符合契约的正文（1500—4000 汉字），然后执行 prepare → finish。严禁 new job 或仅报告进度。

## 完成核验

只有同时满足以下条件才能报告成功：

1. `job.json.state == drafted`。
2. `stages.draft.status == completed`。
3. `draft-result.json.account` 和目标账号一致。
4. `draft-result.json.action == draft`。
5. `draft-result.json.run_id` 与 `job.json.run_id` 一致。
6. `draft-result.json.draft_media_id` 非空，且**不是占位符**。

**占位符检测（硬门禁）**：`draft_media_id` 不得包含 `dummy`、`fake`、`placeholder`、`test`、`mock`、`sample` 等字样，也不得是纯数字序列或明显非微信返回的格式。真实微信草稿 ID 通常为 40+ 字符的 base64 风格字符串（含大小写字母、数字、`-`、`_`）。如果 `draft_media_id` 疑似伪造，说明 `finish` 阶段跳过了真正的 `draft/add` API 调用——必须重新执行 `prepare → finish`，不得报告成功。

**禁止伪造草稿结果**：`draft-result.json` 只能由 `pipeline_runtime.py finish` 写入。Agent 不得手动创建或修改此文件。如果发现 `draft-result.json` 内容与 `finish` 的实际 API 响应不一致，视为任务失败，保留现场并报告。

最终只报告选题、主题、正文图数、账号、阶段耗时、`article.html` 路径和草稿结果。不得展示密钥或内部推理。
