---
name: wechat-content-pipeline
description: 编排中文微信公众号文章：用户提供主题与大致思路后，完成写作、humanize、可降级正文配图、生图或用户指定封面、随机主题并写入指定公众号草稿箱。默认不自动选题、不扫热点；不公开发布。
---

# 微信公众号内容生产流水线

**默认模式：用户命题。**用户给出主题 + 大致思路，本 Skill 扩写成稿并送到指定账号草稿箱。

- **禁止**在未获主题时自行联网选题、换题或「找个热点凑一篇」。
- **禁止**公开发布（仅草稿箱，除非用户另行明确要求）。

## 怎么用这份文档

**每一条命令的 stdout 都会告诉你下一条命令**（`next_command` 字段），`begin` 还会给出
`writing_contract`——全部写作硬门禁的机器可读卡片。**照命令链和卡片走就能完成全程。**

下面的「命令链」是全部流程。只有卡在某一步时才去读对应的 reference。

⚠️ 链上有 **3 步没有命令**，是你自己写文件，最容易漏：

1. `init` 之后写 `user-brief.md`（第 2 步）
2. `begin` 之后写 `article.md` + `digest.txt`（第 5 步）
3. humanize 阶段就地改写 `article.md`（第 7 步）

其余每一步都有现成命令，**不要自己发明命令、不要新建脚本**。

## 命令链

`<PIPELINE>` = 本 Skill 根目录，`<ROOT>` = 项目根目录。所有产出路径由 `init` 打印的
`job_contract.paths` 给出绝对路径，**不要自己推算路径**。

```bash
# 1. 初始化（生成 run_id，清空重建工作区，打印 job_contract）
python3 <PIPELINE>/scripts/pipeline_job.py init --project-root <ROOT> --account <账号> --topic "<用户主题>"

# 2. 落盘用户 brief —— 必须在 init 之后（init 会清空工作区）
#    写到 job_contract.paths.work_dir/user-brief.md，格式见 references/user-brief.md
#    这一步没有命令，是你自己写文件；init 的 next_command 会提醒你。

# 3. 固化选题（source 必须是 provided）
python3 <PIPELINE>/scripts/pipeline_job.py topic --job <job.json> --value "<主题>" --source provided --event-focus "<一句话核心>"

# 4. 锁定结构（防同质，默认 --auto，同 run_id 稳定，永不死锁）
python3 <PIPELINE>/scripts/pipeline_job.py shape --job <job.json> --auto

# 5. 开始写作 → 输出 writing_contract，照卡片写 article.md（+ digest.txt）
#    写作本身没有命令，是你自己写文件。
#    ⭐ 写之前先读 ../wechat-viral-writer/references/writing-checklist.md（一页纸硬要求）
#    ⭐ 标题先用 3 个不同刺点的候选跑一次排序（30 秒，比写完再改省事）：
#       python3 <ROOT>/.agents/skills/wechat-viral-writer/scripts/score_draft.py \
#               --markdown --titles "候选A" "候选B" "候选C"
#    深度风格读 ../wechat-tech-insight-writer/SKILL.md
python3 <PIPELINE>/scripts/pipeline_runtime.py begin --job <job.json>

# 6. 自检（不改状态，一次列出全部问题与修法，修到 status=ok）
#    check 会连带跑写作体检，结果在 `writing` 字段（score / grade / dimensions）。
#    体检的 high 级问题会并进 problems，带 [写作·xxx] 前缀；score < 75 也会拦。
python3 <PIPELINE>/scripts/pipeline_runtime.py check --job <job.json>
#    想看逐条修法的完整报告（推荐，问题多的时候直接跑这条）：
python3 <ROOT>/.agents/skills/wechat-viral-writer/scripts/score_draft.py \
        --article <article.md> --markdown

# 7. Humanize（就地改写 article.md，默认 intensity=strong）
python3 <PIPELINE>/scripts/pipeline_job.py stage --job <job.json> --name humanize --status running
#    ⚠️ 这一步没有脚本，是你自己动手改写。读 ../humanizer-zh/SKILL.md 拿改写手法，
#    读 references/humanize-pass.md 拿本流水线的尺度限制，然后直接编辑 article.md。
#    不新增事实，不删 brief 要求保留的时间线与结论，不把字数改到 1500 以下。
python3 <PIPELINE>/scripts/pipeline_job.py stage --job <job.json> --name humanize --status completed --detail intensity=strong

# 8. 正文配图（一条命令，退出码恒为 0，自己记账）
python3 <PIPELINE>/scripts/gen_inline_images.py --article <article.md> --imgs-dir <imgs/> --seed <run_id> \
        --job <job.json> --record-stage
#    --record-stage 会自动完成 running → completed/skipped 记账，**跑完不要再补 stage 命令**。
#    （漏标 running 会被 stage 门禁直接拒绝，这是这一环最常见的失败方式。）

# 9. 封面（一条命令，退出码恒为 0，自己记账）
python3 <PIPELINE>/scripts/gen_cover_image.py --job <job.json> --record-stage
#    它内部走完整降级链：用户图 → 生图 → 离线兜底，保证有封面（封面是 finish 硬门禁）。
#    无网络/无 API key 也能出图；要跳过生图直接兜底加 --skip-generate。

# 10. Prepare（校验标题、字数、humanize、图片数与路径安全，固定主题）
python3 <PIPELINE>/scripts/pipeline_runtime.py prepare --job <job.json>

# 11. Finish（验收封面，写草稿箱，文件锁防双草稿）
python3 <PIPELINE>/scripts/pipeline_runtime.py finish --job <job.json> --config <ROOT>/wechat-accounts.json
```

