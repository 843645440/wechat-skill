---
name: wechat-inline-visuals
description: 从已完成写作的微信公众号文章中提取观点、对比、流程或已核实数据，并交给固定渲染器一次生成当前主题的公众号正文与原生 HTML 信息模块。用于已选定排版主题后增强手机端扫读体验，同时不生成正文图片、不调用图片模型、不让 Agent 临时编码排版的场景。
---

# 微信公众号原生信息模块

从 `article.md` 提取 0—3 个语义模块，再由流水线固定渲染器把正文和模块一次写入 `article.html`。最终模块是公众号正文 HTML，不是 PNG。

## 输入

必须同时取得：

- 最终 `article.md` 和内部 `sources.md`。
- 本轮已固定的主题标识。

先读 [references/plan-schema.md](references/plan-schema.md)。`theme-component-map.md` 仅保留为旧组件对应关系参考，流水线不再要求 Agent 按它手工组装 HTML。

## 工作流

被 `wechat-content-pipeline` 调用时，本 Skill 只负责一次生成 `inline-visuals.json`；随后立即交还 `pipeline_runtime.py finish`。不要自行运行校验器或渲染器，因为统一运行器会机械完成校验、降级和排版。下面的校验与渲染步骤只用于单独调用本 Skill 的场景。

1. 从文章已有内容识别最值得扫读的结构。优先顺序为：核心影响对象、清晰二元对比、真实流程、已核实数据。
2. 只在内容自然成立时选 1—3 个模块；没有合适内容时输出空 `modules`，不得为凑数量制造结构。
3. 只尝试一次，写入 `inline-visuals.json`，每个模块记录原文锚点和原文证据。运行：

```bash
python3 <SKILL_ROOT>/scripts/validate_plan.py \
  --plan <WORK_DIR>/inline-visuals.json \
  --article <WORK_DIR>/article.md \
  --theme-index <PROJECT_ROOT>/references/theme-index.md \
  --degrade-on-error --fallback-theme <SELECTED_THEME>
```

4. 校验失败时接受脚本生成的当前主题空计划，不修改字段、不重新提取、不重试。
5. 调用 `wechat-content-pipeline/scripts/render_article.py`，由固定组件按 `placement.after_heading` 和 `placement.after_text` 一次完成正文与模块排版。不得手工复制主题组件，不得为当前文章新写 Python、HTML 模板或二次插入脚本。
6. 渲染器若发现插入异常，会把计划降级为空并保留完整纯正文 HTML；记录降级原因后继续。最后运行根目录的 `validate_gzh_html.py`，ERROR、WARNING、占位符必须全部清零。

## 提取边界

- `insight`：2—4 个受影响对象、成本承担者或关键判断。
- `comparison`：两个对象或阶段在同一维度下的真实差异。
- `process`：正文明确支持的 3—5 个连续环节。
- `metrics`：2—4 个正文和来源已经核实的数据；没有可靠数字时改用 `insight`。

同篇不要重复模块类型，不要连续插入两个模块，不要把标题、导读或结尾 CTA 重新包装成模块。

## 硬性限制

- 不新增事实、数字、公司表述、人物、引用、因果关系或作者经历。
- 不把推测压缩成事实，不删除“可能”“短期内”“仍取决于”等限制条件。
- 不直接解析或改写 `sources.md` 成正文；来源只用于回查。
- 不生成正文 PNG、SVG 文件或截图，不调用 Agnes、Baoyu 或任何图片模型。
- 输出必须遵守根排版 Skill 的微信红线：内联样式、`<span leaf="">`、无 `class`、无 `<style>`、无 Grid 和复杂定位。

## 完成标准

`inline-visuals.json` 是通过校验的计划或明确降级后的空计划；文章原文完整保留；最终 `article.html` 严格校验为零错误、零警告。记录 `module_count`、`kinds` 和 `degraded`。计划或插入失败只降级一次，不阻塞草稿流程。
