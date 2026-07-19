---
name: wechat-content-pipeline
description: 编排中文微信公众号文章从给定选题或自动联网发现热点，到写作、事实来源留档、强制去 AI 味、随机主题基础排版、同主题原生 HTML 信息模块、确定性封面、严格校验和指定公众号草稿箱的完整流水线。用于外部 Agent 定时触发“自动抓热点并生成公众号草稿”，或用户给定主题后要求“一条龙写作排版并送入 A/B 账号草稿箱”时。本 Skill 不创建或管理定时任务，不进行公开发布，也不等待人工批准后才创建草稿。
---

# 微信公众号内容生产流水线

把项目内专项 Skill 串成一次自动任务。外部 Agent 负责触发时间；本 Skill 处理内容生产，并默认把结果直接送入指定账号草稿箱。

## 资源与能力路由

每次读取：

- [references/artifact-contract.md](references/artifact-contract.md)：账号临时工作区与阶段契约。
- [references/account-profiles.md](references/account-profiles.md)：账号内容偏好。
- [references/humanization-contract.md](references/humanization-contract.md)：强制去 AI 味与事实保护。

没有给定主题时再读取 [references/hotspot-discovery.md](references/hotspot-discovery.md)。按阶段使用：

- 写作：`../wechat-tech-insight-writer/SKILL.md`
- 去 AI 味：`../humanizer/SKILL.md`
- 排版与草稿上传：项目根目录 `SKILL.md`
- 原生信息模块：`../wechat-inline-visuals/SKILL.md`
- 确定性封面：`../wechat-html-cover/SKILL.md`

项目根目录通常是本 Skill 向上三级。若结构变化，向上查找同时包含根 `SKILL.md`、`scripts/validate_gzh_html.py` 和 `scripts/wechat_publish.py` 的目录；找不到就停止，不猜路径。

## 默认行为

- 必需输入只有账号别名。主题可选：有主题直接使用，没有主题就联网发现最新热点。
- 不保存 08:00、20:00 或 cron；由 Agent 自带定时任务配置。
- 每个账号复用 `work/<account>/current/`，新一轮覆盖上一轮临时产物。
- Humanizer 必须执行，之后必须复查事实和虚构内容。
- 从根 `references/theme-index.md` 随机选择一套已注册主题并固定到任务状态。
- 正文不生成 PNG、SVG 或截图，不调用生图模型，不上传正文视觉素材。
- AI 完成后直接创建草稿；人工在公众号草稿箱审核。
- 不自动公开发布，不调用公开发布接口。

## 工作流

### 1. 初始化账号工作区

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py init \
  --project-root <PROJECT_ROOT> --account a [--topic "给定主题"]
```

脚本会重建 `work/a/current/`。`article.md` 是各阶段共用正文，不要求用户提前准备。

### 2. 获取选题

已有主题就直接写作。没有主题时按热点发现规则联网检索，选择证据充分、适合账号读者的科技、AI、产业或民生热点并记录：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py topic \
  --job <WORK_DIR>/job.json --value "最终选题" --source auto-hotspot
```

没有网络或可靠热点时停止，不用旧闻或传闻凑稿。

### 3. 写作与来源留档

按 `wechat-tech-insight-writer` 生成：

- `article.md`：标题和完整正文。
- `sources.md`：内部事实来源、日期、链接和对应事实，不进入公众号正文。

当前事件、企业、数据和政策必须核验。非时效主题也要在 `sources.md` 说明未使用时效性事实。

### 4. 强制去 AI 味

读取 Humanizer 和人类作者化契约，完整编辑 `article.md`。保留主题、中心判断、事实、来源和长度级别；不得增加虚构经历、人物、对话、引用或数据。完成后对照 `sources.md` 复查事实，再将 `humanize` 标为完成。

### 5. 随机主题与基础排版

调用：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py choose-theme \
  --job <WORK_DIR>/job.json
