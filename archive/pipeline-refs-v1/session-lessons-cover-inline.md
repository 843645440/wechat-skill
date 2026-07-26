# 会话沉淀：封面探针、正文配图、字数、humanize、假完成

供流水线排障与维护时快速对齐；细节仍以 `pipeline-failure-triage.md` / `execution-recovery.md` / `humanize-pass.md` 与脚本为准。

## 正文字数硬门禁（用户确认）

- 区间：**1500—4000** 可读字符（`count_body_chars`：去一级标题、代码围栏与 Markdown 噪声）。
- 拦截点：`prepare`；区间外 `RuntimeFailure`，不进排版。
- 长短：按已核实信息量——密则写长，薄则写够下限；禁止空话注水。
- 常量：`MIN_BODY_CHARS=1500` / `MAX_BODY_CHARS=4000`（`pipeline_runtime.py`）。
- 历史：曾有「只建议 1600–4000、不加硬门禁」的阶段；**以用户最新要求 1500–4000 硬门禁为准**。用户说「不修字数」时不要擅自加门禁；明确要求后再改常量与文档。

## 写后去 AI 味（humanizer-zh）

- 顺序：`write` → **`humanize`（一轮）** → 配图/封面 → `prepare` → finish。禁止跳过。
- **默认 intensity=`strong`**（`light`/`medium` 仅用户明确指定）。档位见 `humanize-pass.md`。
- Skill 路径优先级：
  1. **monorepo vendored（推荐）**：`wechat-skill/.agents/skills/humanizer-zh/`
  2. 独立副本：`creative/humanizer-zh/`（若并存，裸名会**歧义**；用完整路径加载）
- **不要用英文 `humanizer`** 处理中文公众号正文。
- 约束：不增事实、只改 `article.md`、改后仍 1500–4000、保留 `##`；strong 可有克制阅读反应，禁编造亲历。
- 阶段 detail 含 `intensity=strong`；`cmd_gate` 要求 humanize completed。
- Cron：`skills` 含 pipeline + humanizer-zh；prompt 写明 **默认 strong**。
- 半程成稿：停在 humanize，**对话贴全文**（`partial-run-delivery.md`）。

## 封面「浏览器内容探针执行失败」（历史，仅单独用 wechat-html-cover 时相关）

- **流水线封面已改生图 API**（`ai-cover-generation.md`），不再走 HTML/Chrome；以下仅供单独调用 `wechat-html-cover` 时排障。
- 本机常见：`apparmor_restrict_unprivileged_userns=1` → 非 root 完整 Chrome abort。
- 修复要点：`render_cover.py` 自动 `--no-sandbox --disable-setuid-sandbox`；优先 Playwright `chrome-headless-shell`；探针前建 profile 目录；错误带回 stderr。
- 流水线内封面失败：重试后仍失败时，仅当有默认 `thumb_media_id` 可 `skipped` 继续。

## 正文配图稳定性

- 当前主流程使用 `baoyu-article-illustrator`。
- `illustrations` 必须先 `running`，真实图片写入 `imgs/`、Markdown 引用插入 `article.md` 后才可 `completed`。
- 正文图 0—3 张：超过 3 张拒绝；单图失败重试一次后跳过；全部失败标 `skipped` 无图继续。`prepare` 检查路径不越界；引用文件不存在时删引用继续。

## 假完成 / Cron 中断 / 续跑

- 实战：cron 在 `write=running`、无 `article.md` 时输出「drafted」与虚构路径；调度器 `last_status=ok` 仅表示会话退出。
- 报告前必查：`state=drafted` + 非空 `draft_media_id` + 磁盘有 `article.md`/`article.html` + 封面 png 或默认封面兜底。
- **状态诊断**：`job.json` 的 `stages.*.status` + `work/<account>/current/` 文件列表 + 无相关进程 = 已中断；不要只看 cron list。
- 卡在 write/humanize 且已有 topic：优先**续跑**（补稿 → humanize → 配图/封面 → prepare → finish），不要无故 `init` 清选题；用户说「可以」续跑时直接接续。

## 账号选题

- `config/wechat-content-profiles.json`：`a` 熵增时刻（AI/科技/就业变化）；`b` 野路子（民生/建设）。无主题热点必须跟账号 `topic_discovery.categories`。

## 脚本路径

- 流水线入口在 `.agents/skills/wechat-content-pipeline/scripts/`，不是 monorepo 根 `scripts/`。
