# 流水线失败快速分诊

用于定时任务或 `finish` 后，`job.json` 已有阶段结果、需要判断“代码/环境问题还是 Agent 产物问题”。先读 `work/<account>/current/job.json`，再按阶段对号入座。不要凭记忆重跑整条流水线。

## 读取顺序

1. `state` 与各 `stages.*.status`（`completed` / `skipped` / `failed`）。
2. `stages.*.details.reason`、`message`、`degraded`。
3. 对照产物：`article.md`、`inline-visuals.json`、`cover/cover.spec.json`、`cover/cover.png`、`draft-result.json`。

## 字数（write → prepare，硬门禁）

- 契约：正文可读字符 **1500—4000**（不含一级标题与空白；`prepare` 机械统计并拦截）。
- 长短按已核实信息量决定：信息密则靠近上限，信息薄则写够下限；禁止空话注水。
- 症状：`prepare` 报 `article.md 正文字数 N 不在 1500—4000 字范围内`。
- 处置：回写作 Skill 在同一次写作中补人群/流程/成本/限制，或删冗；禁止二次“去 AI 味”全文改写凑字。
- 不要用重复段落或空话补字数。

## 信息模块（inline-visuals）

- 合法顶层**只能**是：`version`（=1）、`theme`（=本轮主题）、`modules`（0—3）。
- 空计划也必须是：

```json
{"version": 1, "theme": "<theme>", "modules": []}
```

- 稳定性策略（`validate_plan.py`）：
  1. **别名纠正**：`name`/`title`/`step`→`label`，`afterHeading`→`after_heading`，`type`→`kind` 等
  2. **超长截断**到 schema 上限；缺 `id` 自动补 `inline-NN`
  3. **按模块抢救**：整包失败时只丢坏块，保留有效模块（`partial=true`）
  4. 仅当 JSON 损坏或全部模块无效时才清空为 `modules: []`
- 仍会丢模块的情况：锚点/证据不是原文、章节不存在、同类型重复且无法并存。
- 处置：看 `degrade_reason`；改 coerce/salvage 或写作侧示例，不手改单篇 HTML，不循环重提。

## 封面（cover）

- 症状：`status=skipped`，`message` 含 HTML 封面失败；`reason` 含 `浏览器内容探针执行失败` / `No usable sandbox` / 探针超时。
- **不是**模板审美问题，也**不要**回退 AI 生图。
- 环境根因（本机已踩过）：
  1. Ubuntu 上 `apparmor_restrict_unprivileged_userns=1` 时，非 root 完整 Chrome 无沙箱会直接 abort。
  2. 渲染器须在检测该限制（或 root / `WECHAT_COVER_NO_SANDBOX=1`）时附加 `--no-sandbox --disable-setuid-sandbox`。
  3. 优先 Playwright **headless_shell**  
     `~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell`  
     完整 Chrome for Testing 在部分机器上 `--dump-dom` 会挂起。
- 复现命令（在 monorepo 根）：

```bash
python3 .agents/skills/wechat-html-cover/scripts/render_cover.py \
  --spec work/<account>/current/cover/cover.spec.json \
  --output /tmp/cover-probe.png --timeout 45
```

成功应返回 `status=ok`、PNG `1410x600`，`browser` 路径多为 headless_shell。
- 两次技术失败后：有账号 `default_thumb_media_id`（每账号独立永久素材 ID）则继续草稿；否则门禁停。详见 `execution-recovery.md`。

## 草稿（draft）

- 瞬时 TLS/超时/5xx：脚本侧最多再试一次。
- 成功后核对 `draft-result.json`：`account`、`action=draft`、`draft_media_id` 非空；`state=drafted`。
- 禁止自动 `publish`。

## 修复归属

| 现象 | 改哪里 |
|------|--------|
| 探针/sandbox/headless 候选 | `wechat-html-cover/scripts/render_cover.py` + 本文/execution-recovery |
| 字数门禁 1500—4000 | `pipeline_runtime.py`（`MIN_BODY_CHARS`/`MAX_BODY_CHARS`）+ writer/pipeline SKILL |
| plan 字段别名/单块失败清空全部 | `validate_plan.py` 的 `coerce_module` + `salvage_plan` |
| plan 缺 version 仍丢 modules | prepare 空壳 + `coerce_plan` + `render_article.coerce_plan_shape` |
| Agent 行为（短稿、烂 plan） | 对应 Skill 正文，不是临时改单篇 HTML |

更新 monorepo：`cd ~/.hermes/skills/wechat-skill && git pull`，再 `/reload-skills`。勿用 hub 重装覆盖可 pull 的 `.git`。