## 三条硬门禁

### 1. 用户 brief（第 1 步之前）

用户须提供**主题**（一句话）+ **大致思路**（要点、时间线、论点、素材或大纲，可短）。
可选：目标读者、情绪、必须写到的点、禁止写的点、配图/封面路径、字数偏好。

缺主题，或思路为空（只有一句话题目、无可展开材料）→ **停止并追问**，最多 1–2 个问题。
**不得**自行找热点填空。详见 [references/user-brief.md](references/user-brief.md)。

⚠️ `user-brief.md` 必须写在 `init` **之后**。`init` 会清空重建工作区，在它之前落盘会被清掉。

### 2. 图片降级链

**正文配图**——全部交给 `gen_inline_images.py` 一条命令，它内部就是这条链：

| 情况 | backend | status |
|---|---|---|
| 用户已给图（article.md 已引用真实文件，或 imgs/ 里已有图） | `user_provided` | `completed` |
| 无用户图，生图成功 | `image_generate` | `completed` |
| 无用户图，无候选位（文章太短/全是代码表格） | `none` | `skipped` |
| 无用户图，生图失败（无 key / 超时 / 非图片 / 后端非零退出） | `none` | `skipped` |

**生不出图就不配图，这是正常结果，不是失败。**脚本退出码恒为 0，article.md 保持原样，
绝不会留下指向不存在文件的 `![]()`。不要自己分析文章挑插图位，不要视觉审图。

**封面**（`finish` 的硬门禁）——同样是**一条命令**，`gen_cover_image.py` 内部走完整降级链：

| 情况 | backend | status |
|---|---|---|
| `cover/cover.png` 已存在（用户给的） | `user_provided` | `completed`（原样保留，绝不覆盖） |
| 无用户图，生图成功 | `image_generate` | `completed` |
| 无用户图，生图失败/无 key/无后端 → 自动离线兜底 | `offline_render` | `completed` |
| 生图和兜底都失败 | `none` | `failed` |

```bash
python3 <PIPELINE>/scripts/gen_cover_image.py --job <job.json> --record-stage
```

**正文图可以没有，封面不能没有**——所以这条链一直走到出图为止，不需要你判断走到第几档。
只有第 4 行那种极端情况才会 `failed`，此时只有账号配了默认 `thumb_media_id` 才能继续。

`check` 在封面缺失时会把这条命令拼好放进 `hints`。**禁止 HTML 封面与视觉审图。**
标题取 `article.md` 的一级标题，眉标取账号 label，都不需要你传参。

### 3. 写作契约

`begin` 输出的 `writing_contract` 是权威。**照卡片执行即可满足所有硬门禁。**要点：

- **忠实 brief（第一信源）**：不换题、不推翻用户主判断与事实线；可润色、补机制解释与可读结构。
- 标题 ≤32 字，禁止周报体。
- **正文 1500–4000 字**。这里的字数是 `check` 算出来的**纯正文中文字符数**：已扣掉
  `#` 标题、开头引言、图片引用、代码块和空白，所以**远小于 `wc -c` 的字节数**。
  别用 `wc` 自估，写完直接跑 `check` 看它报的数。首轮写太短是最高频的返工点。
- 按已锁 structure 组织，但**内容顺序优先服务 brief 大纲**。
- 每段留 1–3 个 `**关键短语**`——渲染器把它渲染成主题下划线，是排版的基础标记，缺了排出来会很平。
- **读者价值服从题材**：有可执行点再写清单；历史案件、人物传记类以认知增量与事实线为主，禁止硬塞防骗清单。
- 禁止编造亲历；禁止把用户未提供的「内幕」写成既定事实。
- **正文不写关注段**：文末「在看 / 转发 / 关注」由渲染器自动追加，正文再写一遍就是重复。
- **摘要**：另写一句 ≤50 字到 `digest.txt`——它是分享卡片副标题，要补标题没说完的第二钩子（关键数字、悬念下半句、读者代价），不要复述标题。

深度风格细节读 `wechat-tech-insight-writer`。声口与 `writer_instructions` 已内联在 `init` 的
`job_contract.account_profile` 里，不必另读账号档案文档。

### 3.5 写作体检（`check` 自动带）

写作契约管的是**交付合法性**，体检管的是**有没有人读得下去**。两者不重叠，都要过。

`check` 的输出里有一个 `writing` 字段：

