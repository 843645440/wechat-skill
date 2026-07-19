# 封面 JSON 规格

封面提供两套并列模板，不在 Skill 内绑定账号：

- `editorial-ledger`：折叠报刊式编辑设计，重点词使用橙色与深底反色。
- `kinetic-type`：动态字构海报，标题第二行使用通栏深底，右侧用主题强调色形成节奏。

```json
{
  "template": "editorial-ledger",
  "theme": "olive-journal",
  "eyebrow": "AI 与产业观察",
  "title": "模型变便宜之后，真正昂贵的是什么",
  "title_lines": ["模型变便宜之后，", "真正昂贵的是什么"],
  "highlights": ["变便宜", "真正昂贵"],
  "subtitle": "企业竞争正在从参数转向工作流程"
}
```

- `template`：两套注册模板之一；具体账号映射以后再配置。
- `theme`：当前文章已固定的六套主题标识之一，模板会使用该主题主色。
- `eyebrow`：栏目或文章类型，最多 18 字。
- `title`：最终文章标题，最多 32 字。
- `title_lines`：正好两行，拼接后必须与 `title` 完全一致；每行最多 18 字。
- `highlights`：0—2 个标题中的原文短语，每项最多 8 字。`editorial-ledger` 会把第一项设为主题强调色、第二项设为深底反色；`kinetic-type` 保留字段但以整行反色为主。
- `subtitle`：正文已有的一句有限判断，最多 40 字。

禁止加入日期、期号、模型版本、随机字母、伪代码和正文不存在的数据。标题分行只改变视觉结构，不得改变文字。
