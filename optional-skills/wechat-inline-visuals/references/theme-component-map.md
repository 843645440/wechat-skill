# 当前主题与信息模块

流水线信息模块由 `render_article.py` 按 `insight` / `comparison` / `process` / `metrics` 四种语义渲染，不再使用已归档的 Markdown 组件编号。

`theme` 必须是 `render_article.py` 的 `THEMES` 标识。普通稿默认空计划；正式报道最多一张 `process` 事实脉络，文案必须来自正文原句。

| 主题标识 | 适用模块 |
|---|---|
| `moyu-green` `olive-journal` `peach-soft` | insight / comparison / process / metrics |
| `plain-white` `ink-rule` `deep-pool` `color-block` | insight / process；对比优先用正文表格 |
| `news-wire` `solemn-gray` `formal-brief` | process（事实脉络）；不用营销卡片 |
| `aurora-violet` `noir-gold` | insight / comparison / metrics |

不要按题材改主题：主题由 `prepare` 按 `run_id` 哈希固定（编辑稿不含通报皮）。模块只服务扫读，不补事实。
