# 公众号流水线约束（覆盖通用 humanizer 建议）

当输入来自 `wechat-content-pipeline` 的 `article.md` 时：

1. **就地覆盖** `article.md`；不改 `sources.md`。
2. **只改一轮**；文件内只留终稿，不要写“所做更改”清单。
3. 字数 **1500—4000**；保留 `#` / `##` 与必要表格、少量加粗。
4. **禁止编造**第一人称经历、现场见闻、未核访对话——即使通用 humanizer 文鼓励“适当使用我 / 注入灵魂”。公众号事实稿的人味来自短句节奏、明确判断、具体机制（谁、环节、成本、限制）。
5. 用户只要「去 AI 后全文」：对话输出终稿即可；非用户要求不要附长 diff。
6. 详细硬约束见流水线 `wechat-content-pipeline/references/humanize-pass.md`。
