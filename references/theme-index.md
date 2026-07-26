> **本文件仅供人阅读选主题。**主题的**单一真相源**是
> `.agents/skills/wechat-content-pipeline/scripts/render_article.py` 的 `THEMES` 字典
> ——色值、布局和全部组件 HTML 都在那里。脚本和本表冲突时**以脚本为准**。
>
> 别再解析这个文件来发现主题。要主题清单就问脚本：`render_article.py --help`
> 里 `--theme` 的 choices 就是全集。

# 主题索引

## 已注册主题

| 标识（`--theme` 取值） | 中文名 | 主色 | 适用场景 |
|---|---|---|---|
| `moyu-green` | 摸鱼绿 | `#059669` emerald | 教程、测评、清单、工具盘点、知识整理（卡片丰富、信息密度高）。**默认推荐** |
| `red-white` | 红白色系 | `#DC2626` 正红 | 深度分析、观点、力量感话题（经典编辑风，编号章节 + 引言卡，红色克制点睛） |
| `moyu-ticket` | 摸鱼票据 | `#059669` emerald | 工具对比、创意评测（票据/门票视觉隐喻，星级 + 编号 + 硬阴影卡片） |
| `olive-journal` | 橄榄手记 | `#ED7B2F` 橙（配墨黑 `#23251D`） | 内刊手记、深度评测、案例复盘、系统性说明文（编辑部内刊质感） |

## 怎么选

- 用户指定了 → 直接用。
- 题材明显契合上表某行 → 用那套，交付时一句话说明理由。
- 没有明显倾向 → 用 `moyu-green`。
- 流水线调用 → 用 `pipeline_job.py choose-theme` 已固定的那套，**不要重新选、不要询问**。它按 `run_id` 派生：跨文章会轮换，同一个 run 重跑必然选到同一套（恢复时不会换皮）。
- 一篇文章只用一套，不混搭。

## 加新主题

在 `render_article.py` 的 `THEMES` 里加一项，按需在 `render_hero` / `render_heading` / `render_toc` 等函数加 `layout` 分支，再到上表登记一行。

四个 `layout` 已实现：`magazine`（摸鱼绿）、`editorial`（红白，同时是未知 layout 的兜底）、`ticket`（票据）、`journal`（橄榄）。**复用现有 layout 只改色值最省事**——加一个 `THEMES` 条目即可，一行渲染代码都不用写。

改完必须验证：

```bash
for t in moyu-green red-white moyu-ticket olive-journal <新标识>; do
  python3 <PIPELINE>/scripts/render_article.py --article 样例.md --theme $t --output /tmp/$t.html
  python3 scripts/validate_gzh_html.py /tmp/$t.html   # 必须 0 ERROR
done
```

> **归档说明**：v1/v2 的 Markdown 组件库在 `archive/themes-v2/`，含 `theme-generator.md`（自定义主题生成流程）与 `common-components.md`（通用增量库）。它们只是**历史设计参考**，不再是排版依据——代码块、图片/GIF、小标签标题等通用组件已全部实现在 `render_article.py` 里。
