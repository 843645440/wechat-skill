---
name: wechat-content-pipeline
description: 编排中文微信公众号文章从给定选题或 48 小时内热点，到写作、humanize、可降级正文配图、随机主题、确定性封面和指定公众号草稿箱。用于定时自动生产或给定主题的一条龙草稿任务；不公开发布。
---

# 微信公众号内容生产流水线

外部 Agent 负责触发时间；本 Skill 以指定账号的微信公众号草稿箱为终点。

## 每次必读

- [references/artifact-contract.md](references/artifact-contract.md)：工作区、阶段和 `run_id`。
- [references/account-profiles.md](references/account-profiles.md)：账号内容偏好。
- 无给定主题时读 [references/hotspot-discovery.md](references/hotspot-discovery.md)。
- 写完正文、prepare 前读 [references/humanize-pass.md](references/humanize-pass.md)，加载 `humanizer-zh`，默认 `strong`。
- 正文配图读 `../baoyu-article-illustrator/SKILL.md`。
- 失败时读 [references/pipeline-failure-triage.md](references/pipeline-failure-triage.md)。
- 修改阶段、产物、门禁、图片降级、草稿幂等或 cron 契约时，先读 [references/contract-simplification-migration.md](references/contract-simplification-migration.md)，按跨层清单和离线双运行探针验收。

项目根目录通常是本 Skill 向上三级；固定入口为：

```text
pipeline_job.py init/topic/history/stage/show
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

先读取最近 7 天历史：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py history \
  --job <WORK_DIR>/job.json --days 7
```

Agent 比较历史 `event_focus`，判断是否为同一核心事件。明确重复则换题；拿不准时放行。代码不做关键词、bigram 或阈值相似度判断。

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
  --event-focus "<一句话核心事件>"
```

写入时只校验三项：类别属于账号档案、`0 <= 当前时间 - published_at <= 48 小时`、Agent 已提供 `event_focus`。后续 prepare/finish 不重复检查热点年龄。

### 3. 写作

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py begin \
  --job <WORK_DIR>/job.json
```

生成 `article.md`：

- 唯一一级标题，标题不超过 32 字。
- 正文可读字符 1500—4000，不含一级标题与空白。
- 按已核实信息量定长短，不为凑字注水。
- 不创建 `sources.md`，不创建 `fact-check` 阶段。

### 4. Humanize

将 `humanize` 标为 `running`，按 `humanizer-zh` 对 `article.md` 就地执行一轮，默认 `intensity=strong`，不新增事实；完成后标为 `completed`。

### 5. 正文配图

将 `illustrations` 标为 `running`。目标生成 1—3 张横向、无水印正文图，提示词保存到 `prompts/`，图片保存到 `imgs/`，以 Markdown 引用插入 `article.md`。

- 信息不适合配图时允许 0 张。
- 生成失败最多重试两次；仍失败时将 `illustrations` 标为 `skipped`，无图继续。
- 有图时标为 `completed`；无需声明 `image_count`。
- 最多 3 张；路径越界仍是硬错误。
- 缺失或损坏的正文图允许删除对应引用/标签后继续；封面不适用此降级。

### 6. Prepare

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py prepare \
  --job <WORK_DIR>/job.json
```

`prepare` 检查标题、1500—4000 字、humanize、正文图最多 3 张与路径安全，固定随机主题并生成封面规格。它不读取 `sources.md`，不重复检查热点时效，不要求图片计数声明。

### 7. Finish

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py finish \
  --job <WORK_DIR>/job.json \
  --config <PROJECT_ROOT>/wechat-accounts.json
```

`finish` 确定性重建正文 HTML 和封面，执行轻量草稿门禁后只调用一次 `send --action draft`：

- 不生成 preview，不执行独立 validate 阶段，不记录 leaf count 或文件哈希。
- 封面技术故障最多尝试两次；有账号默认封面则继续，否则停止。
- 正文图按真实字节检测格式，上传文件名和 MIME 采用真实格式；扩展名不一致不阻塞。
- 正文坏图可跳过；微信认证、上传或 API 故障不得伪装成图片降级。
- 同一任务 `finish` 使用文件锁，防止并发调用创建两个草稿。

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
