# 半程交付与 Tavily 选题（会话约定）

## 半程停

用户明确要求「不要再往下 / 只写到去 AI 味 / 完整文章发我 / 先别排版封面草稿」时：

1. 做完：用户 brief（例外路径才自动选题）→ 写作 → **一轮** `humanizer-zh`（**默认 strong**）。
2. **停止**：禁止正文配图、`prepare`、cover、`finish`、发布。
3. **对话贴全文**：去 AI 后的完整 Markdown（`#` 标题 + 正文），不要只丢路径。
4. 一行附注即可：本地路径 + 约略字数。不要追问“要不要继续跑完”。
5. 半程演示可不 `pipeline_job init`；定时日更/要进草稿箱时仍走完整 init→…→finish。

## Tavily 选题（仅例外路径）

- 仅当账号 `topic_discovery.enabled=true` 且用户明确要求自动选题时可用；默认主路径是用户 brief（见 [user-brief.md](user-brief.md)）。
- 本机默认 `web.backend: tavily`；密钥 `TAVILY_API_KEY` + 可选 `TAVILY_API_KEY_2`。
- 操作细则：[tavily-hotspot-discovery.md](tavily-hotspot-discovery.md)
- 与通用热点规则合用：[hotspot-discovery.md](hotspot-discovery.md)（已归档）

## Humanize 硬边界（公众号）

与 [humanize-pass.md](humanize-pass.md) 一致，再强调：

- 禁止为“有人味”编造第一人称经历/伪访谈。
- 人味 = 节奏 + 判断 + 具体机制（谁/环节/成本/限制）。
- 改后仍 1500—4000 字；只一轮。

## 与 SKILL 主文关系

选题与门禁契约以主 `SKILL.md` + `artifact-contract.md` 为准；本文件只补充「半程停」的交付约定。
