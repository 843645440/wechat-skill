# 流水线失败快速分诊

先读 `work/<account>/current/job.json`，再按阶段处理。不要凭记忆重跑整条流水线。

## 读取顺序

1. `state` 与各 `stages.*.status`。
2. `stages.*.details.message/reason/outcome/retry_safe/run_id`。
3. 对照 `article.md`、`imgs/`、`cover/cover.png`（生图封面）、`prompts/cover.txt`、`article.html`、`draft-result.json`。

不存在 `sources.md`、`fact-check`、`validate`、预览、leaf count 或文件哈希 checkpoint；不要按旧契约补这些产物。

## 字数

- 正文可读字符必须为 2500—5000，不含一级标题与空白，且落在本篇 `body_band`：`short` 2500–3300、`mid` 3300–4200、`long` 4200–5000（边界值可落在相邻两档）。
- `##` 至少 `max(2, heading_count-1)` 个。
- `prepare` 报字数或小节错误时，补真实的人群、流程、成本或限制，或删冗余；禁止重复注水。
- humanize 只执行一轮，不要用第二轮全文改写凑字。humanize 后又改正文，`prepare`/`finish` 会标 `article_changed_after_humanize`。

## 写作质量

- `check` 是写作期反馈；`prepare` 和 `finish` 都会检查 humanize 后最终稿。
- 低于 75 分、存在 high/blocking 问题，或内置 scorer 不可用时，都会失败关闭。
- 按报错给出的 `score_draft.py --markdown` 命令逐项修复；不要重跑 humanize 刷分，也不要补假数据。
- 若报缺 brief、`event_focus` 或 `article_shape`，回到 stdout 的 `next_command` 补齐，不要手改阶段状态绕过。

## 正文配图

- 正文允许 0—3 张。没有引用时 `prepare` 直接 skipped，不阻塞草稿。
- 只有正文引用且文件存在才算 `user_provided`；`imgs/` 未引用文件会 warning。
- 生成失败最多重试两次；仍失败则 `illustrations=skipped`，无图继续。脚本生图成功后会裁底部约 7% 水印。
- `prepare` 会拒绝超过 3 张或路径越界；缺失引用会被移除。
- 发布器按真实字节和解码结果决定 MIME 与文件名；JPEG 末尾杂质会先尝试 Pillow 重编码。损坏图可删引用后继续。
- **不要**做视觉/OCR 审图；用户草稿箱人工核对。
- 路径越界、微信认证或 API 失败仍是硬错误。

## 封面

- 唯一入口是 `gen_cover_image.py --record-stage`，写入 `cover/cover.png`（见 `ai-cover-generation.md`）。
- 正式报道 / 公共事件会走 HTML 准确排标题（`build_cover_spec.py` / `render_cover.py`），这是降级链的一环，不是过时流程。
- `finish` 做机械检查（存在/非空/魔数），比例明显偏离 2.35:1 时 warning，**不做视觉/OCR 校验**。
- 按降级链取第一个可用后端：用户图 → 正式报道 HTML → 可选生图 → HTML/Pillow → 账号默认 `thumb_media_id`。
- **「没有生图能力」不是失败**：缺 `AGNES_API_KEY` 时脚本自动落到 HTML 或 `render_cover_fallback.py`（纯 Pillow，需要一款中文字体）。
- 兜底渲染报「找不到可渲染中文的字体」时，设置 `WECHAT_COVER_FONT=<字体文件绝对路径>` 重跑。
- 生图 API/落盘失败最多重试两次；各档全不可用时才 `skipped`，且必须有默认 `thumb_media_id`。
- 封面文件扩展名与真实格式不一致不算错误：发布器按魔数识别并规范化 MIME。

## 草稿

成功前核对：

- `state=drafted`
- `draft.status=completed`
- `draft-result.json.account` 正确
- `action=draft`
- 结果 `run_id` 与 job 一致
- `draft_media_id` 非空，且不是占位符（不含 `dummy`/`fake`/`placeholder`/`test`/`mock`/`sample`，不是纯数字序列）

**伪造结果检测**：若 `draft_media_id` 疑似占位符，说明 `finish` 跳过了真正的 `draft/add` API 调用。必须用 `pipeline_job.py stage` 将 draft 重置为 pending，然后重新执行 `prepare → finish`。Agent 不得手动创建或修改 `draft-result.json`。

同一 `run_id` 且 `content_fingerprint`（正文/HTML/封面/已引用图）未变才复用旧草稿；改图或改稿后重跑 `finish` 会新建草稿。新 `run_id` 允许同账号当天继续创建。`finish` 使用任务级文件锁阻止并发重复提交，结束后删除 lock 文件。

看一眼现状：`python3 <PIPELINE>/scripts/pipeline_job.py show --job <job.json>`，读输出里的 `summary`。

若 `draft=running` 或 `outcome=uncertain`，不得自动重发。先人工核对微信草稿箱，确认远端结果后再决定是否重置。缺少凭证或账号配置等明确请求前错误记录为 `preflight-failed/retry_safe=true`。

禁止调用公开发布接口。
