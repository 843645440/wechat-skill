---
name: wechat-content-pipeline
description: 编排中文微信公众号文章从选题或自动联网发现热点，到写作、事实来源留档、强制去 AI 味、正文配图、封面、随机主题排版、严格校验和指定公众号草稿箱的完整流水线。用于外部 Agent 定时任务触发“自动抓热点并生成公众号草稿”，或用户给定主题后要求“一条龙写作配图排版并送入 A/B 账号草稿箱”时。本 Skill 不创建或管理定时任务，不进行公开发布，也不等待人工批准后才创建草稿。
---

# 微信公众号内容生产流水线

把项目内专项 Skill 串成一次自动任务。外部 Agent 负责何时触发；本 Skill 只处理触发后的内容生产，并默认把结果直接送入指定账号草稿箱。

## 资源与能力路由

每次读取：

- [references/artifact-contract.md](references/artifact-contract.md)：账号临时工作区与阶段契约。
- [references/account-profiles.md](references/account-profiles.md)：账号内容偏好。
- [references/humanization-contract.md](references/humanization-contract.md)：强制去 AI 味与事实保护。

没有给定主题时再读取 [references/hotspot-discovery.md](references/hotspot-discovery.md)。按阶段使用：

- 写作：`../wechat-tech-insight-writer/SKILL.md`
- 去 AI 味：`../humanizer/SKILL.md`
- 确定性封面与正文配图：`../wechat-html-visuals/SKILL.md`
- 排版与草稿上传：项目根目录 `SKILL.md`

项目根目录通常是本 Skill 向上三级。若结构变化，向上查找同时包含根 `SKILL.md`、`scripts/validate_gzh_html.py` 和 `scripts/wechat_publish.py` 的目录；找不到就停止，不猜路径。

## 默认行为

- 必需输入只有账号别名。主题可选：有主题直接使用，没有主题就联网发现最新热点。
- 不在 Skill 内保存 08:00、20:00 或 cron；这些由 Agent 自带定时任务配置。
- 每个账号只使用一个内部临时工作区 `work/<account>/current/`。新一轮会覆盖该账号上一轮临时产物，不建立文章历史目录。
- Humanizer 是必经阶段，不是可选项；处理后必须复查事实和禁止虚构。
- 从 `references/theme-index.md` 当前已注册主题中随机选择一套并写入任务状态，不按账号固定主题。
- AI 完成后自动创建草稿，不等待人工批准。人工审核发生在微信公众号草稿箱。
- 不自动公开发布，不调用公开发布接口。

## 工作流

### 1. 初始化账号工作区

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py init \
  --project-root <PROJECT_ROOT> --account a [--topic "给定主题"]
```

脚本会重建 `work/a/current/`。`article.md` 是各阶段共用的正文文件，不要求用户提前准备。

### 2. 获取选题

如果初始化时已有主题，直接进入写作。没有主题时，按热点发现规则联网检索，选出一个证据充分且适合账号读者的科技、AI、产业或民生热点，然后记录：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py topic \
  --job <WORK_DIR>/job.json --value "最终选题" --source auto-hotspot
```

没有网络或没有可靠热点时停止，不用旧闻或传闻凑稿。

### 3. 写作与来源留档

按 `wechat-tech-insight-writer` 写作并保存：

- `article.md`：标题和完整正文。
- `sources.md`：内部事实来源、日期、链接和对应事实；不追加到公众号正文。

当前事件、企业、数据和政策必须核验。通用非时效主题也要在 `sources.md` 说明未使用时效性事实。

### 4. 强制去 AI 味

读取 Humanizer 和人类作者化契约，对 `article.md` 完整编辑一次。必须保留原主题、中心判断、事实、来源和长度级别；不得增加第一人称经历、人物、对话、引用、数据或未经来源支持的判断。

完成后重新核对 `sources.md` 与正文。发现事实漂移就恢复原事实并重新编辑，直到同时满足自然表达和事实安全，再将 `humanize` 标为完成。

### 5. 正文配图与封面

