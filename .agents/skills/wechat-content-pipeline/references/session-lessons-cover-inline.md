# 会话沉淀：封面探针、inline-visuals、字数、humanize、假完成

供流水线排障与维护时快速对齐；细节仍以 `pipeline-failure-triage.md` / `execution-recovery.md` / `humanize-pass.md` 与脚本为准。

## 正文字数硬门禁（用户确认）

- 区间：**1500—4000** 可读字符（`count_body_chars`：去一级标题、代码围栏与 Markdown 噪声）。
- 拦截点：`prepare`；区间外 `RuntimeFailure`，不进排版。
- 长短：按已核实信息量——密则写长，薄则写够下限；禁止空话注水。
- 常量：`MIN_BODY_CHARS=1500` / `MAX_BODY_CHARS=4000`（`pipeline_runtime.py`）。
- 历史：曾有「只建议 1600–4000、不加硬门禁」的阶段；**以用户最新要求 1500–4000 硬门禁为准**。用户说「不修字数」时不要擅自加门禁；明确要求后再改常量与文档。

## 写后去 AI 味（humanizer-zh）

- 顺序：`write/sources` → **`humanize`（一轮）** → `prepare` → inline → finish。禁止跳过。
- Skill：`humanizer-zh`（`~/.hermes/skills/creative/humanizer-zh`，git：`op7418/Humanizer-zh`）。**不要用英文 `humanizer` 处理中文公众号正文。**
- 约束全文：`humanize-pass.md`（**默认 strong**；不增事实、不改 sources、改后仍 1500–4000、保留 `##` 与语义 Markdown、禁止伪第一人称经历）。
- 阶段：`stages.humanize` running→completed；`cmd_gate` 要求 humanize 已 completed。
- Cron：`skills` 须含 `wechat-content-pipeline` **与** `humanizer-zh`；prompt 写明 humanize 步骤。
- 文件内只留终稿，不要把「改写说明/模式列表」写进 `article.md`。

## 封面「浏览器内容探针执行失败」

- 本机常见：`apparmor_restrict_unprivileged_userns=1` → 非 root 完整 Chrome abort。
- 修复要点：`render_cover.py` 自动 `--no-sandbox --disable-setuid-sandbox`；优先 Playwright `chrome-headless-shell`；探针前建 profile 目录；错误带回 stderr。
- 复现：`python3 .agents/skills/wechat-html-cover/scripts/render_cover.py --spec work/<a|b>/current/cover/cover.spec.json --output /tmp/cover-probe.png --timeout 45`
- 成功：`status=ok`，PNG 1410×600。有默认 `thumb_media_id` 时可降级继续草稿，禁止 AI 生图回退。

## inline-visuals 稳定性（用户：不要老降级）

- `module_count=0` 先看 `job.json` → `stages.inline-visuals` 的 `degraded` / `reason` / `partial`。
- 「缺少字段：version」≠ 信息量不足。Agent 常写残缺 plan。
- **三层网**：
  1. `prepare` 写入 `{version,theme,modules:[]}` 空壳 + `plan_schema`
  2. `coerce_plan` / `coerce_module`：补顶层；`name`/`title`/`step`→`label`；`afterHeading`→`after_heading`；超长截断；缺 id 补 `inline-NN`；重写为规范键
  3. `salvage_plan`：整包失败时**按模块抢救**，只丢坏块（`partial=true`），不再因一个字段写错清空全部
- 仍会丢模块：锚点/证据不是原文、章节不存在、JSON 损坏、全部模块无效。
- 规范字段仍应直接写 `label`+`text`；别名是稳定网不是鼓励乱写。见 `../wechat-inline-visuals/references/plan-schema.md` 与 `validate_plan.py`。

## 假完成 / Cron 中断 / 续跑

- 实战：cron 在 `write=running`、无 `article.md` 时输出「drafted」与虚构路径；调度器 `last_status=ok` 仅表示会话退出。
- 报告前必查：`state=drafted` + 非空 `draft_media_id` + 磁盘有 `article.md`/`article.html`（或预览）+ 封面 png 或默认封面兜底。
- **状态诊断**：`job.json` 的 `stages.*.status` + `work/<account>/current/` 文件列表 + 无相关进程 = 已中断；不要只看 cron list。
- 卡在 write/fact-check/humanize 且已有 topic：优先**续跑**（补稿 → humanize → prepare → inline → finish），不要无故 `init` 清选题；用户说「可以」续跑时直接接续。

## 账号选题

- `config/wechat-content-profiles.json`：`a` 熵增时刻（AI/科技/就业变化）；`b` 野路子（民生/建设）。无主题热点必须跟账号 `topic_discovery.categories`。

## 脚本路径

- 流水线入口在 `.agents/skills/wechat-content-pipeline/scripts/`，不是 monorepo 根 `scripts/`。
