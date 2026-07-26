---
name: wechat-content-pipeline
description: 编排中文微信公众号文章：用户提供主题与大致思路后，完成写作、humanize、可降级正文配图、生图或用户指定封面、随机主题并写入指定公众号草稿箱。默认不自动选题、不扫热点；不公开发布。
---

# 微信公众号内容生产流水线

**默认模式：用户命题。** 外部 Agent 或用户给出主题 + 大致思路；本 Skill 负责扩写成稿并送到指定账号草稿箱。

- **禁止**在未获主题时自行联网选题、换题或「找个热点凑一篇」。
- **禁止**公开发布（仅草稿箱，除非用户另行明确要求发布）。

## 每次必读

- [references/user-brief.md](references/user-brief.md)：用户 brief 模板、缺项追问、忠实扩写边界。
- [references/artifact-contract.md](references/artifact-contract.md)：工作区、阶段和 `run_id`。
- [references/account-profiles.md](references/account-profiles.md)：账号内容偏好。
- 写作前读 [references/structure-rotation.md](references/structure-rotation.md)：结构池与近文轮换，防同质限流。
- 写完正文、prepare 前读 [references/humanize-pass.md](references/humanize-pass.md)，加载 `humanizer-zh`，默认 `strong`。
- 正文配图：用户已给图则直接用；否则读 `../baoyu-article-illustrator/SKILL.md` + [references/baoyu-illustrations-integration.md](references/baoyu-illustrations-integration.md)。
- 封面：用户已给封面则用用户图；否则读 [references/ai-cover-generation.md](references/ai-cover-generation.md)。
- 失败时读 [references/pipeline-failure-triage.md](references/pipeline-failure-triage.md)。
- 修改阶段、产物、门禁、图片降级、草稿幂等时，先读 [references/contract-simplification-migration.md](references/contract-simplification-migration.md)。

> 自动热点发现已**默认关闭**。历史文档 [references/hotspot-discovery.md](references/hotspot-discovery.md) 仅作归档；仅当账号档案显式 `topic_discovery.enabled=true` 且用户要求自动选题时才可读，且不得作为日常路径。

项目根目录通常是本 Skill 向上三级；固定入口为：

```text
pipeline_job.py init/topic/history/shape/stage/show
pipeline_runtime.py begin/prepare/finish
```

不得为单篇文章新建临时渲染脚本，不得公开发布。

## 固定工作流

### 1. 接收用户 brief（硬门禁）

用户须提供至少：

1. **主题**（一句话）
2. **大致思路**（要点、时间线、论点、素材或大纲，可短）

可选：目标读者、情绪、必须写到的点、禁止写的点、配图/封面路径、字数偏好。

缺主题或思路为空（只有一句话题目、无可展开材料）→ **停止并追问**，最多 1—2 个澄清问题。  
**不得**自行找热点填空。

将 brief 落盘（推荐）：

```text
work/<account>/current/user-brief.md
```

格式见 [references/user-brief.md](references/user-brief.md)。

### 2. 初始化

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py init \
  --project-root <PROJECT_ROOT> --account <ACCOUNT> \
  --topic "<用户主题>"
```

每次 `init` 生成新的 `run_id`。同账号使用 `work/<account>/current/`；存在 `running`、`failed` 或 `draft outcome=uncertain` 时不得覆盖。只有人工对账并明确丢弃旧任务时使用 `--force-new`。

不得因为同账号当天已经 `drafted` 而退出。新的 `run_id` 可以在同一天继续创建另一篇草稿。

### 3. 固化选题（用户提供，非自动发现）

先读近 7 天历史（**结构轮换**，不是为了换题）：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py history \
  --job <WORK_DIR>/job.json --days 7 --rotation
```

阅读 `rotation.blocked_*` / `preferred_*`，供 `shape` 选型。  
若用户主题与近文明显重复，**提示用户**是否仍要写，不得擅自改题。

写入选题（`source` 必须为 `provided`）：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py topic \
  --job <WORK_DIR>/job.json \
  --value "<用户主题>" \
  --source provided \
  --event-focus "<一句话核心，可来自 brief>" \
  --hook "<可选：点击理由，优先摘用户表述>" \
  --tension "<可选：核心矛盾，优先摘用户表述>" \
  --reader-stakes "<可选：读者关切，优先摘用户表述>"
```

- **禁止** `--source auto-hotspot`（除非档案显式开启且用户要求）。
- 不校验 48 小时热点时效。
- hook / tension / reader_stakes：用户 brief 有则提炼写入；没有则可从思路补全，并在 brief 中可注明「AI 补全」。
- 故事核写不出时 **回问用户**，不要 `discover=failed` 后偷偷换题。

`discover` 阶段语义：**brief 已确认**（不是「发现了热点」）。

### 4. 锁定文章结构（防同质）

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

若用户 brief 指定了结构/结尾方式（如「以人物结局收」「只写时间线与影响」），**优先用户**，在轮换池允许范围内选取最贴近的 shape；冲突时宁可放宽 opening/ending 提示用户，也不得写成与 brief 相反的模具文。

细则见 [references/structure-rotation.md](references/structure-rotation.md)。

### 5. 写作

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py begin \
  --job <WORK_DIR>/job.json
```

