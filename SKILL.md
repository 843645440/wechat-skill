---
name: wechat-skill
description: 微信公众号文章排版与多账号发布工具，把已有 Markdown、DOCX、PDF 或纯文本转成可直接粘贴或通过官方 API 写入草稿箱/发布的 HTML。用于用户明确要求“公众号排版”“微信排版”“转公众号 HTML”“自动排版”“一键排版”、上传草稿、发布已有文章或配置多账号发布时。单独要求撰写文章时使用 wechat-tech-insight-writer；要求从选题一路完成写作、排版和草稿发布时使用 wechat-content-pipeline。不用于普通网页、落地页或 PPT；发布能力不等同于向粉丝群发。
---

# 公众号文章排版 Skill

把一篇 Markdown 转成粘进公众号编辑器后样式不丢的 HTML。

**排版由脚本完成，不要手写 HTML。**渲染器是
`.agents/skills/wechat-content-pipeline/scripts/render_article.py`，主题、组件、
内联样式、`<span leaf="">` 包裹、章节编号、代码块缩进全部在里面确定性生成。

> 历史上本 Skill 要求 Agent 读取大型 Markdown 组件库再手写 HTML。旧组件已从活跃分支移除，
> 需要考古时从 Git 历史读取；当前实现只以固定渲染器为准。

## 主流程（五步，无分支）

设 `RENDER=.agents/skills/wechat-content-pipeline/scripts/render_article.py`。

```bash
# 1. 非 Markdown 输入先归一化（见下节），已是 md 则跳过
# 2. 选主题：读 references/theme-index.md，取一个 --theme 标识
# 3. 渲染
python3 $RENDER --article <输入.md> --theme <标识> --output "<原名>_排版_<中文名>(<标识>).html"
# 4. 校验（ERROR 必须 0，半角标点 WARNING 也要修到 0）
python3 scripts/validate_gzh_html.py "<上面的 html>"
# 5. 生成带「复制」按钮的预览页
python3 scripts/wrap_preview.py "<上面的 html>"
```

交付时告诉用户：**打开 `{...}_预览.html` → 点右上角「复制到公众号」→ 编辑器里粘贴**，
并给出干净正文文件路径作为兜底，附校验结论。

`render_article.py` 成功时 stdout 打一行 JSON（`status` / `title` / `theme` / `image_count`）。
校验或渲染报错时**回去改 `article.md`**，不要去改产物 HTML，也不要新写渲染脚本。

### 第 1 步：输入归一化

用户可能给 Markdown 文本、`.md` 路径、`.docx`、`.pdf`、`.txt`/无标记纯文本、网页富文本。
**非 Markdown 一律先读 [references/format-normalize.md](references/format-normalize.md) 按其规则转成 Markdown 草稿**（docx 用 `scripts/extract_docx.py`，PDF 用 Read 分页读取 + 清噪，纯文本按标题启发式推断结构）。什么都没给就向用户索要。

### 第 2 步：选主题

读 [references/theme-index.md](references/theme-index.md)（只有 ~1 KB 的选择表）。
用户指定了就用；题材明显契合某套就用那套并说明理由；没倾向用 `moyu-green`；
**被 `wechat-content-pipeline` 调用时用编排器已固定的主题，不重选、不询问**。

用户说「直接排 / 自动排 / 一键 / 不用问」→ 全自动模式：不提问，自动推断结构与主题，交付时附决策说明。

## 渲染器认得的 Markdown

写 `article.md` 时只用下面这些，脚本会挑对应组件。**其它花样不保证。**

