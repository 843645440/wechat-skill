# 计划壳字段与 coerce

## 合法顶层

只能三字段：

```json
{"version": 1, "theme": "<SELECTED_THEME>", "modules": []}
```

禁止 `{"modules":[]}` alone。`version` 必须是整数 `1`（字符串 `"1"` 由 coerce 归一）。

## 流水线约定

1. `prepare` 先写当前主题的空壳 plan。
2. Agent 只写一次完整 `inline-visuals.json`；覆盖时不得删 `version`/`theme`。
3. `validate_plan.coerce_plan`：补顶层，**保留 modules**。
4. `render_article.coerce_plan_shape`：二次兜底。
5. 只有锚点/证据/结构真失败才降级清空 modules。

## 排障

- `job.json` → `stages.inline-visuals`：`degraded`、`reason`、`module_count`。
- `reason` 含「缺少字段：version」→ 壳字段问题，不是信息量不够。
- 分诊：`../wechat-content-pipeline/references/pipeline-failure-triage.md`。
