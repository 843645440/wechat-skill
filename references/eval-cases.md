# 触发与主题选择 · 回归用例

维护本 skill（改 description、加主题、调路由）后用这组用例核对，确保该触发时触发、不该触发时不触发、主题推荐合理。

## 正例（应触发 wechat-skill）

- "帮我把这篇 Markdown 做成公众号排版"
- "微信公众号文章排版"
- "gzh，这篇用 XX 主题"（XX 为 theme-index 中已注册主题）
- "把下面这篇文章转成能直接粘进公众号编辑器的 HTML"
- "这篇文章帮我排个版，发公众号用"
- "给公众号排版加一套新主题 / 自定义风格"（→ 在 `THEMES` 加一项并登记 theme-index）

## 反例（不应触发，应转其它能力）

- "帮我做一个网页落地页" → 前端/web skill
- "把内容做成 PPT" → PPT skill
- "帮我排版这个 Word 文档" → 排版对象不是公众号
- "写一篇公众号文章" → `wechat-tech-insight-writer`
- "从这个选题开始，写作、原生信息模块、排版后发到 A 账号草稿箱" → `wechat-content-pipeline`
- "每天复盘一件有官方结论的中国重大公共事件并放进 B 草稿箱" → 外部 Agent 定时触发 `wechat-public-event-archive`
- "为 B 账号自动找今天的科技热点并生成草稿" → 默认拒绝；通用热点开关关闭，需用户命题

## 完整流水线行为

- 普通流水线没有主题 → 停止追问，不自行联网找题
- 公共事件档案 → 仅在独立配置开关已启用时自动比较候选；没有生效裁判/官方结论与官方媒体双重佐证则跳过当天
- 已有主题 → 直接写作，不重复选题
- 写作 → 一次交付最终稿，只有事实、逻辑或合规硬伤才局部修正，不做第二次全文改写
- 排版主题 → 普通稿从已注册主题减去正式三套后按 `run_id` 哈希轮换；正式报道只在 `solemn-gray`、`news-wire`、`formal-brief` 中选择；同一轮失败重试沿用已选结果
- 工作区 → 只使用 `work/<account>/current/`，新任务覆盖旧临时产物，不创建每篇文章历史目录
- 发布目标 → 校验通过后自动创建草稿，不等待 AI 内审批，不调用公开发布接口
- 定时职责 → 由外部 Agent 的定时任务触发，Skill 内不保存时刻或 cron
- 标题 → 每次根据事件生成，不使用固定标题模板；必须保留具体对象和动作，再落到受影响人群或现实问题，且不超过 32 字
- 排版与信息模块 → 固定渲染器一次生成，不允许为单篇文章临时写转换脚本；正式报道最多自动加入一张“公开事实脉络”，锚点和证据必须来自最终正文；计划失败时只降级一次为空计划
- 流水线封面 → 用户图优先（`user_provided`）；正式报道使用准确标题 HTML，普通观点稿使用无文字、无 Logo 的 2.35:1 艺术指导主视觉；失败后自动降级到 HTML、Pillow、账号默认素材
- 独立 HTML 封面 → 三套模板按视觉宽度自动分成两行或三行并计算安全字号；浏览器硬超时；只做机械校验，不调用视觉模型
- 阶段时长 → 结束后检查 `started_at`、`completed_at`、`duration_ms`；`humanize` 允许 pending 直接 completed

## 五篇压力测试回归

- `英特尔把Gemini引入芯片研发，工程师先面对责任重分配`
- `NotebookLM更名，Google让研究工具直接运行代码`
- `Google给AI广告加制作标签，广告主的低成本创意开始留痕`
- `FREE Walk外骨骼进医院，治疗师从扶走转向调参`
- `Claude教师版免费开放，Anthropic把AI接进备课流程`
- `WAIC 2026发布300多款新品，职场人先面对任务重分配`

以上标题应全部通过 32 字限制和自动封面分行校验。用全部注册主题分别渲染 `insight`、`comparison`、`process`、`metrics`；所有组合必须通过 `validate_gzh_html.py`。把任一模块锚点改成不存在的文字后，预期行为是输出完整纯正文、计划变为空、`degraded=true`，不得生成第二份模块计划。

封面回归还需把 `OpenAI重算AI价值，复核人员成了隐藏成本` 和一个恰好 32 字的全中文标题分别用 `signal-editorial`、`night-signal`、`redaction-poster` 渲染。标题必须完整落在单一底色安全区内，不能跨背景、被装饰覆盖或从右侧裁切；长标题应自动转为三行。

