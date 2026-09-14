> **本文件仅供人阅读选主题。**主题的**单一真相源**是
> `.agents/skills/wechat-content-pipeline/scripts/render_article.py` 的 `THEMES` 字典
> ——色值、布局和全部组件 HTML 都在那里。脚本和本表冲突时**以脚本为准**。
>
> 别再解析这个文件来发现主题。要主题清单就问脚本：`render_article.py --help`
> 里 `--theme` 的 choices 就是全集。

# 主题索引

## 已注册主题

> **全局规范（2026-09）**：全部主题正文区一律**稳重灰调**——要么黑白灰，
> 要么极淡的颜色点缀；主题色只以**深色调**出现在强调、编号与细节线上
> （accent 压纸面 ≥3.0:1，测试已卡）。「本文看点」类目录模块已全线移除，
> 文章从首屏 hero 直接进入第一节。

### 卡片密集型（信息密度高）

| 标识（`--theme` 取值） | 中文名 | 主色 | 适用场景 |
|---|---|---|---|
| `moyu-green` | 松烟 | `#31544A` 墨绿 | 教程、测评、清单、工具盘点、知识整理（卡片丰富、信息密度高）。**默认推荐** |
| `olive-journal` | 手泽 | `#6B573F` 深赭（配墨黑 `#1F201B`） | 内刊手记、深度评测、案例复盘、系统性说明文（编辑部内刊质感） |

### 低噪音 / 强母题（装饰只在 hero 和章节标题，正文区极干净）

| 标识（`--theme` 取值） | 中文名 | 主色 | 适用场景 |
|---|---|---|---|
| `plain-white` | 留白 | `#8C8378` 暖灰 | 长文、随笔、需要读者沉进去的题材。全篇唯一的「大」元素是章节号的浅灰大数字，视觉噪音最低 |
| `ink-rule` | 墨栏 | `#111111` 纯黑 | 严肃议题、书评、历史复盘。**衬线正文** + 黑线分节，像纸质书内页 |
| `deep-pool` | 静渊 | `#3E4C57` 石板灰 | 深度调查、行业观察。深色 hero 起手有重量，正文回白底，整篇不压 |
| `color-block` | 玄章 | `#1F1F1F` 玄黑 | 观点文、判断明确的分析。章节标题通栏反白压在玄黑色上，是全部主题里冲击力最强的一套 |

### 新闻 / 正式报道（低装饰、不使用营销式文末引导）

| 标识（`--theme` 取值） | 中文名 | 主色 | 适用场景 |
|---|---|---|---|
| `news-wire` | 专电 | `#273746` 深灰蓝 | 新闻解读、事件进展、事实核查。报纸栏线结构，突出“事实—进展—边界”，适合信息密集但不需要压抑气氛的报道 |
| `solemn-gray` | 素笺 | `#712F38` 暗酒红 | 伤亡事件、事故复盘、纪念与公共安全议题。暖灰纸面配宋体，降低装饰和情绪刺激，文末不催在看与转发 |
| `formal-brief` | 文告 | `#234E70` 海军蓝 | 政策说明、机构动态、专题报告、阶段总结。文档页眉、摘要框和 SECTION 层级明确，适合正式、可归档的内容 |

### 垂类氛围组（一套管一个内容垂类，深色/浓色只出现在 hero，正文回浅底）

| 标识（`--theme` 取值） | 中文名 | 主色 | 适用场景 |
|---|---|---|---|
| `aurora-violet` | 霓灰 | `#4A4458` 灰紫 | AIGC、前沿科技、产品发布、效率工具深度体验。深灰紫 hero 收在一条灰调渐变细线上，章节标题用竖向渐变短棒，克制里带一点科技感 |
| `peach-soft` | 陶然 | `#7A4A38` 深陶（配暖白纸面） | 生活分享、书影音推荐、探店食记、情感与成长随笔。全篇胶囊圆角母题（胶囊序号、圆角卡片），松弛有生活感 |
| `noir-gold` | 金石 | `#7A6A45` 灰金（配墨黑 `#141414`） | 商业观察、财经解读、公司研究、职场进阶。黑色刊头配灰金细节，灰金只做点缀、深底文字一律用提亮灰金，杂志刊头质感 |

