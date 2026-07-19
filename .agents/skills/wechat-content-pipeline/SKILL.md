---
name: wechat-content-pipeline
description: 编排中文微信公众号文章从给定选题或自动联网发现热点，到写作、来源留档、随机主题、原生 HTML 信息模块、确定性封面、严格校验和指定公众号草稿箱的完整流水线。用于外部 Agent 定时触发“自动抓热点并生成公众号草稿”，或用户要求将给定主题一条龙送入 A/B 账号草稿箱时。本 Skill 不创建定时任务、不公开发布，也不等待人工确认后才创建草稿。
---

# 微信公众号内容生产流水线

外部 Agent 负责触发时间；本 Skill 自动完成内容生产并以指定账号草稿箱为终点。

## 每次必读

- [references/artifact-contract.md](references/artifact-contract.md)：工作区、产物和阶段状态。
- [references/account-profiles.md](references/account-profiles.md)：账号内容偏好。
- [references/execution-recovery.md](references/execution-recovery.md)：失败降级和重试边界。
- 没有给定主题时再读 [references/hotspot-discovery.md](references/hotspot-discovery.md)。
- 写作时读 `../wechat-tech-insight-writer/SKILL.md`；信息计划读 `../wechat-inline-visuals/SKILL.md`。

项目根目录通常是本 Skill 向上三级。若结构变化，只向上查找同时含根 `SKILL.md`、`scripts/validate_gzh_html.py` 和 `scripts/wechat_publish.py` 的目录；找不到就停止。

## 不可绕过的运行契约

完整流水线只允许使用以下入口：

```text
pipeline_job.py init/topic/show
pipeline_runtime.py begin/prepare/finish
```

`pipeline_runtime.py` 是排版、信息模块、封面、校验、预览、门禁和草稿上传的唯一编排器。不得为单篇文章新建 Python、JavaScript、Shell 或 HTML 渲染脚本；不得手工拼接主题组件、手写封面 JSON、直接调用内部渲染脚本或用其它 Skill 替代失败步骤。现有脚本失败时按规定降级或停止，不现场开发新实现。

Agent 只保留三类判断工作：

1. 从可靠来源选择一个热点和写作角度。
2. 生成一次最终 `article.md` 与 `sources.md`。
3. 生成一次 `inline-visuals.json`；失败后不再修正或重写。

主题、封面模板、标题分行、高亮词、HTML 组件、阶段计时、重试、门禁和上传全部交给固定脚本。不得调用图片模型或 AI 视觉检测。不得公开发布。

## 固定工作流

### 1. 初始化

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py init \
  --project-root <PROJECT_ROOT> --account <ACCOUNT> [--topic "给定主题"]
```

只使用 `work/<account>/current/`；新任务覆盖同账号旧临时产物，不建立文章历史目录。

### 2. 确定选题

触发请求有主题时直接使用。没有主题时，按热点规则联网检索并只记录一个最佳选题：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name discover --status running
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py topic \
  --job <WORK_DIR>/job.json --value "最终选题" --source auto-hotspot
```

没有可靠热点时停止，不用旧闻、传闻或候选清单凑稿。

### 3. 写作和来源

先启动真实计时：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py begin \
  --job <WORK_DIR>/job.json
```

按写作 Skill 一次生成：

- `article.md`：唯一一级标题和完整正文，根据信息密度写 1600—4000 字。
- `sources.md`：机构、标题、日期、链接及支撑事实，不进入正文。

标题不超过 32 字，必须包含可识别主体或对象、明确动作和现实落点。保持受影响最深人群视角，不调用第二个全文改写或“去 AI 味”步骤。

### 4. 固定主题并交接唯一信息计划

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py prepare \
  --job <WORK_DIR>/job.json
```

该命令机械核验正文和来源、完成写作计时、随机固定注册主题、稳定选择两套封面模板之一，并自动生成合法封面规格。读取命令返回的 `theme` 和 `plan` 路径，按 `wechat-inline-visuals` 只写一次 `inline-visuals.json`。没有自然适合的模块就写当前主题的空计划；不要凑数量。

### 5. 一次完成排版到草稿

生产任务必须运行：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_runtime.py finish \
  --job <WORK_DIR>/job.json \
  --config <PROJECT_ROOT>/wechat-accounts.json
```

该命令固定执行：

1. 校验信息计划；失败立即覆盖为空计划，不重试。
2. 一次生成正文与同主题信息模块，保留全部原文。
3. 用 HTML/CSS 生成 1410×600 封面；单次硬超时 45 秒，不做视觉审查。技术故障只重试一次，随后使用账号默认封面或停止。
4. 对正文执行零 ERROR、零 WARNING 严格校验并生成预览。
5. 通过草稿门禁后只调用 `send --action draft`；微信瞬时网络错误最多重试一次。
6. 校验账号、动作和 `draft_media_id`，状态变为 `drafted` 后结束。

开发测试才允许增加 `--dry-run`；它会走完整机械流程和草稿输入校验，但不连接微信 API。`--skip-draft` 仅用于故障诊断，不得用于定时生产。

## 失败和恢复

- 信息计划或插入失败：标记 `skipped`、`degraded=true`，以纯正文继续，不重试。
- 封面两次技术尝试均失败：有默认封面则继续，没有则门禁停止；不回退 AI 生图。
- HTML 有任何错误、警告或占位符：停止草稿创建。
- 草稿成功后立即停止，不调用公开发布接口。
- 同一轮失败保留工作区；恢复时读取 `job.json`，不得重新随机主题或模板。

## 最终报告

只报告选题、主题、信息模块数量及是否降级、目标账号、各阶段 `duration_ms`、文章与预览路径和草稿结果。不要展示内部推理、密钥或 `sources.md` 内容。
