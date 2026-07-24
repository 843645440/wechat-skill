# 定时流水线跨层可靠性

用于排查“cron 已触发但草稿不存在”、模型总结请求崩溃、自动选题重复，以及生成图片上传前格式异常。业务状态、Agent 运行时和媒体产物必须分层验证，不能用任一层的成功替代另一层。

## 1. 从产物反推真实状态

1. cron 的 `last_status=ok`、`execution_success=true` 或会话正常退出，只证明 Agent 进程结束。
2. 读取 `work/<account>/current/job.json`，以 `state` 和具体失败阶段为准。
3. 只有 `state=drafted`、`stages.draft.status=completed` 且 `draft-result.json.draft_media_id` 非空，才算完成。
4. 对 `[SILENT]` 任务检查 `updated_at` 的服务器本地日期；昨天的 `drafted` 不能视为今天完成。
5. `failed/uncertain` 工作区不得直接覆盖。先判断失败发生在外部 POST 前还是结果可能已提交。

## 2. 自动热点必须机械去重

提示词里的“避免重复”不是门禁。维护账号级持久历史，例如 `work/<account>/topic-history.json`：

- 记录选题、选中时间和证据 URL；覆盖 `current/` 前先归档当前选题。
- 默认比较近 30 天历史。
- 任一证据 URL 重合即按同一事件拒绝。
- 对标题规范化后做字符 n-gram 相似度；高相似标题即使替换同义词也拒绝。
- 机械拒绝后必须换事件，不得继续围绕原事件改标题。
- 历史文件与账号绑定，原子写入，并限制条目数量。

回归测试至少包含：同一事件换措辞被拒绝、不同事件通过、新选题写入历史、重新初始化后历史仍保留。

## 3. Responses 总结请求的工具字段必须成组移除

最大迭代数后的总结通常是无工具请求。如果正常请求构造器先生成了：

```text
tools
tool_choice
parallel_tool_calls
```

总结和总结重试路径必须同时移除三者。只删 `tools` 会形成孤立的 `tool_choice`，部分 Responses provider 会返回“设置了 tool_choice 但没有 tools”的 400。

定向回归测试应让 `_build_api_kwargs` 返回三个字段，截获最终总结 kwargs，并断言三者全部不存在。初次总结和空响应后的重试分支都要覆盖。

## 4. 图片格式以真实字节为准

生成服务的 URL 后缀、`Content-Type`、存储文件名可能与真实编码不一致。下载或 base64 解码后，用文件签名判断 PNG、JPEG、WebP、GIF：

- PNG：`89 50 4E 47 0D 0A 1A 0A`
- JPEG：`FF D8 FF`
- GIF：`GIF87a` / `GIF89a`
- WebP：`RIFF....WEBP`

真实格式与声明不一致时，保存为与真实编码匹配的后缀，并让正文引用该路径。`public_url` 和临时 URL 都应在工具返回前落盘，避免过期和后续消费者重新猜格式。0 字节文件必须视为生成失败，不能标记 illustrations 完成。

回归测试应覆盖：伪装为 `.png` 的 JPEG、URL 后缀与真实字节冲突、`public_url` 被缓存为本地文件、空响应拒绝。

## 5. 恢复边界

- 能证明错误发生在微信 POST 前，例如本地图片格式预检失败，可修复产物后显式重置 draft 阶段再续跑。
- timeout、EOF、连接重置或响应落盘失败无法证明 POST 未发生，必须保持 `uncertain/retry_safe=false`，先人工核对草稿箱。
- 正文和配图已完成时只恢复失败阶段，不重写正文、不重新选题。
- 0 字节图片必须重新生成；仅改扩展名无效。

## 6. 验证顺序

1. 对修改文件运行语法检查和 diff whitespace 检查。
2. 运行选题历史、请求构造和图片缓存的定向回归测试。
3. 运行公众号流水线完整测试组。
4. 确认 cron 实际加载的源码路径；长驻 gateway 只有在用户已授权时才重启，使核心代码修改生效。
5. 手动触发单个账号后立即复查 `job.json`、实际图片格式和 `draft_media_id`，不要仅看 cron 状态。
