> 🤝 **本项目由 甲木 × [「摸鱼小李」](https://mp.weixin.qq.com/s/EMahAzgfAbRQrYukWE7_IQ) 联名共建** —— 排版组件、主题设计与质量标准凝聚了两人的公众号实践与共同打磨，特别感谢小李。

<div align="center">

# wechat-skill · 微信公众号内容 Skill 工具包

**把热点发现、写作、去 AI 味、配图、排版和多账号草稿串成可复用工作流**

6 套精选主题 + 主题生成器 · 代码块/图片/GIF · 自动章节编号与关键词标记 · 双关卡质量校验

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blue)](https://claude.ai/code)
[![Themes](https://img.shields.io/badge/themes-6%20+%20generator-059669)](references/theme-index.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Agents](https://img.shields.io/badge/Claude%20Code%20·%20Codex%20·%20Cursor-supported-8b5cf6.svg)](#-快速开始)

[English](README.en.md) ｜ 中文

</div>

---

一个给 AI Agent（Claude Code / Codex / Cursor 等）用的公众号内容工具包。根 Skill 负责把已有 Markdown 排成**样式全内联、粘贴到公众号编辑器不掉格式**的 HTML；项目内还附带科技深度写作、封面、正文配图和统一流水线 Skill，可从选题一路生成到指定账号草稿箱。

## ✨ 核心特性

- **6 套精选主题**：摸鱼绿（默认）· 红白 · 石墨极简 · 留白禅意 · 摸鱼票据 · 橄榄手记 —— 每套都是自成体系的厚组件库（设计变量 + 数十个精细组件 + 视觉层级表 + 文章类型配方表）。
- **主题生成器**：不满足现成主题？用一句话描述或一张参考图，生成一套全新组件库并保存本地复用（见 `references/theme-generator.md`）。
- **内容全兼容**：代码块（深/浅色，等宽不折行）、图片、GIF（带动图角标）、行内代码、引用、列表、产品徽章。
- **智能排版**：章节自动编号（末章 ∞ / ///）、每段主动标 1–3 个关键词下划线、从正文提炼引言卡与目录、作者签名去重合并。
- **中文全角标点**：正文自动规范全角，代码块内原样保留。
- **不掉格式**：所有样式内联、文字 `<span leaf="">` 包裹，规避 `<style>/<div>/class/grid/position` 等公众号会过滤的写法。
- **双关卡质量校验**：`component_lint.py`（组件库源头）+ `validate_gzh_html.py`（最终产物），构成可复现的「改→验→修」闭环。
- **一键复制**：生成带「复制」按钮的预览页，点一下把富文本复制到剪贴板，直接粘进公众号，免手动全选。
- **多账号发布**：每个公众号使用独立环境变量和素材空间，外部 Agent 定时任务只需传入账号别名。
- **内容生产流水线**：`wechat-content-pipeline` 可联网发现热点，强制去 AI 味，生成正文和图片，随机选择已注册主题，校验后自动写入指定账号草稿箱。

## 👀 效果预览

6 套主题各排同一篇长文（真实长图，含配图、引言卡、编号章节、金句、名词旁注等完整组件）：

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
<td width="33%" align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-graphite-minimal.png?v=1" width="250"><br><sub><b>石墨极简风</b></sub></td>
<td width="33%" align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-zen-whitespace.png?v=1" width="250"><br><sub><b>留白禅意风</b></sub></td>
<td width="33%" align="center"><img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/lf-moyu-ticket.png?v=1" width="250"><br><sub><b>摸鱼票据风</b></sub></td>
</tr>
</table>

> 📚 **6 套完整长图 → [docs/all-themes.md](docs/all-themes.md)**　｜　克隆后浏览器打开 `docs/gallery/index.html` 可看可交互的完整 HTML。

## ✅ 适合 / ❌ 不适合

**✅ 适合**：观点/深度分析 · 教程/操作指南 · 测评/工具盘点 · 知识整理/方法论 · 访谈/人物特稿 · 数据复盘/报告 · 生活/情感随笔 · 案例实战 —— 把 Markdown / Word / PDF / 纯文本长文，一键排成可直接粘进公众号编辑器的 HTML；也能按描述或参考图生成自定义主题。

**❌ 不适合**：普通网页/落地页（用前端 Skill）· PPT（用 PPT Skill）· 非公众号平台的排版。仅调用根 `wechat-skill` 时不会代写；科技、AI、产业和民生文章使用 `wechat-tech-insight-writer`，从选题到草稿箱使用 `wechat-content-pipeline`。

## 🗂 常见使用场景

| 你的内容 | 推荐怎么排 |
|---|---|
| 观点 / 深度长文 | 红白 或 石墨极简；关键词下划线 + 金句引用 + 居中金句 |
| 产品测评 / 工具盘点 | 摸鱼绿 或 摸鱼票据；step/tool-label + 卡片，按配方表走 |
| 教程 / 操作指南 | 摸鱼绿；step-label + 代码块 + 编号列表 |
| 数据复盘 / 年度报告 | 摸鱼绿 或 橄榄手记；数据卡 + 表格 |
| 禅意 / 极简随笔 | 留白禅意；大留白 + 居中衬线引用 |
| 内刊 / 深度评测 / 案例复盘 | 橄榄手记；编者按 + 分节 + 暗色摘要框 |
| Word / PDF 稿转公众号 | 先自动格式归一化 → 再按题材选主题 |
| 想要现成之外的风格 | 主题生成器：一句话或参考图现造一套 |

## 🎨 6 套精选主题

覆盖绝大多数公众号题材，每套都打磨到「拿来即用」：

| 主题 | 适合 |
|---|---|
| **摸鱼绿**（默认） | 教程、测评、清单、工具盘点（卡片丰富、信息密度高） |
| **红白色系** | 深度分析、观点、力量感话题（经典编辑风） |
| **石墨极简风** | 设计、科技评论、专业观点、高端品牌 |
| **留白禅意风** | 禅意、极简生活、深度随笔（呼吸感最强） |
| **摸鱼票据风** | 工具对比、创意评测（票据视觉隐喻） |
| **橄榄手记** | 内刊手记、深度评测、案例复盘（编辑部内刊质感） |

> 主色、下划线色值等**完整速查表见文末 [附录](#-完整主题速查表)**；不够用就让 AI [生成新主题](#-faq)。

## 🚀 快速开始

### 方式一：完整内容工具包（推荐）

```bash
git clone https://github.com/843645440/wechat-skill.git
cd wechat-skill
```

把该仓库作为云端 Agent 的工作区运行。这样根排版 Skill、`.agents/skills/` 下的写作/图片/编排 Skill、项目配置和脚本会一起可用。

### 方式二：让 AI 加载完整仓库

对**任意 Agent**（Claude Code / Codex / Cursor 等）说一句：

> 请克隆并以工作区方式加载 https://github.com/843645440/wechat-skill，使用其中的项目级 Skills。

不要只复制根 `SKILL.md`，否则写作、配图和完整流水线不会随包加载。

### 方式三：只安装排版能力

```bash
npx skills add https://github.com/843645440/wechat-skill
```

这种方式用于只需要根排版 Skill 的运行环境。装好后对 Agent 说：

> 用摸鱼绿把这篇文章排成公众号 HTML：`article.md`

## 💬 交流群

扫码加入**官方企业微信交流群**（活码自动邀请入群，一起交流公众号排版 & Agent Skills 玩法）：

<img src="https://github.com/isjiamu/gzh-design-skill/releases/download/assets-v1/group-qr.png" width="220" alt="企业微信交流群二维码">

> 扫码失效？加作者微信 **`zuiyn_soul`**（备注「gzh-design」）拉你进群。

## 📖 使用流程

完整安装、多账号凭证、云端 Agent 定时触发和常见命令见 **[使用指南](docs/usage.md)**。

完整内容生产可以直接调用：

> 使用 `$wechat-content-pipeline`，根据这个选题为 A 账号完成写作、配图、排版并写入草稿箱：……

没有给选题时，它会先联网筛选最新可靠热点；给了选题则直接使用。每个账号只复用一个内部交接区 `work/<account>/current/`，不是文章档案库，新任务会覆盖旧临时产物。

1. **确定选题** — 使用外部主题，或联网比较热点并选出一个可核验的角度。
2. **写作与核验** — 生成 `article.md`，将来源和日期内部记录到 `sources.md`。
3. **强制去 AI 味** — Humanizer 必须执行，随后复查事实，禁止新增经历、人物和数据。
4. **生成图片** — 用固定 HTML/CSS 模板生成正文视觉卡和封面，再由浏览器确定性截图；素材按账号分别上传。
5. **随机排版** — 从 `theme-index.md` 的已注册主题中随机选择一套，同一轮重试保持不变。
6. **严格校验** — 清除 HTML 错误、警告和占位符。
7. **自动建草稿** — 校验通过后立即写入指定账号草稿箱，到此结束；人工在草稿箱审核，流水线不公开发布。

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

## ⏰ 多账号与 Agent 定时触发

发布层支持任意数量公众号；配置文件只记录账号别名和环境变量名，不保存 AppSecret。下面的标记用于区分上线要求：

- **【必须】**：缺少时无法完成指定账号的真实草稿创建。
- **【二选一必备】**：两种方案至少启用一种。
- **【按场景】**：仅在使用对应功能时需要。
- **【无需配置】**：由脚本自动处理，或本流程不会使用。

### 【必须】账号运行配置

复制无密钥模板：

```bash
cp assets/wechat-accounts.example.json wechat-accounts.json
```

打开 `wechat-accounts.json`，将 `default_author` 中的“作者名 A / 作者名 B”替换为真实作者名；不显示作者时改为空字符串。不要原样保留占位文字。账号别名 `a`、`b` 必须同时存在于该文件和 `config/wechat-content-profiles.json`。

`wechat-accounts.json` 已被 `.gitignore` 排除，不要把 AppSecret、access token 或其他真实密钥写入其中。

### 【必须】A/B 公众号凭证

在云端 Agent 的密钥管理中设置以下环境变量，不要写进定时任务提示词：

```text
WECHAT_A_APP_ID
WECHAT_A_APP_SECRET
WECHAT_B_APP_ID
WECHAT_B_APP_SECRET
```

每个账号使用各自公众号后台的 AppID 和 AppSecret。脚本会自动获取并缓存 `access_token`，无需手动生成或定期填写。

### 【必须】公众号后台与运行环境

- 两个公众号都已启用开发接口，并具有素材上传和草稿箱相关接口权限。
- 云端执行器的公网出口 IP 已分别加入两个公众号的接口 IP 白名单；动态出口环境应配置固定 NAT、固定代理或中转服务。
- 运行环境能够通过 HTTPS 访问 `api.weixin.qq.com`。
- 已安装 Python 3，Agent 能读取根 `SKILL.md` 和 `.agents/skills/`，并能写入 `work/<account>/current/`。
- 已安装 Chrome 或 Chromium，用于把内部 HTML 视觉模板截图成 PNG；自定义路径时设置 `HTML_VISUAL_BROWSER`。
- 云端 Agent 本身具有可用的大模型能力；模型授权由 Agent 平台提供，本仓库不读取通用 LLM API Key。

公众号类型和认证状态可能影响可用接口。首次部署时应在两个公众号后台分别确认接口权限，不能只验证其中一个账号。

### 【二选一必备】公众号封面

微信草稿必须有封面，每个账号至少满足以下一种方案：

1. **HTML 确定性视觉图（默认）**：项目使用 `wechat-html-visuals`，将受约束 JSON 渲染为固定 HTML/CSS，再通过 Chrome/Chromium 生成 PNG。它不调用图片模型，不需要图片 API Key，也不进行 AI 视觉检测。默认输出为：

   ```text
   封面：1410 × 600
   正文视觉图：1200 × 800
   ```

   模板支持封面、观点卡、对比图、流程图和数据卡。文字、编号和布局由浏览器排版，PNG 只检查签名和精确尺寸；每张图只渲染一次，浏览器技术故障最多重试一次。

2. **固定封面降级方案**：不启用自动生图时，为账号配置已有的永久封面素材 ID：

```text
WECHAT_A_THUMB_MEDIA_ID
WECHAT_B_THUMB_MEDIA_ID
```

永久素材 ID 属于具体公众号，A/B 不能混用。正文视觉图渲染失败时流水线可以降级继续；没有 HTML 封面且没有对应默认素材 ID 时，草稿门禁会停止上传。Agnes 和 Baoyu 图片 Skill 仍保留供独立、明确调用，但完整定时流水线不会使用，也不会自动回退到 AI 生图。

### 【按场景】其他能力

- **自动抓取热点**：定时任务不提供主题时，Agent 必须具有联网搜索能力。平台原生搜索不需要在本仓库配置 Key；自行接入第三方搜索时使用其凭证。
- **最新事实核验**：涉及实时事件、数据或企业公告时需要联网，即使任务已经提供主题。
- **浏览器路径**：渲染器会自动查找 Chrome、Chromium 和 Playwright Chromium；找不到时通过 `HTML_VISUAL_BROWSER` 指定可执行文件。
- **可选 AI 生图**：只有单独调用 `agnes-image-gen`、`baoyu-cover-image` 或 `baoyu-article-illustrator` 时才需要相应后端及凭证；默认流水线不使用。
- **Token 缓存**：默认写入 `~/.cache/wechat-skill`；目录需可写。无持久磁盘时可使用发布命令的 `--no-token-cache`。
- **内容档案**：可在 `config/wechat-content-profiles.json` 调整 A/B 的受众和热点类别，但必须保留随机主题、强制 Humanizer 和草稿箱终点。
- **定时任务**：时间、时区和账号别名配置在 Agent 平台，不写进 Skill。建议明确使用 `Asia/Shanghai`，早间任务传 `a`，晚间任务传 `b`。

### 【无需配置】本流程不使用的凭证

- 不需要手动配置微信 `access_token`。
- 不需要微信公众号登录 Cookie、扫码登录、回调 URL、消息校验 Token 或 EncodingAESKey。
- 不需要小程序 AppID/AppSecret。
- `humanizer` 不需要独立 API Key。
- 默认 HTML 视觉图不需要 Agnes、OpenAI、Google 或其他图片 API Key。
- 公开仓库只读克隆不需要 GitHub Token；只有推送修改或仓库改为私有时才需要仓库凭证。
- Skill 内不需要 cron、早晚时间或轮询配置。

### 上线前验收

先列出账号并做离线检查：

```bash
python3 scripts/wechat_publish.py --config wechat-accounts.json accounts
python3 scripts/wechat_publish.py --config wechat-accounts.json send \
  --account a --html out.html --title '文章标题' --cover cover.jpg \
  --action draft --dry-run
```

使用默认永久封面时可省略 `--cover`。`--dry-run` 只检查账号映射和 HTML，不能验证 AppSecret、IP 白名单、素材权限或草稿接口。正式启用定时任务前，必须分别为 A、B 创建一次真实草稿并在各自草稿箱确认文章、作者、封面和正文图片。

`wechat-content-pipeline` 只创建草稿。定时时间配置在 Agent 自带的定时任务中，由它触发 Skill 并传入 `a`、`b` 等账号别名和可选主题；Skill 内没有 cron、早晚时间或轮询器。

完整凭证配置见 [`references/multi-account-publishing.md`](references/multi-account-publishing.md)。根发布工具仍保留显式 `publish` 命令供独立人工操作，但自动内容流水线不会调用它。

## 💡 为什么这么设计

- **约束优于自由** — 预设主题色板 + 固定组件先保住输出下限，不让模型每次现场发挥、风格飘忽。
- **样式粘贴不掉** — 全内联样式 + 每个文字节点 `<span leaf="">` 包裹，专门规避公众号会过滤的写法，粘进去不塌。
- **质量靠脚本不靠自觉** — 双关卡（源头 `component_lint` + 产物 `validate_gzh_html`）确定性检查平台红线和标点，不靠模型「记得住」。
- **配图不赌模型识字** — 结构化内容经过固定 HTML/CSS 模板和浏览器截图，中文、编号与布局可重复，不运行视觉模型修图循环。
- **换模型不走样** — 排版逻辑全沉淀在组件库和脚本里，不依赖某家模型，Claude / GPT / Gemini / 国产模型都能跑出一致效果。
- **Agent 友好** — 输入输出全是纯文本 Markdown / HTML，任何 Agent 都能读、写、改、验，天然适配 Claude Code / Codex / Cursor。

## 📁 目录结构

```
wechat-skill/
├── .agents/skills/             # 写作、封面、正文配图、Humanizer 与编排 Skill
├── .baoyu-skills/              # 图片 Skill 的项目级非交互偏好
├── config/                     # A/B 账号的非敏感内容档案
├── SKILL.md                    # 排版工作流主文档（Agent 入口）
├── references/
│   ├── theme-index.md          # 6 套主题索引（主色/适用/下划线，单一来源）
│   ├── theme-*.md              # 6 套主题组件库（theme-moyu-green.md 等）
│   ├── theme-generator.md      # 主题生成器（按描述/参考图生成新主题）
│   ├── common-components.md    # 跨主题通用增量组件（代码块/图片/小标签）
│   ├── format-normalize.md     # 格式归一化（docx/pdf/纯文本 → Markdown）
│   ├── multi-account-publishing.md # 多账号凭证、草稿与外部 Agent 触发
│   └── eval-cases.md           # 触发用例 + 可验证循环
├── docs/usage.md               # 完整安装、配置与云端 Agent 使用指南
├── scripts/
│   ├── validate_gzh_html.py    # 产物合规校验
│   ├── component_lint.py       # 组件库源头检查
│   └── wechat_publish.py       # 多账号草稿与发布 CLI
├── work/<account>/current/     # 账号级临时交接区（运行时生成，不提交）
├── assets/
│   ├── sample-article.md       # 演示输入
│   ├── wechat-accounts.example.json # 无密钥的账号配置模板
│   └── theme-previews/         # 主题生成器产出的区块库预览
└── docs/gallery/               # 主题浏览器预览
```

## 🎯 设计原则

- **约束而非自由** — 用预设主题色板和固定组件保证输出下限，不让模型现场发挥。
- **确定性下沉脚本** — 平台限制这类死规则交给校验脚本，模型只做内容判断。
- **小标签，不用虚线框** — 强调用左竖条/药丸标签，笨重的四周虚线框只留给「待补素材」居中占位。
- **每处经验都可复现** — 踩过的坑写进 gotchas 和校验脚本，用可验证循环防回归。
- **配方优于自由** — 先按文章类型查主题库的「配方表」定组件组合，再装配，同类文章排版气质稳定。
- **克制用色** — 主色只在锚点出现（全文 ≤5 处），大面积白底 + 灰阶，彩色只做点缀。
- **灰阶承重** — 约 90% 的文字交给一套中性灰阶，色彩不承担正文阅读，避免花哨。

## 🧠 方法论：不止 6 套，自己造主题

### 主题生成：一句话 / 一张参考图，现造一套新主题

内置 6 套不够用时不必等更新——让 AI 现造一套。背后是 [`references/theme-generator.md`](references/theme-generator.md) 定义的第二条工作流：

1. **收集偏好**（一次问全，不逐条追问）：主题描述必填（或给参考图），名称 / 主色 / 背景 / 正文色 / 强调色 / 装饰色 / 字体 / 圆角 / 阴影 / 适用场景可留空自动补全。
2. **生成区块库**：AI 产出 45~75 个区块的完整 HTML 组件库，存到 `assets/theme-previews/{id}.html`，浏览器整页一次浏览确认风格（不逐块问）。
3. **转标准主题库 + 登记**：确认后转成 `references/theme-{id}.md`（补 `<span leaf>`、补齐五章节：变量表 / 组件 / 骨架 / 配方表 / 映射表），登记进 theme-index，跑 `component_lint.py` 到 0 ERROR。
4. **即刻同权**：之后排版和内置主题完全一样，直接说「用 XX 主题排这篇」。

**怎么触发**：

> 按「黑白杂志、克莱因蓝点睛、衬线字体」的气质，给公众号排版生成一套新主题
>
> 按这张参考图（附图）做一套公众号排版组件库

仓库里 `assets/theme-previews/theme-mono-blue-editorial.html` 就是这样生成的一套「墨蓝刊读风」样例。

### 颜色搭配：一套可复制的配色结构，AI 自动生成协调色板

每套主题的视觉都建立在一张**设计变量色板**上——配色不是拍脑袋，而是固定的角色分工：

| 角色 | 作用 | 取色思路 |
|---|---|---|
| **主色** | 章节编号、锚点强调、封面点睛 | 一个有辨识度的品牌色（`#059669` emerald / `#DC2626` 正红 …）|
| **浅底 / 浅边框** | 卡片背景、引用块、标签底 | 主色同色系的极浅色（主色 + 大量白）|
| **点睛高亮色** | 每段 1~2 处黄底 / 渐变高亮 | 与主色冷暖对比的第二色（绿配黄）|
| **中性灰阶** | 正文 / 标题 / 辅助 / 分割线 | `#111827 → #9CA3AF` 一套灰阶，承担 90% 的文字 |
| **下划线标记色** | 正文关键词逐段标记 | 主色的浅色版（`#A7F3D0` / `#FECACA`），温和不抢戏 |

**克制三原则**：① 主色只在锚点出现（全文 ≤5 处）；② 大面积白底 + 灰阶，彩色只点缀；③ 一段内高亮 ≤2 种。

**让 AI 自动配**：只给一个主色或一句气质描述，主题生成器就据此推导整套协调色板——浅底、边框、高亮、灰阶、下划线色自动生成并保证可读对比度：

> 以 `#7C9EB2` 雾蓝为主色，生成一套清新旅行随笔风的公众号主题

## 🗺 Roadmap

- [x] 主题生成器：按描述/参考图生成自定义主题
- [ ] 更多精选内置主题（欢迎 [提建议](https://github.com/843645440/wechat-skill/issues/new?template=theme_request.md)）
- [ ] 主题静态截图预览（docs/screenshots/）
- [ ] GitHub Pages 在线画廊
- [ ] 一键把整篇 Markdown + 配图打包导出

## ❓ FAQ

**Q：粘贴到公众号后样式会掉吗？**
A：不会。所有样式内联、文字 `<span leaf="">` 包裹，这正是校验脚本强制的重点。

**Q：能自己加主题吗？**
A：两种方式。① **让 AI 生成**：说「按这个风格 / 这张图生成一套公众号主题」，它会走 `references/theme-generator.md` 的流程生成组件库、登记并复用。② **手写贡献**：照 `CONTRIBUTING.md` 的「新增一套主题风格」，跑通可验证循环即可提 PR。

**Q：只能在 Claude Code 用吗？**
A：不限。任何能读取 Skill 目录的 Agent（Codex / Cursor 等）都能用，工作流在 `SKILL.md`。

**Q：对模型有要求吗？国产模型行不行？**
A：不挑模型，**国内外模型都能跑出一致效果**。排版逻辑全部沉淀在组件库和校验脚本里，不依赖某家模型的特殊能力——Claude、GPT、Gemini，以及 DeepSeek、Kimi、通义千问、智谱 GLM 等国产模型都可以。模型只负责按规则填充内容，硬约束由校验脚本确定性兜底，所以换模型不会导致排版走样。

**Q：能一次出多套主题对比吗？**
A：能。说「用这几套主题各排一遍这篇」即可批量生成多套供你挑。

**Q：怎么更新到最新版？**
A：完整工具包在工作区执行 `git pull`；仅安装根排版 Skill 时重新运行 `npx skills add https://github.com/843645440/wechat-skill`。

**Q：Agent 写出来不合规怎么办？**
A：跑 `scripts/validate_gzh_html.py`，报 ERROR 就回到装配步骤修；两关全绿才交付，仍有问题欢迎开 Issue。

## 📋 完整主题速查表

| 主色 | 主题 | 适用 |
|---|---|---|
| ![](https://placehold.co/12/059669/059669.png) `#059669` | 摸鱼绿（默认） | 教程、测评、清单、工具盘点 |
| ![](https://placehold.co/12/DC2626/DC2626.png) `#DC2626` | 红白色系 | 深度分析、观点、力量感话题 |
| ![](https://placehold.co/12/52525B/52525B.png) `#52525B` | 石墨极简风 | 设计、科技评论、专业观点、高端品牌 |
| ![](https://placehold.co/12/4A5D52/4A5D52.png) `#4A5D52` | 留白禅意风 | 禅意、极简生活、深度随笔 |
| ![](https://placehold.co/12/059669/059669.png) `#059669` | 摸鱼票据风 | 工具对比、创意评测（票据视觉隐喻） |
| ![](https://placehold.co/12/1e1f23/1e1f23.png) `#1e1f23` | 橄榄手记 | 内刊手记、深度评测、案例复盘 |

> 每套主题的英文标识、组件库文件、下划线 CSS 见 [`references/theme-index.md`](references/theme-index.md)。
> 需要别的风格？让 AI 用 [主题生成器](#-faq) 现生成一套。

## ⭐ Star

如果这个项目帮到了你，欢迎在 [GitHub](https://github.com/843645440/wechat-skill) 点个 Star。

## 🤝 贡献

欢迎新主题、修复与文档改进，请先读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 License

**AGPL-3.0 © 2026 甲木 × 摸鱼小李**

本项目采用 **GNU AGPL-3.0** 协议，要点：

1. **必须署名** — 保留版权与联名署名声明
2. **衍生品必须开源** — 任何修改版本、Fork、二次分发，必须以 AGPL-3.0（或兼容协议）公开发布，提供完整源代码
3. **网络服务也要开源** — 即使只是把修改版本部署成 SaaS / Web 服务给别人用而不分发代码，也要公开源代码（这是 AGPL 区别于 GPL 的核心）
4. **不允许闭源、专有化、仅付费分发**

完整条款见 [LICENSE](LICENSE)。

> 🤝 **欢迎 AI Agent 厂商、模型厂商共创**：想把 wechat-skill 集成进产品、或基于它做深度共建，我们很欢迎——共创协议请联系甲木。

## 🙏 致谢

- 本项目由 **甲木 × 摸鱼小李** 联名共建：核心组件库与主题设计标准凝聚了两人的公众号排版实践。
- 质量工程（可验证循环）由 skill-optimizer 审计驱动打磨。

---

<div align="center">

<img src="https://origin.picgo.net/2026/07/07/22e8d28de5f71eee085939b2f4c1f19548b19a67a79bdb68.png" width="600" alt="甲木 × 摸鱼小李 公众号名片">

<sub>关注我们的公众号，获取更多 AI 干货与排版实践 👆</sub>

</div>
