# 可选 Skill

这里保存不进入默认 Skill 索引的独立扩展。目录位于 `.agents/skills/` 之外，因此 Agent 默认只看到名称更少、职责更清楚的核心 Skill，也不会为这些扩展加载说明。

| Skill | 何时安装 |
|---|---|
| `wechat-inline-visuals` | 明确需要从成稿提取观点、流程或比较，生成公众号原生 HTML 信息模块 |
| `wechat-html-cover` | 明确需要 Chrome/Chromium 确定性生成 1410×600 中文封面 |
| `baoyu-cover-image` | 明确需要脱离主流水线单独创作 AI 文章封面 |

主流水线会直接调用 `wechat-inline-visuals` 的校验脚本和 `wechat-html-cover` 的确定性渲染脚本，并把 `baoyu-cover-image` 的设计维度固化在小型策略中；这只消耗脚本运行资源，不会把三份 `SKILL.md` 送进模型上下文。自动日更无需把任何目录复制回 `.agents/skills/`。

## 启用一个扩展

只把需要的一个目录复制到目标 Agent 的 Skill 搜索目录。以 Hermes 项目级安装 HTML 封面为例：

```bash
cp -R optional-skills/wechat-html-cover .agents/skills/
hermes skills trust "$PWD"
```

随后显式调用 `$wechat-html-cover`。不要把整个 `optional-skills/` 加入搜索路径，否则三项扩展会重新全部进入默认索引。仓库更新后如需同步已安装副本，重新复制所需目录或使用部署系统管理该副本。

仓库测试直接从 `optional-skills/` 运行，不要求先安装扩展。