读取 `wechat-html-visuals`，从最终正文已有信息生成 2—3 张受约束 JSON 视觉图和一张封面。正文优先组合观点卡、比较图、流程图或数据卡，输出到 `illustrations/` 并把 PNG 相对路径插入 `article.md`；封面输出到 `cover/cover.png`。同一篇文章使用同一视觉主题。

每张图固定经过“JSON 字段校验 → HTML/CSS 模板 → Chrome/Chromium 截图 → PNG 签名与尺寸校验”。**不得调用 Agnes、其他生成式图片模型或 AI 视觉检测，不得生成 V2/V3，不得因审美细节重复渲染。**浏览器进程崩溃时允许同一命令技术性重试一次；成功后在阶段详情记录 `backend=html`、`visual_check=not-required`、`render_count=1`。

每张图使用同一命令形态，所有路径使用绝对路径：

```bash
python3 <VISUAL_ROOT>/scripts/render_visual.py \
  --spec <WORK_DIR>/illustrations/specs/01-insight.json \
  --html-output <WORK_DIR>/illustrations/01-insight.html \
  --output <WORK_DIR>/illustrations/01-insight.png

python3 <VISUAL_ROOT>/scripts/render_visual.py \
  --spec <WORK_DIR>/cover/cover.spec.json \
  --html-output <WORK_DIR>/cover/cover.html \
  --output <WORK_DIR>/cover/cover.png
```

阶段更新参数必须使用 `key=value`，例如：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name illustrate --status completed \
  --artifact illustrations=illustrations \
  --detail backend=html --detail visual_check=not-required --detail render_count=1
```

正文配图后端不可用时将 `illustrate` 标为 `skipped` 后继续。封面不可用时也标为 `skipped`：账号配置了默认封面素材就记录 `default_thumb_media_id=true`，否则记录 `false`。**图片或封面不可用不得提前终止任务，必须继续完成随机主题、排版和 HTML 校验；只在第 8 步门禁阻止草稿上传，也不得回退到 AI 生图。**

### 6. 随机选择排版主题

读取根目录 `references/theme-index.md`，提取全部已注册主题标识，调用：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py choose-theme \
  --job <WORK_DIR>/job.json
```

脚本直接从根 `theme-index.md` 读取当前已注册主题并返回随机结果。使用该主题排版；同一次任务恢复时复用已选主题，不重新随机。

### 7. 排版和严格校验

用根排版 Skill 的全自动模式生成：

- `article.html`：纯公众号正文片段。
- `article_preview.html`：本地预览。

没有真实作者时省略署名组件，不保留占位符。运行：

```bash
python3 <PROJECT_ROOT>/scripts/validate_gzh_html.py <WORK_DIR>/article.html
python3 <PROJECT_ROOT>/scripts/wrap_preview.py \
  <WORK_DIR>/article.html <WORK_DIR>/article_preview.html
```

ERROR、WARNING 和发布占位符均清零，再标记 `validate` 完成。

### 8. 自动写入指定账号草稿箱

先运行确定性门禁：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py gate \
  --job <WORK_DIR>/job.json
```

通过后立即创建草稿，不询问人工批准。若门禁只因封面和默认素材都不可用而失败，保留已完成的文章与 HTML 并报告草稿阻塞，不回退或删除其它阶段产物：

```bash
python3 <PROJECT_ROOT>/scripts/wechat_publish.py \
  --config <PROJECT_ROOT>/wechat-accounts.json send \
  --account a --html <WORK_DIR>/article.html --title "最终标题" \
  --cover <WORK_DIR>/cover/cover.png --action draft --strict \
  --result-file <WORK_DIR>/draft-result.json
```

如果使用账号默认封面素材则省略 `--cover`。成功后记录 `draft_media_id` 并标记 `draft` 完成。到此结束，不调用公开发布接口。

## 状态与输出

用 `pipeline_job.py stage` 更新每个阶段。阶段失败时保留当前账号工作区；同一轮重试从未完成阶段继续。下一次新的定时触发会重新初始化并覆盖该账号工作区。

最终只报告：选中的热点或给定主题、随机主题、目标账号、文章/预览路径和草稿创建结果。不要展示内部推理、密钥或来源工作记录。