## 主题选择行为

- 用户指定了已注册主题 → 直接用，不提问
- 流水线 → `prepare` 按 `run_id` 哈希固定主题；编辑稿候选不含 `solemn-gray` / `news-wire` / `formal-brief`，不按文章风格改
- 单独排版且用户没指定 → 用 `moyu-green`，或让用户从 gallery 挑；不要按题材自行匹配
- 用户明说「直接排/一键/不用问」→ 用 `moyu-green`（用户指定除外），不要推断风格
- 伤亡/未决调查等正式报道 → 池子限定 `solemn-gray` / `news-wire` / `formal-brief`（安全路由）
- theme-index 与 `THEMES` 冲突时以 `render_article.py` 为准

## 新闻 / 正式报道主题回归

- “把这篇校园枪击事件解读排得克制一点” → 推荐 `solemn-gray`；正文使用宋体与暖灰纸面，文末不得出现“在看、转发、星标”。
- “把这篇事件最新进展做成新闻稿样式” → 推荐 `news-wire`；首屏应出现 `NEWS DESK`，章节使用 `REPORT 01`。
- “把这份政策阶段总结排成文告” → 推荐 `formal-brief`；首屏应出现 `BRIEFING`，章节使用 `SECTION 01`。
- 三套主题都不得出现渐变背景和装饰性阴影；`insight`、`comparison`、`process`、`metrics`、表格、引用、列表和代码块必须继续通过公众号 HTML 校验。
- 严肃主题只允许“信息说明 / 阅读说明 / 报告说明”类编辑尾注；不得复用通用涨粉 CTA。

## 全局排版规范回归（2026-09 定稿）

- 全部主题不再输出「本文看点 / 报道提要 / 事件脉络 / 报告目录 / 本期看点」等目录模块；`render_article.py` 中不存在 `render_toc`，摘要后直接进入第一节。
- 全部主题正文区为稳重灰调：要么黑白灰，要么极淡颜色点缀；任何主题的 `accent` 压 `paper` 必须 ≥3.0:1（`test_accent_is_dark_enough_for_emphasis` 卡住），不得回退到饱和亮色。

## 垂类氛围主题回归

- “把这篇大模型发布会解读排得有科技感” → 推荐 `aurora-violet`；首屏应出现 `AURORA LAB`，深灰紫 hero 底部有一道灰调渐变细线，章节标题左侧为竖向渐变短棒。
- “把这篇探店笔记排得生活一点” → 推荐 `peach-soft`；首屏应出现 `DAILY NOTE`，章节序号为深陶色胶囊，文末是 `PEACH END` 胶囊。
- “把这篇公司财报解读排成商业杂志风” → 推荐 `noir-gold`；首屏应出现 `NOIR BRIEF`，章节编号是黑底灰金方块，文末是 `END OF ISSUE` 黑条。
- 三套都沿用“深色/浓色只出现在 hero，正文回浅底”；`noir-gold` 深底上的文字必须用 `darkink/darkbody/ondark`，不得直接用金色 `accent` 压黑底。
- 三套均为通用主题，文末保留“写在最后 + 在看/转发/关注”CTA；`insight`、`comparison`、`process`、`metrics`、表格、引用、列表和代码块必须继续通过公众号 HTML 校验。

## 公共事件档案自动化回归

- `enabled=false` → 不联网、不初始化工作区、不创建草稿，定时结果为 `[SILENT]`。
- 人物只有纪委监委审查调查通报、没有生效裁判 → 淘汰，不能称为贪污犯。
- 人物有法院生效裁判但没有中国官方媒体佐证 → 淘汰，不降低信源要求。
- 重大事故没有刑事判决，但已有政府调查报告与新华社报道 → 可进入排序。
- 同一 `case_key` 已完成 → `reserve` 返回 `already_completed`，必须换题。
- `draft/add` 已发出后超时 → 保留 reservation，禁止第二天自动重发。
- 合格稿只从 `solemn-gray`、`news-wire`、`formal-brief` 中固定主题，不进入全主题随机池。
- `source-dossier.json` 存在时，`gen_inline_images.py --force-generate` 仍必须跳过 AI 图；用户已提供的真实图片仍可保留。
- 三个以上有正文的二级章节 → 自动生成至多一张 `process` 型“公开事实脉络”；每条 evidence 和插入锚点必须是正文原句，改成不存在的句子后渲染器降级为纯正文。
- 正式报道封面 → `gen_cover_image.py` 不得调用 Agnes；Chrome 可用时输出 `html_render`，不可用时自动输出带准确标题的 `offline_render`。
- 普通科技/观点稿封面 → 生成提示词包含类型、色板、渲染、风格、情绪五类设计维度，明确禁止文字/数字/Logo；不得回退到全题材共用的粉彩手绘模板。