| 元素 | 写法 | 产出 |
|---|---|---|
| 文章标题 | `# 标题`（**全文只能一个**） | 主题封面/引言卡 |
| 开头引言 | 文章最前面的 `> 引用` | hero 引言 |
| 章节 | `## 标题` | 编号章节标题（`01/02/…`，末章为结语/总结类自动用 `∞`） |
| 子章节 | `### 标题` | 左竖条小标题 |
| 正文 | 普通段落 | 正文段 |
| 下划线强调 | `**文字**`、`++文字++`、`<u>文字</u>` | 主题下划线 |
| 高亮 | `==文字==` | 主题色底高亮 |
| 行内代码 | 反引号 | 等宽药丸 |
| 代码块 | ` ``` ` 围栏（可带语言） | 代码块组件，缩进与换行保留 |
| 引用 | 非开头的 `> 文字` | 引用块 |
| 列表 | `- 项` / `1. 项` | 列表组件 |
| 表格 | `\|` 分隔 | 表格组件 |
| 图片 / GIF | `![说明](路径)`，**独占一行、路径不含空格** | 图片组件（有 alt 才生成说明） |

**下划线是本 Skill 的核心特色，但它现在是写作期的事**：脚本只把 `**…**` 渲染成下划线，
**决定标哪些词是写作者的活**。所以排版前确认正文里每段有 1–3 个 `**关键短语**`
（核心观点、结论、关键数据、专有名词，4–15 字）。原文一个加粗都没有时，主动补上再渲染
——这是出现频率最高的基础标记，缺了排出来会很平。

正文标点用全角（，。！？：；""''（）—— …）；代码块、行内代码、英文专名/URL 内部保持原样。
半角标点是校验脚本最高频的 WARNING 来源，**在写 `article.md` 时就写对**，别指望事后替换。

## 不要做的事

- 不要手写或手改 HTML 组件，不要为单篇文章新建渲染脚本。
- 不要从 Git 历史恢复旧组件来手写 HTML。
- 不要解析 `theme-index.md` 去发现主题——`--theme` 的 choices 才是全集。
- 产物是**纯 `<section>…</section>` 正文片段**，不带 `<!DOCTYPE>`/`<html>`/`<head>`/`<body>`。这由脚本保证，别去包壳。
- 署名：没有真实作者信息就**省略署名组件**，不要把 `{{作者名}}` 之类占位符带进产物或草稿箱。
- 文末的「在看 / 转发 / 关注」引导由渲染器自动追加，**正文里不要再写一遍**。

## 能力边界与协作

- 只需要写作 → 转交 `wechat-tech-insight-writer`，不要在本 Skill 代写正文。
- 从选题到草稿箱一条龙 → 转交 `wechat-content-pipeline`，用它的 `pipeline_job.py` / `pipeline_runtime.py` 命令链，不要在本 Skill 另写排版或封面实现。
- 流水线排障 → 先读 `work/<account>/current/job.json`，再读 `.agents/skills/wechat-content-pipeline/references/pipeline-failure-triage.md`。
- 正文配图 → `.agents/skills/wechat-content-pipeline/scripts/gen_inline_images.py`（用户图优先；机制图走 `xiaohu:xiaoyi`；失败可无图）。封面 → `gen_cover_image.py` 一条命令自动走用户图 → `xiaohu:agnes` → Pillow 离线兜底。
- 审计草稿恢复以 `run_id` 为幂等边界：同时核对 job 阶段、`draft-result.json` 的账号、动作、`run_id` 和 `draft_media_id`；`running`/`uncertain` 禁止自动重发。

## 可选：多账号草稿与发布

用户要求上传草稿、提交发布或配置多公众号时，先读 [references/multi-account-publishing.md](references/multi-account-publishing.md)，用 `scripts/wechat_publish.py` 执行，不手写临时请求：

1. 让用户复制 `assets/wechat-accounts.example.json`，每个账号用别名注册；AppID/AppSecret 只从各自环境变量读取。
2. 首次先 `--dry-run`，再逐账号 `--action draft` 并人工验收。
3. 只有用户明确要求公开发布时，才 `publish --media-id <已审核草稿ID>` 发布现有草稿。不要在审核后再用 `send --action publish` 创建第二份草稿。向用户说明这是「发布」而非「群发给粉丝」。
4. 外部 Agent 的定时任务只负责触发并传入 `--account`；本 Skill 不创建定时器。原文图片按账号分别上传，封面素材必须属于目标账号。

IP 白名单错误（40164）：报告出口 IP，等用户加白后**只重跑发布这一步**，不重写正文。

## 平台红线（脚本已保证，改脚本时才需要关心）

- **禁止**：`<style>`/`<script>`/`<div>`、`class`/`id` 属性、`position:fixed/absolute/sticky`、`float`、`@media`/`@keyframes`、`display:grid`、CSS 变量、外部字体/CSS。
- **必须**：样式全内联；所有文字节点用 `<span leaf="">文字</span>` 包裹（否则粘贴后样式整片丢失）。
- **可用**：`display:flex`（有限）、`linear-gradient`、`border-radius`、`box-shadow`、`<section>/<p>/<span>/<strong>/<img>/<h3>`。
- 代码块用「每行一个 `<p style="margin:0">`」，**绝不用 `white-space:pre`**；缩进用 `&nbsp;`。
- `<img>` 用 `max-width:100%;height:auto;display:block;margin:0 auto`，**不用 `width:100%`**（会把小图拉糊）；只有表格/封面卡/流程图才用 `width:100%`。

改 `render_article.py` 后必须把全部注册主题各渲染一遍 + `validate_gzh_html.py` 到 0 ERROR + 跑
`python3 -m unittest discover -s tests`。加新主题见 `references/theme-index.md`。

> 触发与主题选择的回归用例见 `references/eval-cases.md`。
