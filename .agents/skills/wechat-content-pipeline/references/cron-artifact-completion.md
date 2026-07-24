# Cron 草稿产物验收与自动续跑

## 适用场景

Hermes cron 驱动公众号生产时，模型可能正常输出进度报告、调度器也记录 `ok`，但流水线仍停在 `write`、`humanize` 或其他中间阶段。不能把模型会话正常结束当作草稿成功。

## 成功的唯一条件

对每个账号设置一个后置检查脚本。脚本应始终以退出码 0 输出一行 JSON：

```json
{"complete": true, "detail": "draft_media_id verified"}
```

检查应同时验证：

1. `work/<account>/current/job.json` 的 `state == "drafted"`；
2. `stages.draft.status == "completed"`；
3. `draft-result.json` 存在，且 `draft_media_id` 为非空字符串。

未满足时返回：

```json
{"complete": false, "detail": "说明缺失的状态或文件"}
```

不要把未完成作为检查脚本的非零退出：非零只保留给检查器自身无法执行的技术错误。

## Hermes cron 配置契约

在 job record 中设置：

```json
{
  "completion_check": "wechat_a_completion.py",
  "completion_retry_limit": 2
}
```

其中脚本路径相对于 `~/.hermes/scripts/`。调度器应在每一个 Agent 最终回复后执行检查：

- `complete=true`：才记录 cron 成功；
- `complete=false`：把 `detail` 作为续跑反馈，要求同一 Agent 在**现有工作区**继续，不得 `init` 新任务或只汇报进度；
- 重试上限后仍未通过：记录失败，并把检查详情作为错误原因。

这项机制是调度器级兜底，不替代流水线自身的 `prepare` / `finish` 门禁。

## 账号 A/B 检查脚本模板逻辑

脚本可由自身文件名取得账号，例如 `wechat_a_completion.py` → `a`，读取：

```text
<project-root>/work/a/current/job.json
<project-root>/work/a/current/draft-result.json
```

只输出验收 JSON，绝不打印 token、草稿 media ID 或完整微信 API 响应。

## 部署与验证

1. 先用当前未完成工作区运行检查脚本，确认它返回 `complete=false`；再用一个已草稿完成的工作区确认 `complete=true`。
2. 将两个账号任务都绑定检查脚本和有限续跑次数。
3. 手动触发一个真实任务，最后直接再次执行检查脚本；同时检查 `job.json`、HTML、正文图、预览和草稿结果。
4. 修改 `cron/scheduler.py` 后，必须从**外部终端**重启 gateway 以加载代码：

   ```bash
   systemctl --user restart hermes-gateway.service
   ```

   在 gateway 自己处理的聊天/工具进程里不要尝试自重启；使用独立终端。

## 报告规则

只在后置检查通过后报告“已进入草稿箱”。若检查失败，报告停留阶段和检查详情，不能用 cron 的 `last_status=ok` 覆盖产物事实。