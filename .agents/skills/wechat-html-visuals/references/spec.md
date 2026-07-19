# 视觉图 JSON 规格

所有 JSON 使用 UTF-8。未知字段、空字段、超长文字和错误数组长度会在浏览器启动前被拒绝。`theme` 可选值为 `emerald`、`indigo`、`amber`、`slate`。

## 通用约束

- 不使用 Markdown、HTML 或换行标签。
- 标题和条目必须来自文章已有内容。
- 正文卡片固定 1200×800；封面固定 1410×600。
- 同一篇文章的所有 JSON 使用同一个 `theme`。

## cover

```json
{
  "kind": "cover",
  "theme": "emerald",
  "eyebrow": "AI 与产业观察",
  "title": "模型变便宜之后，真正昂贵的是什么",
  "subtitle": "企业竞争正在从参数转向工作流程"
}
```

限制：`eyebrow` 最多 18 字，`title` 最多 28 字，`subtitle` 最多 40 字。三项都必须填写。

## insight

```json
{
  "kind": "insight",
  "theme": "emerald",
  "title": "效率提高之后，压力转移给了谁",
  "subtitle": "同一项技术在不同岗位上产生的结果并不相同",
  "points": [
    {"label": "一线员工", "text": "重复操作减少，但产出要求可能同步提高"},
    {"label": "技术主管", "text": "需要承担工具选择、复核和责任划分"},
    {"label": "中小企业", "text": "模型费用下降，流程改造仍然需要投入"}
  ]
}
```

限制：`title` 24 字，`subtitle` 44 字；`points` 2—4 项，`label` 10 字，`text` 42 字。

## comparison

```json
{
  "kind": "comparison",
  "theme": "indigo",
  "title": "演示效果与真实部署的差距",
  "left": {
    "heading": "演示阶段",
    "items": ["任务边界清楚", "环境经过筛选", "失败成本较低"]
  },
  "right": {
    "heading": "生产环境",
    "items": ["输入经常变化", "需要稳定复核", "责任必须可追溯"]
  },
  "footer": "模型能力只是起点，部署能力决定最终体验"
}
```

限制：`title` 24 字；两侧 `heading` 12 字，各 2—4 条，每条 28 字；`footer` 36 字。

## process

```json
{
  "kind": "process",
  "theme": "amber",
  "title": "一项 AI 能力进入企业的五个环节",
  "subtitle": "编号由模板自动生成",
  "steps": [
    {"label": "选场景", "text": "找到高频且边界明确的任务"},
    {"label": "接数据", "text": "整理权限、格式和更新机制"},
    {"label": "做复核", "text": "明确人工检查与异常处理"},
    {"label": "算成本", "text": "核算调用、维护和培训投入"},
    {"label": "定责任", "text": "保留记录并划分决策责任"}
  ]
}
```

限制：`title` 24 字，`subtitle` 36 字；`steps` 3—5 项，`label` 10 字，`text` 28 字。不要提供编号字段。

## metrics

```json
{
  "kind": "metrics",
  "theme": "slate",
  "title": "真正需要计算的四类成本",
  "subtitle": "只使用正文和来源中已经核实的数据或概念",
  "metrics": [
    {"value": "调用成本", "label": "模型与算力", "note": "随使用规模和频率变化"},
    {"value": "改造成本", "label": "流程与系统", "note": "通常高于单次模型费用"},
    {"value": "复核成本", "label": "人员与责任", "note": "高风险场景不能省略"}
  ]
}
```

限制：`title` 24 字，`subtitle` 44 字；`metrics` 2—4 项，`value` 12 字，`label` 12 字，`note` 28 字。