## 怎么选

- 用户指定了 → 直接用。
- 流水线调用 → `prepare` 已按 `run_id` 哈希固定主题。编辑稿只在非通报主题里轮换；伤亡/案件才进 `solemn-gray` / `news-wire` / `formal-brief`。不要按文章风格改。
- 单独排版且用户没指定 → 用 `moyu-green`，或让用户从 gallery 挑。不要按题材自行匹配垂类主题。
- 有伤亡、灾难或未决调查 → `prepare` 会把池子收成 `solemn-gray` / `news-wire` / `formal-brief`（安全路由，不是风格匹配）；单独排版时也只用这三套，不要用营销卡片。
- 一篇文章只用一套，不混搭。

## 加新主题

在 `render_article.py` 的 `THEMES` 里加一项，按需在 `render_hero` / `render_heading` / `render_follow_cta` / `render_end` 加 `layout` 分支，再到上表登记一行。**目录模块已删除，不要新增任何「看点/目录」区块。**

**十二个 `layout` 已实现**：`magazine`（松烟）、`journal`（手泽）、`plain`（留白）、`serif-rule`（墨栏）、`darkhero`（静渊）、`colorblock`（玄章）、`newswire`（专电）、`solemn`（素笺）、`briefing`（文告）、`aurora`（霓灰）、`capsule`（陶然）、`noir`（金石）。另有 `editorial` 分支不注册主题，仅作未知 layout 的防御性兜底。**复用现有 layout 只改色值最省事**；只有信息层级、章节或文末语义确实不同，才新增 layout 分支。

新闻组三套有一条额外约束：文末使用编辑说明，不出现“在看 / 转发 / 星标”等营销式引导。伤亡与未决案件尤其不能用互动话术消费事件。

### 必需键

`layout` / `name` / `paper` / `ink` / `body` / `muted` / `accent` / `soft` / `line` / `underline` / `radius` / `shadow`。
缺键会在渲染时才炸，`test_required_theme_keys_present` 会提前拦住。

可选键：`font`（默认无衬线，墨栏用 `SERIF_FONT`）、`num`（plain 的大数字色）、`rule`（serif-rule 的黑线色）、`dark`/`darkink`/`darkbody`/`ondark`（darkhero，及同样带深色 hero 的 aurora、noir）、`block`/`blockink`（colorblock）。

### 对比度是硬门禁

`ThemeContrastTests` 用 WCAG 相对亮度卡死：正文级色（`body`/`muted`/`darkbody`）**≥ 4.5:1**，大字号色 ≥ 3.0:1，深色底的组合一并检查；另有 `test_accent_is_dark_enough_for_emphasis` 卡住 accent 的**亮度上限**（≥3.0:1 才算「深色重点」，亮彩色的 accent 过不了）。

**别为了「淡」而淡**——这是加主题最容易犯的错。实测踩过三次：留白的 `muted` 一度是 `#9A9A9A`（2.81:1），而它正是 plain 布局里 hero 引言的正文色；静渊的 `accent` 压在 `dark` 上只有 3.47:1，10px 的 kicker 看不清，只好另备 `ondark`；玄章的 CTA 如果沿用 `accent` 做强调色，等于深色压深色，直接隐形。

### 改完必须验证

```bash
python3 -m unittest tests.test_article_renderer          # 含对比度与必需键回归
for t in $(python3 -c "import sys;sys.path.insert(0,'<PIPELINE>/scripts');from render_article import THEMES;print(' '.join(THEMES))"); do
  python3 <PIPELINE>/scripts/render_article.py --article 样例.md --theme $t --output /tmp/$t.html
  python3 scripts/validate_gzh_html.py /tmp/$t.html      # 必须 0 ERROR 0 WARN
done
```

样例文章要覆盖代码块、表格、列表、引用、子标题，否则漏测的块类型会在真文章里才暴露。

> **历史说明**：v1/v2 的 Markdown 组件库已从活跃分支移除，需要考古时可从 Git 历史读取。它们不再是排版依据；代码块、图片/GIF、小标签标题等组件均以 `render_article.py` 为准。
