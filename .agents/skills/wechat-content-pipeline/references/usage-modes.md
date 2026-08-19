# 两条使用方式

后半段同一条流水线。变的是入口和门禁，不是排版/封面/草稿实现。

## 方式 1：用户成稿 `--lane manuscript`

用户交出 Markdown / Word / 已有正文。Agent 只做排版、可选去 AI 味、封面和草稿。

- `init --lane manuscript --topic '<标题>'`
- 把成稿写入 `article.md`（Word/PDF 先按根 Skill 归一化）
- 去 AI 味默认关；用户要求时 `--humanize`
- 不校验 1500—4000 字，不跑写作分
- 仍检查：一个一级标题、标题 ≤32 字、占位符、图片路径

## 方式 2：给主题，AI 写 `--lane brief`（默认）

用户给主题和思路，或打开系列选题（默认科技/AI）。

- 必须写作，去 AI 味强制开，不能 `--no-humanize`
- `check` / `prepare` / `finish` 拦字数和 score ≥75
- 默认系列见 `config/public-event-archive.json`（科技/AI）；由用户 Agent 的定时任务触发

只丢了一个标题、没有成稿，不要进方式 1。

## 配图

1. 用户或 Agent 已把图放进 `imgs/` 并插入正文 → 用现成图
2. Agent 有自带生图能力 → 先生成再跑 `gen_inline_images.py`
3. 否则仅在配置了 `AGNES_API_KEY` 时由脚本生成
4. 都没有 → 正文不配图

封面不能空：用户图 → 正式报道 HTML 标题 → 可选生图 → HTML/Pillow → 账号默认封面。

提示词和设计说明里不要写供应商名。免费 Key：<https://platform.agnes-ai.cn>