```json
"writing": {"score": 86.8, "grade": "B", "pass_line": 75,
            "dimensions": {"hook": 20, "value_density": 25, "reader_benefit": 15,
                           "readability": 17.8, "retention": 9},
            "report_command": "python3 …/score_draft.py --article … --markdown"}
```

- 体检的 **high 级问题会并进 `problems`**（前缀 `[写作·xxx]`），`score < 75` 也会拦。
- 问题多的时候直接跑 `report_command`，它给的是**逐条修法**，不是评价。
- 五个维度的判据和阈值见 `../wechat-viral-writer/SKILL.md`；写之前先读它的
  [writing-checklist.md](../wechat-viral-writer/references/writing-checklist.md)，
  可以少返工一轮。
- ⚠️ **不许为了刷分塞假数字、假案例、假亲历。**体检是用来发现问题的，不是用来刷的。

## 主题

由 `pipeline_job.py choose-theme` 从 `render_article.py` 的 `THEMES` 里**按 run_id 派生**：
跨文章会轮换，同一个 run 重跑必然选到同一套（恢复时不换皮）。

主题的单一真相源就是 `render_article.py`。**不要读 `archive/themes-v2/` 下的 Markdown 组件库，
不要手写排版 HTML，不要为单篇文章新建渲染脚本。**

## 幂等与恢复

- 同一 `run_id` 已成功：账号、动作、`run_id`、`draft_media_id` 全匹配时直接返回原结果。
- 新 `run_id`：允许同账号当天继续新草稿。**不得**因为今天已有 `drafted` 就退出。
判定标准只有一条，**不是错误码枚举**：这次失败之后，远端草稿箱里有没有可能已经躺着一篇草稿？

- **`draft/add` 已发出但没读到响应**（timeout / EOF / 连接重置 / 响应无法解析）→ `outcome=uncertain`，
  `retry_safe=false`，**禁止自动重发**，先人工核对草稿箱。这是唯一会走到这一档的情况。
- **其余全部失败**（取 token 被拒、正文图/封面上传失败、服务端对 `draft/add` 明确返回 errcode）
  → `preflight-failed`，`retry_safe=true`。草稿一定没建，**直接重跑 `finish` 即可，不必手工重置 draft 阶段**。
- IP 白名单错误（40164）属于上面第二档：**要加白的 IP 就在错误信息里**（微信实际看到的直连出口）。
  ⚠️ 不要用 `curl ifconfig.me` 取 IP——发布器强制直连 `api.weixin.qq.com`（忽略 `HTTP(S)_PROXY`），
  而 curl 走本机代理，有分流规则时两者不是同一个出口，加白 curl 给的那个不会生效。
  加白后只重跑 `finish`，不重写正文。
- `state=failed` 且 draft 曾 running/uncertain → 重置 format/draft 为 pending，确认 `article.md` 契约后 prepare → finish。继续现有工作区，**禁止无故 init 新 job**。
- write 未完成就中断 → 有 brief 则照 brief 写完；**禁止**改为自动热点选题。

`init` 之后任何一步的 stdout 都带 `next_command`，卡住时先看它，再读
[references/pipeline-failure-triage.md](references/pipeline-failure-triage.md)。

## 完成核验

同时满足才可报告成功：

1. `job.json.state == drafted`
2. `stages.draft.status == completed`
3. `draft-result.json` 的账号、`action==draft`、`run_id` 一致
4. `draft_media_id` 非空且非占位符（不得含 dummy/fake/placeholder/test/mock/sample）

`draft-result.json` 只能由 `pipeline_runtime.py finish` 写入，**agent 不得手写伪造**。

最终报告：主题、是否用了用户配图、主题皮肤、正文图数、账号、`article.html` 路径、草稿 ID。
**不得展示密钥。**

## 需要时才读

| 卡在哪 | 读什么 |
|---|---|
| 写作体检不过线、标题/开头/节奏 | [`../wechat-viral-writer/SKILL.md`](../wechat-viral-writer/SKILL.md) |
| 不知道写什么（需要开热点开关） | [`../wechat-viral-writer/references/hot-topic-radar.md`](../wechat-viral-writer/references/hot-topic-radar.md) |
| brief 格式、缺项追问、忠实扩写边界 | [references/user-brief.md](references/user-brief.md) |
| 结构池与近文轮换 | [references/structure-rotation.md](references/structure-rotation.md) |
| humanize 改写尺度 | [references/humanize-pass.md](references/humanize-pass.md) |
| 封面生图 | [references/ai-cover-generation.md](references/ai-cover-generation.md) |
| 任何一步报错 | [references/pipeline-failure-triage.md](references/pipeline-failure-triage.md) |
| 工作区/阶段语义（`init` 的 job_contract 没覆盖到的） | [references/artifact-contract.md](references/artifact-contract.md) |

> 自动热点发现已**默认关闭**。仅当账号档案显式 `topic_discovery.enabled=true` 且用户要求
> 自动选题时才走那条路，历史文档在 `archive/pipeline-refs-v1/hotspot-discovery.md`，
> 不得作为日常路径。`--source auto-hotspot` 在默认模式下禁用。
