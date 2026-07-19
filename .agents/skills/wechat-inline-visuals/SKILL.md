---
name: wechat-inline-visuals
description: 从已完成写作和去 AI 味的微信公众号文章中提取观点、对比、流程或已核实数据，生成与当前排版主题一致的公众号原生 HTML 信息模块并插入现有 article.html。用于文章排版已选定主题后，需要增强手机端扫读体验但不生成正文图片、不上传正文素材、不调用图片模型的场景。
---

# 微信公众号原生信息模块

在基础排版完成后，从 `article.md` 提取 0—3 个语义模块，复用当前主题组件写入 `article.html`。最终模块是公众号正文 HTML，不是 PNG。

## 输入

必须同时取得：

- 最终 `article.md` 和内部 `sources.md`。
- 已完成基础排版的 `article.html`。
- 本轮已固定的主题标识及对应 `references/theme-*.md`。

先读 [references/plan-schema.md](references/plan-schema.md) 和 [references/theme-component-map.md](references/theme-component-map.md)。

## 工作流

1. 从文章已有内容识别最值得扫读的结构。优先顺序为：核心影响对象、清晰二元对比、真实流程、已核实数据。
2. 只在内容自然成立时选 1—3 个模块；没有合适内容时输出空 `modules`，不得为凑数量制造结构。
3. 写入 `inline-visuals.json`，每个模块记录原文锚点和原文证据。运行：

```bash
python3 <SKILL_ROOT>/scripts/validate_plan.py \
  --plan <WORK_DIR>/inline-visuals.json \
  --article <WORK_DIR>/article.md \
  --theme-index <PROJECT_ROOT>/references/theme-index.md
```

4. 读取当前主题完整组件库，按组件映射选择该主题自己的观点、列表、对比、流程或数据组件。复制组件 HTML 后替换字段；不要跨主题借组件，也不要现场设计新风格。
5. 按 `placement.after_heading` 和 `placement.after_text` 把模块插入相关正文之后。不得删除、改写或移动原段落；模块是额外的扫读层。
6. 更新原 `article.html`，再运行根目录的 `validate_gzh_html.py`。ERROR、WARNING、占位符必须全部清零。

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

`inline-visuals.json` 校验通过；所有模块使用当前主题组件；文章原文完整保留；最终 `article.html` 严格校验为零错误、零警告。记录 `module_count` 和使用的 `kinds`，不要展示内部证据清单给公众号读者。
