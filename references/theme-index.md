> **本文件仅供人阅读选主题。**主题的**单一真相源**是
> `.agents/skills/wechat-content-pipeline/scripts/render_article.py` 的 `THEMES` 字典
> ——色值、布局和全部组件 HTML 都在那里。脚本和本表冲突时**以脚本为准**。
>
> 别再解析这个文件来发现主题。要主题清单就问脚本：`render_article.py --help`
> 里 `--theme` 的 choices 就是全集。

# 主题索引

## 已注册主题

### 卡片密集型（信息密度高，视觉热闹）

| 标识（`--theme` 取值） | 中文名 | 主色 | 适用场景 |
|---|---|---|---|
| `moyu-green` | 摸鱼绿 | `#059669` emerald | 教程、测评、清单、工具盘点、知识整理（卡片丰富、信息密度高）。**默认推荐** |
| `red-white` | 红白色系 | `#DC2626` 正红 | 深度分析、观点、力量感话题（经典编辑风，编号章节 + 引言卡，红色克制点睛） |
| `moyu-ticket` | 摸鱼票据 | `#059669` emerald | 工具对比、创意评测（票据/门票视觉隐喻，星级 + 编号 + 硬阴影卡片） |
| `olive-journal` | 橄榄手记 | `#ED7B2F` 橙（配墨黑 `#23251D`） | 内刊手记、深度评测、案例复盘、系统性说明文（编辑部内刊质感） |

### 低噪音 / 强母题（装饰只在 hero、章节标题和目录，正文区极干净）

| 标识（`--theme` 取值） | 中文名 | 主色 | 适用场景 |
|---|---|---|---|
| `plain-white` | 素白 | `#8C8378` 暖灰 | 长文、随笔、需要读者沉进去的题材。全篇唯一的「大」元素是章节号的浅灰大数字，视觉噪音最低 |
| `ink-rule` | 墨线 | `#111111` 纯黑 | 严肃议题、书评、历史复盘。**衬线正文** + 黑线分节，像纸质书内页 |
| `deep-pool` | 深潭 | `#2E7D8C` 青 | 深度调查、行业观察。深色 hero 起手有重量，正文回白底，整篇不压 |
| `color-block` | 色块 | `#1B5E8C` 靛蓝 | 观点文、判断明确的分析。章节标题通栏反白压在主色上，是全部主题里冲击力最强的一套 |

## 怎么选

- 用户指定了 → 直接用。
- 题材明显契合上表某行 → 用那套，交付时一句话说明理由。
- 没有明显倾向 → 用 `moyu-green`。
- 流水线调用 → 用 `pipeline_job.py choose-theme` 已固定的那套，**不要重新选、不要询问**。它按 `run_id` 派生：跨文章会轮换，同一个 run 重跑必然选到同一套（恢复时不会换皮）。
- 一篇文章只用一套，不混搭。

## 加新主题

在 `render_article.py` 的 `THEMES` 里加一项，按需在 `render_hero` / `render_heading` / `render_toc` / `render_follow_cta` 加 `layout` 分支，再到上表登记一行。

**八个 `layout` 已实现**：`magazine`（摸鱼绿）、`editorial`（红白，同时是未知 layout 的兜底）、`ticket`（票据）、`journal`（橄榄）、`plain`（素白）、`serif-rule`（墨线）、`darkhero`（深潭）、`colorblock`（色块）。**复用现有 layout 只改色值最省事**——加一个 `THEMES` 条目即可，一行渲染代码都不用写。

### 必需键

`layout` / `name` / `paper` / `ink` / `body` / `muted` / `accent` / `soft` / `line` / `underline` / `radius` / `shadow`。
缺键会在渲染时才炸，`test_required_theme_keys_present` 会提前拦住。

可选键：`font`（默认无衬线，墨线用 `SERIF_FONT`）、`num`（plain 的大数字色）、`rule`（serif-rule 的黑线色）、`dark`/`darkink`/`darkbody`/`ondark`（darkhero）、`block`/`blockink`（colorblock）。

### 对比度是硬门禁

`ThemeContrastTests` 用 WCAG 相对亮度卡死：正文级色（`body`/`muted`/`darkbody`）**≥ 4.5:1**，大字号色 ≥ 3.0:1，深色底的组合一并检查。

**别为了「淡」而淡**——这是加主题最容易犯的错。实测踩过三次：素白的 `muted` 一度是 `#9A9A9A`（2.81:1），而它正是 plain 布局里 hero 引言的正文色；深潭的 `accent` 压在 `dark` 上只有 3.47:1，10px 的 kicker 看不清，只好另备 `ondark`；色块的 CTA 如果沿用 `accent` 做强调色，等于深蓝压深蓝，直接隐形。

### 改完必须验证

```bash
python3 -m unittest tests.test_article_renderer          # 含对比度与必需键回归
for t in $(python3 -c "import sys;sys.path.insert(0,'<PIPELINE>/scripts');from render_article import THEMES;print(' '.join(THEMES))"); do
  python3 <PIPELINE>/scripts/render_article.py --article 样例.md --theme $t --output /tmp/$t.html
  python3 scripts/validate_gzh_html.py /tmp/$t.html      # 必须 0 ERROR 0 WARN
done
```

样例文章要覆盖代码块、表格、列表、引用、子标题，否则漏测的块类型会在真文章里才暴露。

> **归档说明**：v1/v2 的 Markdown 组件库在 `archive/themes-v2/`，含 `theme-generator.md`（自定义主题生成流程）与 `common-components.md`（通用增量库）。它们只是**历史设计参考**，不再是排版依据——代码块、图片/GIF、小标签标题等通用组件已全部实现在 `render_article.py` 里。