## 关键行为核对（用 assets/sample-article.md 或含代码块/图片的文跑一遍）

- [ ] 流水线主题来自 `prepare` 哈希，不是按文章类型匹配
- [ ] 渲染器用 `THEMES` 的 layout 分支，不手写组件 HTML
- [ ] 无「本文看点 / 目录」模块；摘要后直接第一节
- [ ] 正文引号生成时即为全角弯引号，无需事后替换
- [ ] 代码块走代码块组件，不塞进段落
- [ ] 图片用图片组件、GIF 加动图角标
- [ ] 正文半角标点被改成中文全角（代码块内不动）
- [ ] 开头引言卡署名按文章作者/主题定，不固定某个作者名
- [ ] 尾部签名区默认用 `{{作者名}}` 占位（不写死人名）；用户给了署名才填入，原文已有签名则沿用原文
- [ ] 原文已有签名段时合并进唯一签名区，不重复
- [ ] 强调/小标题用小标签或左竖条，无虚线框
- [ ] 代码块紧凑：每行一个 `<p style="margin:0">`，无 `white-space:pre`，无大段空白
- [ ] `【插入…】` 类待补占位用 2c 居中板块，不是左对齐提示块
- [ ] 骨架按所选主题库的"完整文章模板骨架"装配，不套用其它主题骨架
- [ ] 生成后跑 scripts/validate_gzh_html.py，ERROR 与半角 WARNING 清零

## 自定义主题生成行为

- 新主题加在 `render_article.py` 的 `THEMES`，登记 `theme-index.md`，补 `docs/gallery/<id>.html`
- 复用现有 layout 只改色值；不要新建 Markdown 组件库
- 跑 `tests.test_article_renderer` 与 `validate_gzh_html.py` 到 0 ERROR
- 主题 ID 与已有主题冲突 → 提示换名或确认覆盖，不静默覆盖

## 格式兼容用例

- 连续的 `1. 第一步` / `2. 第二步` → 逐项进入现有列表组件，保留文字、强调和顺序；与段落、章节正确分开。小数 `1.5`、日期 `2026.10.28` 和代码块中的编号保持原样。

- 给 `.docx` → 先跑 `scripts/extract_docx.py` 转 md，再结构确认，不直接读二进制
- 给 `.pdf` → Read 分页读取，删页眉页脚页码、合并硬断行，图位留居中占位
- 给无标记 `.txt`（含"一、二、"式标题）→ 正确推断为 `##`，结构确认后再排
- 给完全无标题的纯文本 + "直接排" → 全自动：语义分章 + 自拟标题 + 默认 `moyu-green`，交付附决策说明；不要按题材猜垂类主题
- 给 `.doc` 老格式 → 提示另存为 .docx，不硬解析

## 维护 · 可验证循环

改了组件库或 SKILL 后，按这个闭环验证，确保不引入排版反模式（大空白、左对齐占位、正文虚线框、平台禁用项）：

1. **改** 组件库 / SKILL / 脚本
2. **源头关**：`python3 scripts/component_lint.py .`
   扫所有组件库的 ```html 块，检测 `white-space:pre`（大空白）、四周虚线框 `border:…dashed`（正文，居中占位块豁免）、平台禁用项（div/class/id/style/grid/position/var/@media）。须 **0 ERROR**。
3. **生成** 用改后的 skill 排版 `assets/sample-article.md`（或真实文章）
4. **产物关**：`python3 scripts/validate_gzh_html.py <产物.html>`
   检测禁用标签、`<span leaf>` 包裹、半角标点。须 **0 ERROR、半角 0 WARN**。
5. 任一关不过 → 回第 1 步，直到两关全绿。

两脚本分工：`component_lint` 管「组件库源头不含反模式」，`validate_gzh_html` 管「最终产物合规」。源头干净 → 产物必然跟着干净，这是循环成立的依据。