```

使用返回主题和根排版 Skill 生成基础 `article.html`。同一次任务恢复时复用已选主题，不重新随机。此时先完整转换原文、保持所有事实和段落，不插入跨主题组件。

### 6. 提取并插入同主题原生信息模块

排版完成后读取 `wechat-inline-visuals`。从 `article.md` 和 `sources.md` 中选择适合视觉化的观点、比较、流程或已核验数据，生成 `inline-visuals.json`，先校验计划：

```bash
python3 <INLINE_ROOT>/scripts/validate_plan.py \
  --article <WORK_DIR>/article.md \
  --plan <WORK_DIR>/inline-visuals.json \
  --theme-index <PROJECT_ROOT>/references/theme-index.md
```

只从当前主题组件库复制对应组件，替换其中示例文字后插入 `article.html`。每篇 0—3 个；没有自然适合的内容时空计划是正常结果。模块不得相邻、不得重复正文长段、不得引入原文和来源之外的事实。

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name inline-visuals --status completed \
  --artifact inline_visuals=inline-visuals.json \
  --detail mode=native-html --detail module_count=<N>
```

该阶段不创建正文图片，不调用浏览器截图、生图 API、图片上传或 AI 视觉检测。

### 7. 生成封面

封面是草稿 API 的独立必需素材。读取 `wechat-html-cover`，根据最终标题和已选主题创建 `cover/cover.spec.json`。规格必须显式选择 `editorial-ledger` 或 `kinetic-type`，并提供与原题完全一致的两行标题和 0—2 个重点词。当前不按账号绑定模板；触发请求没有指定时可任选一套，但同一轮重试必须保持不变。随后用固定 HTML/CSS 模板截图一次：

```bash
python3 <COVER_ROOT>/scripts/render_cover.py \
  --spec <WORK_DIR>/cover/cover.spec.json \
  --html-output <WORK_DIR>/cover/cover.html \
  --output <WORK_DIR>/cover/cover.png
```

只做字段、PNG 签名和精确尺寸校验，不做 AI 视觉检测或审美重绘。浏览器故障最多原命令重试一次，不回退到生成式图片模型。失败时把 `cover` 标为 `skipped`；账号有默认封面则记录 `default_thumb_media_id=true`，否则记录 `false`，随后仍完成 HTML 校验。

### 8. 严格校验与预览

运行：

```bash
python3 <PROJECT_ROOT>/scripts/validate_gzh_html.py <WORK_DIR>/article.html
python3 <PROJECT_ROOT>/scripts/wrap_preview.py \
  <WORK_DIR>/article.html <WORK_DIR>/article_preview.html
```

ERROR、WARNING 和发布占位符全部清零，再标记 `validate` 完成。没有真实作者时删除署名组件，不保留占位符。

### 9. 自动写入指定账号草稿箱

先运行门禁：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py gate \
  --job <WORK_DIR>/job.json
```

通过后直接创建草稿：

```bash
python3 <PROJECT_ROOT>/scripts/wechat_publish.py \
  --config <PROJECT_ROOT>/wechat-accounts.json send \
  --account a --html <WORK_DIR>/article.html --title "最终标题" \
  --cover <WORK_DIR>/cover/cover.png --action draft --strict \
  --result-file <WORK_DIR>/draft-result.json
```

使用账号默认封面时省略 `--cover`。成功后记录 `draft_media_id` 并结束，不调用公开发布接口。门禁因封面不可用失败时保留文章与 HTML，不删除其它产物，也不回退到 AI 生图。

## 状态与输出

用 `pipeline_job.py stage` 更新各阶段。同一轮失败时保留工作区并从未完成阶段继续；下一次外部触发重新初始化当前账号工作区。

最终只报告：选题、随机主题、原生信息模块数量、目标账号、文章与预览路径、草稿创建结果。不要展示内部推理、密钥或内部来源记录。
