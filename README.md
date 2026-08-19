<div align="center">

# wechat-skill · 微信公众号内容 Skill 工具包

**把成稿排版，或按主题写作，再配封面、写入多账号草稿箱**

11 套精选主题 + 主题生成器 · 代码块/图片/GIF · 自动章节编号与关键词标记 · 双关卡质量校验

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blue.svg)](https://claude.ai/code)
[![Themes](https://img.shields.io/badge/themes-11%20+%20generator-059669)](references/theme-index.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Agents](https://img.shields.io/badge/Claude%20Code%20·%20Codex%20·%20Cursor-supported-8b5cf6.svg)](#-快速开始)

[English](README.en.md) ｜ 中文

</div>

---

给 AI Agent（Claude Code / Codex / Cursor 等）用的公众号内容工具包。它可以：

- 把已有 Markdown / Word / PDF / 纯文本排成**样式全内联、粘贴到公众号编辑器不掉格式**的 HTML
- 按你给的主题和思路写成文章，去 AI 味、配封面，写入指定账号**草稿箱**
- 用 11 套主题排版，或按一句话 / 一张参考图生成新主题
- 多账号草稿；定时任务由你的 Agent 触发（仓库里不内置 cron）

流水线**只创建草稿，不公开发布**，也不等于向粉丝群发。人工审核发生在微信公众号草稿箱。默认不自动扫热点选题。

## ✨ 这个 Skill 能做什么

- **11 套精选主题**：覆盖卡片型、低噪音长文、新闻报道和正式简报；其中新闻线、沉静灰、正式简报专门处理事实进展、伤亡事件与机构报告。
- **主题生成器**：不满足现成主题？用一句话描述或一张参考图，生成一套全新组件库并保存本地复用（见 `references/theme-generator.md`）。
- **内容全兼容**：代码块（深/浅色，等宽不折行）、图片、GIF（带动图角标）、行内代码、引用、列表、产品徽章。
- **智能排版**：章节自动编号（末章 ∞ / ///）、每段主动标 1–3 个关键词下划线、从正文提炼引言卡与目录、作者签名去重合并。
- **两种内容入口**：已有成稿只排版推草稿；或给主题让 AI 写完再排。后半段同一条工作流。
- **可选视觉**：正文配图可关；封面走用户图 → 正式标题 HTML → 可选生图 → 离线兜底。原生 HTML 信息模块按题材自动。
- **中文全角标点**：正文自动规范全角，代码块内原样保留。
- **不掉格式**：所有样式内联、文字 `<span leaf="">` 包裹，规避 `<style>/<div>/class/grid/position` 等公众号会过滤的写法。
- **双关卡质量校验**：`component_lint.py`（组件库源头）+ `validate_gzh_html.py`（最终产物），构成可复现的「改→验→修」闭环。
- **一键复制**：生成带「复制」按钮的预览页，点一下把富文本复制到剪贴板，直接粘进公众号，免手动全选。
- **多账号草稿**：每个公众号使用独立环境变量和素材空间，外部 Agent 定时任务只需传入账号别名。

## 👀 效果预览

以下为经典主题长图；全部主题可在本地 gallery 中交互预览：

<table>
<tr>
<td colspan="3" align="center"><img src="https://origin.picgo.net/2026/07/07/-40619312d679bc34.jpg" width="100%"><br><sub><b>摸鱼绿（默认）</b></sub></td>
</tr>
<tr>
<td colspan="3" align="center"><img src="https://origin.picgo.net/2026/07/07/-084eb2b9d6f8d5e2.jpg" width="100%"><br><sub><b>红白色系</b></sub></td>
</tr>
<tr>
<td colspan="3" align="center"><img src="https://origin.picgo.net/2026/07/07/-747b33f502544254.jpg" width="100%"><br><sub><b>橄榄手记</b></sub></td>
</tr>
<tr>
<td width="33%" align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-moyu-ticket.png?v=1" width="250"><br><sub><b>摸鱼票据风</b></sub></td>
</tr>
</table>

> 📚 **主题说明 → [docs/all-themes.md](docs/all-themes.md)**　｜　克隆后浏览器打开 `docs/gallery/index.html` 可看可交互的完整 HTML。

## ✅ 适合 / ❌ 不适合

**✅ 适合**：观点/深度分析 · 教程/操作指南 · 测评/工具盘点 · 知识整理/方法论 · 访谈/人物特稿 · 数据复盘/报告 · 生活/情感随笔 · 案例实战 —— 把 Markdown / Word / PDF / 纯文本长文，一键排成可直接粘进公众号编辑器的 HTML；也能按描述或参考图生成自定义主题；也可以给主题让 AI 写成草稿。

**❌ 不适合**：普通网页/落地页（用前端 Skill）· PPT（用 PPT Skill）· 非公众号平台的排版 · 自动公开发布。仅调用根 `wechat-skill` 时不会代写；科技、AI、产业和民生文章使用 `wechat-tech-insight-writer`；从成稿或主题一路到草稿箱使用 `wechat-content-pipeline`；**想让文章有人读完**（标题钩子、信息密度、利他落点、竖屏节奏，附可量化体检脚本）使用 `wechat-viral-writer`。

## 🗂 常见排版场景

| 你的内容 | 推荐怎么排 |
|---|---|
| 观点 / 深度长文 | 红白 或 橄榄手记；关键词下划线 + 金句引用 + 居中金句 |
| 产品测评 / 工具盘点 | 摸鱼绿 或 摸鱼票据；step/tool-label + 卡片，按配方表走 |
| 教程 / 操作指南 | 摸鱼绿；step-label + 代码块 + 编号列表 |
| 数据复盘 / 年度报告 | 摸鱼绿 或 橄榄手记；数据卡 + 表格 |
| 内刊 / 深度评测 / 案例复盘 | 橄榄手记；编者按 + 分节 + 暗色摘要框 |
| 新闻进展 / 事实核查 | 新闻线；报道提要 + REPORT 分节 + 信息说明 |
| 伤亡事件 / 事故复盘 | 沉静灰；宋体长读 + 事件脉络 + 克制编辑尾注 |
| 政策 / 机构 / 专题报告 | 正式简报；文档页眉 + 摘要框 + SECTION 分节 |
| Word / PDF 稿转公众号 | 先自动格式归一化 → 再按题材选主题 |
| 想要现成之外的风格 | 主题生成器：一句话或参考图现造一套 |

## 🎨 11 套精选主题

覆盖绝大多数公众号题材，每套都打磨到「拿来即用」：

| 主题 | 适合 |
|---|---|
| **摸鱼绿**（默认） | 教程、测评、清单、工具盘点（卡片丰富、信息密度高） |
| **红白色系** | 深度分析、观点、力量感话题（经典编辑风） |
| **摸鱼票据风** | 工具对比、创意评测（票据视觉隐喻） |
| **橄榄手记** | 内刊手记、深度评测、案例复盘（编辑部内刊质感） |
| **素白** | 随笔、长文与低视觉噪音阅读 |
| **墨线** | 严肃议题、书评、历史复盘 |
| **深潭** | 深度调查、行业观察 |
| **色块** | 观点明确、需要强章节识别的分析 |
| **新闻线** | 新闻解读、事件进展、事实核查 |
| **沉静灰** | 伤亡事件、事故复盘、纪念与公共安全议题 |
| **正式简报** | 政策说明、机构动态、专题报告、阶段总结 |

> 主色、下划线色值等**完整速查表见文末 [附录](#-完整主题速查表)**；不够用就让 AI [生成新主题](#-faq)。

## 🚀 快速开始

### 安装方式一：完整内容工具包（推荐）

```bash
git clone https://github.com/843645440/wechat-skill.git
cd wechat-skill
```

把该仓库作为 Agent 的工作区运行。这样根排版 Skill、`.agents/skills/` 下的写作、系列选题、去 AI 味、图片后端与编排 Skill、项目配置和脚本会一起可用。`optional-skills/` 不自动加载。

装好后对 Agent 说：

> 帮我配置公众号技能

它会跑 `python3 scripts/setup_status.py`，只问还没配的项：账号、常用方式、去 AI 味、正文配图、要不要开系列选题。凭证只进环境变量，不要写进 Git。说明见 [docs/setup.md](docs/setup.md)。

### 安装方式二：让 AI 加载完整仓库

对**任意 Agent**（Claude Code / Codex / Cursor 等）说一句：

> 请克隆并以工作区方式加载 https://github.com/843645440/wechat-skill，使用其中的项目级 Skills。

不要只复制根 `SKILL.md`，否则写作、图片后端和完整流水线不会随包加载。

### 安装方式三：只安装排版能力

```bash
npx skills add https://github.com/843645440/wechat-skill
```

这种方式用于只需要根排版 Skill 的运行环境。装好后对 Agent 说：

> 用摸鱼绿把这篇文章排成公众号 HTML：`article.md`

## 📖 两种内容用法

后半段都是同一条工作流（排版 → 封面 → 草稿）。差别只在谁出稿、拦什么。完整命令见 [docs/usage.md](docs/usage.md)。

| | 用法 1：我已有稿 | 用法 2：我给主题，AI 写 |
|---|---|---|
| 你提供 | 文章（Markdown / Word / PDF / 正文） | 主题 + 思路，或打开一个系列选题 |
| Skill 做什么 | 归一化、可选去 AI 味、选主题排版、封面、草稿 | 写作、强制去 AI 味、体检、排版、封面、草稿 |
| 去 AI 味 | 可关，默认关 | 强制开 |
| 字数 / 写作分 | 不拦 | 拦（1500–4000 字，score ≥75） |
| 定时任务 | 不适合 | 可以，用你自己 Agent 的定时器 |

只丢了一个标题、没有成稿，不要走用法 1。

**用法 1 示例**（已有文章，只要排版）

> 用 `$wechat-content-pipeline`，把这篇稿排版后写入 A 账号草稿箱。去 AI 味关掉。
>
> 或只排版、不进草稿箱：用摸鱼绿把 `article.md` 排成公众号 HTML。

**用法 2 示例**（给主题，AI 写到草稿箱）

> 使用 `$wechat-content-pipeline` 为 A 账号写到草稿箱。  
> 主题：……  
> 思路：……（时间线 / 论点 / 必须写到 / 不要写）

系列选题（涉黑涉恶、贪腐、重大诈骗等）是用法 2 的一个预设，不是热搜。开关在 [`config/public-event-archive.json`](config/public-event-archive.json)。必须已有生效裁判或稳定官方结论，并且同时有机关材料和中国官方媒体报道；没有合格题就跳过当天。由你的 Agent 定时任务触发，仓库里不内置 cron。

每个账号只复用一个内部交接区 `work/<account>/current/`，不是文章档案库；每次 `init` 生成新 `run_id`，同账号同日可产多篇。Agent 不应为单篇文章创建临时渲染器，**不做视觉审图**（草稿箱人工核对）。

### 用法 2 后半段在做什么

1. **接收 brief** — 主题 + 思路是硬门禁；读近 7 天历史做结构轮换（`shape`），防同质。
2. **写作** — `begin` 验证 brief 与结构后写 `article.md`。普通观点稿按账号声口；公共事件档案覆盖为克制正式。
3. **去 AI 味** — 强制一轮；公共事件用克制尺度。
4. **正文配图** — 已有图优先；Agent 可先用自带生图；否则仅在有 `AGNES_API_KEY` 时脚本生成。失败可不配图。公共事件禁用 AI 正文图。
5. **封面** — 用户图 → 正式报道准确标题 HTML → 可选生图 → HTML / Pillow → 账号默认素材。
6. **随机主题排版** — 固定一套主题，脚本一次生成正文 HTML。
7. **终检与草稿** — 用法 2 要求 score ≥75、blocking=0；用法 1 不卡字数和分数。写入草稿箱后结束，不公开发布。同一 `run_id` 成功后不重复发送。

## 🖼 配图开关

- **正文图**：默认关。用户带来的图优先，不覆盖。开了之后：先用 Agent 自带生图；没有则看 `AGNES_API_KEY`；都没有就不配图。
- **封面**：不能关成「没有封面」。微信草稿必须有封面。
- HTML 信息模块按题材自动，不算正文图。公共事件强制：无 AI 正文图，封面走准确标题。

提示词和设计说明里不要写供应商名。需要脚本生图时，免费 Key 在 <https://platform.agnes-ai.cn>，环境变量是 `AGNES_API_KEY`。

## 🧩 公众号平台限制（已内置兜底）

生成的 HTML 严格遵守：禁 `<style>/<script>/<div>`、`class/id`、`position:fixed/absolute/sticky`、`float`、`@media/@keyframes`、`display:grid`、CSS 变量、外部字体；样式全部内联；所有文字用 `<span leaf="">` 包裹。这些由校验脚本确定性检查，而非靠模型自觉。

## 🔁 可验证循环

改组件库或工作流后，用双关卡闭环防回归：

```bash
python3 scripts/component_lint.py .            # 源头关：扫组件库反模式
python3 scripts/validate_gzh_html.py out.html  # 产物关：扫最终 HTML 合规
```

- **源头关** 查 `white-space:pre`（大空白）、正文四周虚线框、平台禁用项 —— 须 0 ERROR。
- **产物关** 查禁用标签、`<span leaf>` 包裹、半角标点 —— 须 0 ERROR / 半角 0 WARN。
- 逻辑：源头干净 → 产物必然干净。详见 `references/eval-cases.md`。

## ⏰ 多账号与草稿配置

发布层支持任意数量公众号；配置文件只记录账号别名和环境变量名，不保存 AppSecret。

### 【必须】账号运行配置

```bash
cp assets/wechat-accounts.example.json wechat-accounts.json
```

打开 `wechat-accounts.json`，将 `default_author` 中的“作者名 A / 作者名 B”替换为真实作者名；不显示作者时改为空字符串。账号别名 `a`、`b` 必须同时存在于该文件和 `config/wechat-content-profiles.json`。不要把 AppSecret、access token 或其他真实密钥写入其中（该文件已被 `.gitignore` 排除）。

### 【必须】公众号凭证

在 Agent 的密钥管理中设置，不要写进定时任务提示词：

```text
WECHAT_A_APP_ID
WECHAT_A_APP_SECRET
WECHAT_B_APP_ID
WECHAT_B_APP_SECRET
```

脚本会自动获取并缓存 `access_token`。每个账号使用各自后台的 AppID / AppSecret。

### 【必须】公众号后台与运行环境

- 对应公众号已启用开发接口，并具有素材上传和草稿箱相关接口权限。
- 运行环境的公网出口 IP 已加入该公众号接口 IP 白名单；动态出口应配置固定 NAT 或代理。
- 能通过 HTTPS 访问 `api.weixin.qq.com`。
- 已安装 Python 3，Agent 能读取根 `SKILL.md` 和 `.agents/skills/`，并能写入 `work/<account>/current/`。
- 正式报道封面会优先使用 Chrome/Chromium 生成准确标题；没有浏览器会自动降级到 Pillow。自定义路径时设置 `WECHAT_COVER_BROWSER`。
- 本仓库不读取通用 LLM API Key；模型能力由 Agent 平台提供。

公众号类型和认证状态可能影响可用接口。首次部署时应在每个公众号后台分别确认，不能只验证其中一个账号。

### 【二选一必备】公众号封面

微信草稿必须有封面，每个账号至少满足一种：

1. **流水线封面脚本（默认）**：`gen_cover_image.py` 自动走用户图 → 正式报道 HTML 标题 → 可选生图 → HTML / Pillow。
2. **固定封面素材**：为账号配置已有的永久封面素材 ID：

```text
WECHAT_A_THUMB_MEDIA_ID
WECHAT_B_THUMB_MEDIA_ID
```

永久素材 ID 属于具体公众号，不能混用。封面与离线兜底都失败且没有默认素材时，草稿门禁会停止上传。

### 【按场景】

- **可选脚本生图**：设置 `AGNES_API_KEY`（<https://platform.agnes-ai.cn>）。没有 Key 时正文无图继续，封面自动离线兜底。
- **Token 缓存**：默认写入 `~/.cache/wechat-skill`。无持久磁盘时可用 `--no-token-cache`。
- **内容档案**：可在 `config/wechat-content-profiles.json` 调整受众和声口，但必须保留随机主题和草稿箱终点。
- **定时任务**：时间、时区和账号别名配置在 Agent 平台，不写进 Skill。建议 `Asia/Shanghai`。
- **实时事实**：涉及正在发生的事件、数据或企业公告时需要联网。

### 【无需配置】

- 不需要手动填微信 `access_token`，不需要 Cookie / 扫码登录 / 回调 URL / EncodingAESKey。
- 不需要小程序 AppID。
- 原生 HTML 正文、HTML 封面和 Pillow 兜底不需要图片 API Key。
- Skill 内不需要 cron。

### 上线前验收

```bash
python3 scripts/wechat_publish.py --config wechat-accounts.json accounts
python3 scripts/wechat_publish.py --config wechat-accounts.json send \
  --account a --html out.html --title '文章标题' --cover cover.jpg \
  --action draft --dry-run
```

`--dry-run` 只检查账号映射和 HTML，不能验证 AppSecret、IP 白名单、素材权限或草稿接口。正式启用前，必须为每个账号真实创建一次草稿并在后台核对。根目录的 `publish` 命令只供人工显式发布已审核草稿，自动流水线不会调用它。

完整凭证说明见 [`references/multi-account-publishing.md`](references/multi-account-publishing.md)。系列选题的 Hermes 部署见 [`hermes-deployment.md`](.agents/skills/wechat-public-event-archive/references/hermes-deployment.md)。

## 💡 为什么这么设计

- **约束优于自由** — 预设主题色板 + 固定组件先保住输出下限，不让模型每次现场发挥、风格飘忽。
- **样式粘贴不掉** — 全内联样式 + 每个文字节点 `<span leaf="">` 包裹，专门规避公众号会过滤的写法。
- **质量靠脚本不靠自觉** — 双关卡（源头 `component_lint` + 产物 `validate_gzh_html`）检查平台红线和标点。
- **正式内容不走想象图** — 公共事件用当前主题的原生 HTML，封面准确排最终标题。
- **换模型不走样** — 排版逻辑沉淀在组件库和脚本里，Claude / GPT / Gemini / 国产模型都能跑出一致效果。
- **Agent 友好** — 输入输出是 Markdown / HTML，Claude Code / Codex / Cursor 都能用。

## 📁 目录结构

```
wechat-skill/
├── .agents/skills/             # 默认发现：写作、系列选题、去 AI 味、图片后端与编排
├── optional-skills/            # 按需安装：独立封面与原生信息模块扩展
├── config/                     # A/B 账号的非敏感内容档案
├── SKILL.md                    # 排版工作流主文档（Agent 入口）
├── references/                 # 主题索引、生成器、多账号发布、评测用例
├── docs/usage.md               # 安装、配置与云端 Agent 使用指南
├── docs/setup.md               # 首次配置（给 Agent 带着问）
├── scripts/
│   ├── setup_status.py         # 首次配置检查
│   ├── validate_gzh_html.py    # 产物合规校验
│   ├── component_lint.py       # 组件库源头检查
│   └── wechat_publish.py       # 多账号草稿与发布 CLI
├── work/<account>/current/     # 账号级临时交接区（运行时生成，不提交）
├── assets/                     # 示例文章、账号模板、主题预览
└── docs/gallery/               # 主题浏览器预览
```

## 🧠 不止 11 套，自己造主题

内置主题不够用时，让 AI 现造一套。流程见 [`references/theme-generator.md`](references/theme-generator.md)：

> 按「黑白杂志、克莱因蓝点睛、衬线字体」的气质，给公众号排版生成一套新主题
>
> 按这张参考图（附图）做一套公众号排版组件库

仓库里 `assets/theme-previews/theme-mono-blue-editorial.html` 就是这样生成的「墨蓝刊读风」样例。

每套主题都建立在固定角色的色板上：主色只在锚点出现（全文 ≤5 处），大面积白底 + 灰阶，一段内高亮 ≤2 种。只给一个主色或一句气质，生成器会推导浅底、边框、高亮、灰阶和下划线色。

## ❓ FAQ

**Q：粘贴到公众号后样式会掉吗？**  
A：不会。所有样式内联、文字 `<span leaf="">` 包裹，这正是校验脚本强制的重点。

**Q：能自己加主题吗？**  
A：两种方式。① 让 AI 按风格或参考图生成；② 照 `CONTRIBUTING.md` 手写贡献并跑通校验。

**Q：只能在 Claude Code 用吗？**  
A：不限。任何能读取 Skill 目录的 Agent（Codex / Cursor 等）都能用。

**Q：对模型有要求吗？国产模型行不行？**  
A：不挑模型。排版逻辑在组件库和校验脚本里，Claude、GPT、Gemini，以及 DeepSeek、Kimi、通义千问、智谱 GLM 等都可以。硬约束由脚本兜底，换模型不会导致排版走样。

**Q：能一次出多套主题对比吗？**  
A：能。说「用这几套主题各排一遍这篇」即可。

**Q：怎么更新？**  
A：完整工具包在工作区执行 `git pull`；仅安装根排版 Skill 时重新运行 `npx skills add https://github.com/843645440/wechat-skill`。

**Q：Agent 写出来不合规怎么办？**  
A：跑 `scripts/validate_gzh_html.py`，报 ERROR 就回到装配步骤修；两关全绿才交付。

## 📋 完整主题速查表

| 主色 | 主题 | 适用 |
|---|---|---|
| ![](https://placehold.co/12/059669/059669.png) `#059669` | 摸鱼绿（默认） | 教程、测评、清单、工具盘点 |
| ![](https://placehold.co/12/DC2626/DC2626.png) `#DC2626` | 红白色系 | 深度分析、观点、力量感话题 |
| ![](https://placehold.co/12/059669/059669.png) `#059669` | 摸鱼票据风 | 工具对比、创意评测（票据视觉隐喻） |
| ![](https://placehold.co/12/1e1f23/1e1f23.png) `#1e1f23` | 橄榄手记 | 内刊手记、深度评测、案例复盘 |
| ![](https://placehold.co/12/8C8378/8C8378.png) `#8C8378` | 素白 | 长文、随笔、低噪音阅读 |
| ![](https://placehold.co/12/111111/111111.png) `#111111` | 墨线 | 严肃议题、书评、历史复盘 |
| ![](https://placehold.co/12/2E7D8C/2E7D8C.png) `#2E7D8C` | 深潭 | 深度调查、行业观察 |
| ![](https://placehold.co/12/1B5E8C/1B5E8C.png) `#1B5E8C` | 色块 | 观点明确的分析 |
| ![](https://placehold.co/12/273746/273746.png) `#273746` | 新闻线 | 新闻解读、事件进展、事实核查 |
| ![](https://placehold.co/12/712F38/712F38.png) `#712F38` | 沉静灰 | 伤亡事件、事故复盘、公共安全 |
| ![](https://placehold.co/12/234E70/234E70.png) `#234E70` | 正式简报 | 政策说明、机构动态、专题报告 |

> 每套主题的英文标识、组件库文件、下划线 CSS 见 [`references/theme-index.md`](references/theme-index.md)。需要别的风格？让 AI 用 [主题生成器](#-faq) 现生成一套。

## ⭐ Star

如果这个项目帮到了你，欢迎在 [GitHub](https://github.com/843645440/wechat-skill) 点个 Star。

## 🤝 贡献

欢迎新主题、修复与文档改进，请先读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 License

本项目采用 **GNU AGPL-3.0**。完整条款和原作者版权声明见 [LICENSE](LICENSE)。

要点：

1. **必须保留 LICENSE 中的版权声明**
2. **衍生品必须开源** — 任何修改版本、Fork、二次分发，必须以 AGPL-3.0（或兼容协议）公开发布，提供完整源代码
3. **网络服务也要开源** — 即使只是把修改版本部署成 SaaS / Web 服务给别人用而不分发代码，也要公开源代码（这是 AGPL 区别于 GPL 的核心）
4. **不允许闭源、专有化、仅付费分发**

本工具写入的是公众号**草稿**，不代替你对内容合法性、事实和审核负责。公共事件稿只复述已有官方结论，不处理未决传闻，不构成法律意见。
