---
name: wechat-viral-writer
description: 写有人愿意读完的中文微信公众号文章，并用脚本把「好不好」量化成分数。四个维度：信息量（每 300 字一个具体信息）、利他性（读者能带走的东西）、可读性（手机竖屏节奏）、抓人（钩子密度与闭环）。写完必须跑 score_draft.py 体检并修到 blocking=0 且 score≥75。自带默认关闭的热点雷达开关（hot_radar.py），开启后聚合 8 个公开榜单产出选题候选，但不自动选题、不自动写稿。用于用户要求「写公众号」「提高完读率」「这篇没人读」「找选题」时。
---

# 公众号写作 · 可量化版

这个 Skill 解决一件具体的事：**模型写完总觉得自己写得不错，但读者第三屏就退出了。**

办法是把「读者会不会读完」拆成四个能被脚本量出来的维度，写完必须过体检。
不靠感觉，靠分数。

## 30 秒上手

```bash
<SKILL> = .agents/skills/wechat-viral-writer

# 1）写稿前：读 references/writing-checklist.md（一页纸的全部硬要求）
# 1.5）先挑标题（写正文之前，30 秒）：三个候选用不同刺点，让它排序
python3 <SKILL>/scripts/score_draft.py --markdown --titles "候选A" "候选B" "候选C"

# 2）写完之后立刻体检，看 markdown 版逐条修法
python3 <SKILL>/scripts/score_draft.py --article <article.md> --markdown

# 3）改完重跑，直到 blocking_count = 0 且 score ≥ 75
# 4）（可选，默认关闭）今天写什么都不知道时，开热点雷达
python3 <SKILL>/scripts/hot_radar.py --force --markdown
```

体检脚本**退出码恒为 0**：不合格是结果不是故障，看 stdout 的 `status` 字段。

## 四个维度（体检脚本的 100 分怎么来的）

| 维度 | 分 | 一句话判据 | 量化指标 |
|------|----|-----------|---------|
| **开头/标题** | 20 | 前 3 秒有没有留住人 | 标题 ≤32 字、前 16 字有刺点、150 字内进正题 |
| **信息量** | 25 | 读者每 20 秒能不能拿到新东西 | 最长无锚区间 ≤300 字、注水词 ≤4/千字 |
| **利他性** | 20 | 读完能带走什么 | ≥2 种利他物、结尾四分之一有落点 |
| **可读性** | 20 | 手机上滑不滑得下去 | 段落 ≤180 字、长句 ≤20%、每 800 字一个小标题 |
| **抓人** | 15 | 有没有一直被拽着走 | 最长无钩区间 ≤500 字、结尾回扣开头 |

**及格线 75 分，且 high 级问题必须清零。**参考锚点：仓库里五篇旧的「新闻汇报腔」
稿件跑出来是 61–76 分（D/C），[examples/gold-sample.md](examples/gold-sample.md) 是 95.8 分（A）。

## 资源路由

**每次写稿必读**：

- [references/writing-checklist.md](references/writing-checklist.md) —— 一页纸硬要求，写之前读它就够了
- [references/hook-and-title.md](references/hook-and-title.md) —— 标题公式与开头钩子
- [references/value-density.md](references/value-density.md) —— 信息量：什么算「具体」，什么是注水

**按需读**：

- [references/reader-benefit.md](references/reader-benefit.md) —— 利他性：四种形态，按题材选，别硬塞
- [references/readability.md](references/readability.md) —— 竖屏排版节奏
- [references/structure-playbook.md](references/structure-playbook.md) —— 六种可选结构与适用题材
- [references/voice-playbook.md](references/voice-playbook.md) —— 大 V 声口拆解与可复用手法
- [references/distribution-2026.md](references/distribution-2026.md) —— 分发机制、指标口径、合规红线（**含信源可信度标注**）
- [references/hot-topic-radar.md](references/hot-topic-radar.md) —— 热点开关怎么开、怎么用、什么时候别用
- [examples/gold-sample.md](examples/gold-sample.md) —— 满分样例，看节奏不看内容

**和其他 Skill 的关系**：

- 排版、配图、封面、入草稿箱 → `../wechat-content-pipeline/SKILL.md`（本 Skill 不碰这些）
- 去 AI 味的具体改写手法 → `../humanizer-zh/SKILL.md`
- 账号声口与题材边界 → `../wechat-tech-insight-writer/SKILL.md`

## 接入流水线的位置

本 Skill 插在 `wechat-content-pipeline` 的**第 5 步（写作）和第 6 步（check）之间**：

```
init → user-brief.md → topic → shape → begin
   → 【本 Skill：写 article.md + digest.txt】
   → 【本 Skill：score_draft.py 体检，修到 ok】     ← 新增的这一步
   → check → humanize → 配图 → 封面 → prepare → finish
```

两个脚本的分工不重叠，**都要跑**：

- `pipeline_runtime.py check` 管**结构合法性**：几个标题、字数、图片路径越没越界。
- `score_draft.py` 管**有没有人读得下去**。它不会拦住你，但它给的每条问题都值 3–9 分。

## 硬门禁：不得交付

1. `score_draft.py` 的 `blocking_count > 0`，或 `score < 75`。
2. 全文没有任何读者可带走的东西（体检里的 `reader_benefit = 0`）——**白看一场**。
3. 标题前 16 字没有刺点：数字、反差、断言、疑问，一个都没有。
4. 为了凑指标塞假数字、假案例、假亲历。**体检分数是用来发现问题的，不是用来刷的。**
   编一个数字能加 3 分，但会让整个账号失去可信度——这条没得商量。
5. 硬塞与题材无关的「普通人怎么办」清单。利他性按题材选形态，见 reader-benefit.md。
6. 热点雷达输出的榜单标题被原样当成选题。**榜单标题是新闻标签，不是你的观点。**

## 一句话原则

> 读者不欠你注意力。每一段都要重新赢一次。
