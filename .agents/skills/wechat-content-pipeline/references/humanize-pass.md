# 流水线内 Humanize

`article.md` 写完并通过 `check` 后、`prepare` 前执行一轮，只改这个文件。

## 先选声口

以 `user-brief.md` 为准：

- 标有“公共事件档案模式”或要求正式报道：`intensity=restrained`。保持克制、事实优先，不新增第一人称或表演性愤怒。
- 普通行业观点、科技与民生专栏：默认 `intensity=strong`。保留已有第一人称和锋利判断，但情绪必须钉在事实、机制、成本或责任上。
- 用户另有语气要求：服从用户，不用默认值覆盖。

两种模式都要删除套话、报告腔、机械排比、模糊权威和聊天机器人残留；都不得新增事实、亲历、人物、数据、引语或结论。

## 阶段记账

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name humanize --status running
# 就地改写 article.md 一轮
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name humanize --status completed \
  --detail 'pass=humanizer-zh;intensity=<strong|restrained>;voice=<brief声口>'
```

## 硬约束

1. 保留唯一 `#` 标题、必要 `##`、表格、引用、链接和少量关键词强调。
2. 标题 ≤32 字，纯正文仍为 1500—4000 字。
3. 忠实 brief 和 dossier；不改变裁判/调查结论的生效状态，不抬高指控。
4. 不写伪采访、伪亲历、推测动机或来源没有的现场细节。
5. 不添加聊天收尾、emoji、关注转发段和海报口号。
6. 只跑一轮；问题在本阶段内定点修正，不再做第二次全文改写。

## 完成标准

- `strong`：像懂行的人在表达判断，不像通稿；有情绪但不悬浮。
- `restrained`：像严肃编辑完成的正式叙述，清楚、有节奏，不猎奇、不煽动。
- 两者共同：事实未膨胀、必要限定仍在、结构未损坏、字数未越界。
