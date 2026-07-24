# 流水线失败快速分诊

先读 `work/<account>/current/job.json`，再按阶段处理。不要凭记忆重跑整条流水线。

## 读取顺序

1. `state` 与各 `stages.*.status`。
2. `stages.*.details.message/reason/outcome/retry_safe/run_id`。
3. 对照 `article.md`、`imgs/`、`cover/cover.spec.json`、`cover/cover.png`、`article.html`、`draft-result.json`。

不存在 `sources.md`、`fact-check`、`validate`、预览、leaf count 或文件哈希 checkpoint；不要按旧契约补这些产物。

## 字数

- 正文可读字符必须为 1500—4000，不含一级标题与空白。
- `prepare` 报字数错误时，补真实的人群、流程、成本或限制，或删冗余；禁止重复注水。
- humanize 只执行一轮，不要用第二轮全文改写凑字。

## 正文配图

- 正文允许 0—3 张，目标尽量至少 1 张。
- 生成失败最多重试两次；仍失败则 `illustrations=skipped`，无图继续。
- `prepare` 会拒绝超过 3 张或路径越界；缺失引用会被移除。
- 发布器按真实字节和解码结果决定 MIME 与文件名，正文图扩展名不一致不阻塞。
- 缺失、损坏或不可解码的正文图会删除完整 `<img>` 标签并继续。
- 路径越界、有效图片上传失败、微信认证或 API 失败仍是硬错误。

## 封面

- 封面不使用正文图降级规则，错后缀、损坏或不可解码仍失败。
- HTML 封面技术故障最多尝试两次；有当前账号默认 `thumb_media_id` 则继续，否则门禁停止。
- AppArmor userns 限制时优先 `headless_shell` 或按封面 Skill 使用 no-sandbox 方案。

## 草稿

成功前核对：

- `state=drafted`
- `draft.status=completed`
- `draft-result.json.account` 正确
- `action=draft`
- 结果 `run_id` 与 job 一致
- `draft_media_id` 非空，且不是占位符（不含 `dummy`/`fake`/`placeholder`/`test`/`mock`/`sample`，不是纯数字序列）

**伪造结果检测**：若 `draft_media_id` 疑似占位符，说明 `finish` 跳过了真正的 `draft/add` API 调用。必须用 `pipeline_job.py stage` 将 draft 重置为 pending，然后重新执行 `prepare → finish`。Agent 不得手动创建或修改 `draft-result.json`。

同一 `run_id` 成功结果可复用；新 `run_id` 允许同账号当天继续创建。`finish` 使用任务级文件锁阻止并发重复提交。

若 `draft=running` 或 `outcome=uncertain`，不得自动重发。先人工核对微信草稿箱，确认远端结果后再决定是否重置。缺少凭证或账号配置等明确请求前错误记录为 `preflight-failed/retry_safe=true`。

禁止调用公开发布接口。