加载 `wechat-tech-insight-writer`，读取：

1. **`user-brief.md`（第一信源）**
2. 账号 `writer_instructions` / `voice`
3. job 的 hook/tension/reader_stakes 与 `article_shape`

生成 `article.md`：

- **忠实 brief**：不换题、不推翻用户主判断与事实线；可润色、补机制解释与可读结构。
- 叙述人与情绪：按账号声口；第一人称「我」可用，但勿为凑模板强行「我站哪边」「普通人怎么防」——结尾形态服从 brief（影响收束 / 人物结局 / 用户指定均可）。
- 标题 ≤32 字；禁止周报体。
- 按已锁 structure 组织，但 **内容顺序优先服务 brief 大纲**。
- 陌生主体 1—3 句简介（若 brief 读者需要）。
- **读者价值**服从题材：有可执行点再写清单；历史案件、人物传记类以认知增量与事实线为主，禁止硬塞防骗清单。
- 正文 1500—4000；禁止编造亲历；禁止把用户未提供的「内幕」写成既定事实。
- 用户指定配图路径时写入 Markdown，勿丢弃用户图去重生图。

### 6. Humanize

将 `humanize` 标为 `running`，按 `humanizer-zh` + [references/humanize-pass.md](references/humanize-pass.md) 就地改写，默认 `intensity=strong`，不新增事实，不删 brief 要求保留的时间线与结论。完成后 `completed`。

### 7. 正文配图

- **用户已给正文图**：复制到 `imgs/`，插入 `article.md`，`illustrations` → `completed`，detail 含 `backend=user_provided`。
- **未给图**：按 baoyu 分析 + 自有后端；0—3 张；失败可 `skipped`；禁止视觉审图。

### 8. 封面

- **用户已给封面**：写入 `cover/cover.png`，`cover` → `completed`，`backend=user_provided`。
- **未给**：按 [references/ai-cover-generation.md](references/ai-cover-generation.md) 生图；禁止 HTML 封面与视觉审图。

### 9. Prepare

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py prepare \
  --job <WORK_DIR>/job.json
```

检查标题、1500—4000 字、humanize、正文图最多 3 张与路径安全，固定随机主题。不读 `sources.md`，不做热点时效检查。

### 10. Finish

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py finish \
  --job <WORK_DIR>/job.json \
  --config <PROJECT_ROOT>/wechat-accounts.json
```

验收 `cover/cover.png`，轻量门禁后 `send --action draft`。同一任务 `finish` 文件锁防双草稿。

## 草稿幂等与恢复

- 同一 `run_id` 已成功：账号、动作、`run_id`、`draft_media_id` 全匹配时直接返回原结果。
- 新 `run_id`：允许同账号当天继续新草稿。
- timeout / EOF / 连接重置 / 响应不完整：`outcome=uncertain`，禁止自动重发。
- 凭证或账号配置错误在请求前：`preflight-failed`、`retry_safe=true`。
- IP 白名单错误（40164）：报告出口 IP，等待用户加白后**只重跑 finish**，不重写正文。

**失败任务恢复**（`state=failed` 且 draft 曾 running/uncertain）：重置 format/draft 为 pending，确认 `article.md` 契约后 prepare → finish。继续现有 worktree，禁止无故 init 新 job。

**运行中断恢复**（write 未完成）：有用户 brief 则按 brief 写完；**禁止**改为自动热点选题。

## 完成核验

同时满足才可报告成功：

1. `job.json.state == drafted`
2. `stages.draft.status == completed`
3. `draft-result.json` 账号、`action==draft`、`run_id` 一致
4. `draft_media_id` 非空且非占位符（不得含 dummy/fake/placeholder/test/mock/sample）

`draft-result.json` 只能由 `pipeline_runtime.py finish` 写入。Agent 不得手写伪造。

最终报告：主题、是否用了用户配图、主题皮肤、正文图数、账号、`article.html` 路径、草稿 ID。不得展示密钥。

## 与旧「自动热点」模式的关系

| 项 | 默认（当前） | 仅当显式开启 |
|----|----------------|--------------|
| 选题来源 | 用户 brief | `topic_discovery.enabled=true` 且用户要求 |
| 48 小时时效 | 不适用 | 仅 auto-hotspot |
| 无主题时 | 追问用户 | 可读归档 hotspot 文档 |
| 换题 | 禁止（除非用户同意） | 自动路径才可换候选热点 |
