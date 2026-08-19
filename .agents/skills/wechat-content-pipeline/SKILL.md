---
name: wechat-content-pipeline
description: 编排中文微信公众号文章：用户提供主题与大致思路后，完成写作、humanize、可降级正文配图、生图或用户指定封面、随机主题并写入指定公众号草稿箱。默认不自动选题、不扫热点；不公开发布。
---

# 微信公众号内容生产流水线

把用户给出的主题和思路扩写成文章，经写作体检、去 AI 味、配图、封面和排版后写入指定公众号草稿箱。

## 边界

- 默认必须有用户提供的主题与思路；缺一项就追问，不联网另找题，不自行换题。
- 唯一自动选题例外是已明确启用的 `wechat-public-event-archive`。它必须先产出通过校验的 `source-dossier.json` 和完整 `user-brief.md`，本流水线仍按 `--source provided` 接收。
- 只创建草稿，不公开发布。不得把 API 密钥、token 或素材 ID 写进文章和日志。
- 只用下列固定命令和 `init` 声明的工作区文件；不新建临时脚本、单篇渲染器、封面 JSON 或视觉审图循环。
- `optional-skills/` 的完整说明仍按需加载；主流水线只复用其中的确定性 HTML 封面渲染器与信息模块校验器，不读取整份扩展 Skill。

## 执行原则

`<PIPELINE>` 是本 Skill 目录，`<ROOT>` 是项目根目录。每条命令的 JSON 输出都含下一步提示；路径一律取 `init` 返回的 `job_contract.paths`，不要自行拼接。

有三步由 Agent 编辑文件：`init` 后写 brief，`begin` 后写正文，humanize 阶段就地改正文。其余步骤全部使用现成命令。

## 固定命令链

```bash
# 1. 初始化。注意：它会重建本账号 current 工作区。
python3 <PIPELINE>/scripts/pipeline_job.py init \
  --project-root <ROOT> --account <账号> --topic '<主题>'

# 2. 把主题、思路、边界和素材偏好写入 <work_dir>/user-brief.md。
#    公共事件档案同时写 <work_dir>/source-dossier.json，并先由上游校验。

# 3. 固化选题、读取近文轮换并锁定结构。
python3 <PIPELINE>/scripts/pipeline_job.py topic \
  --job <job.json> --value '<主题>' --source provided --event-focus '<一句话核心>'
python3 <PIPELINE>/scripts/pipeline_job.py history --job <job.json> --rotation
python3 <PIPELINE>/scripts/pipeline_job.py shape --job <job.json> --auto

# 4. 输出 writing_contract。写作前先读 writing-checklist.md，随后写 article.md；
#    建议另写一句不复述标题的 digest.txt。
python3 <PIPELINE>/scripts/pipeline_runtime.py begin --job <job.json>

# 5. 写作体检。按 problems 修到 status=ok；需要逐条修法时运行输出中的 report_command。
python3 <PIPELINE>/scripts/pipeline_runtime.py check --job <job.json>

# 6. Humanize：只改 article.md 一轮。
python3 <PIPELINE>/scripts/pipeline_job.py stage \
  --job <job.json> --name humanize --status running
python3 <PIPELINE>/scripts/pipeline_job.py stage \
  --job <job.json> --name humanize --status completed \
  --detail 'intensity=<strong|restrained>'

# 7. 先固定主题，再生成证据绑定的原生信息模块；随后处理可选正文图与封面。
python3 <PIPELINE>/scripts/pipeline_job.py choose-theme --job <job.json>
python3 <PIPELINE>/scripts/build_inline_visuals.py --job <job.json>
python3 <PIPELINE>/scripts/gen_inline_images.py \
  --article <article.md> --imgs-dir <imgs_dir> --seed <run_id> \
  --job <job.json> --record-stage
python3 <PIPELINE>/scripts/gen_cover_image.py --job <job.json> --record-stage

# 8. 终检并创建草稿。
python3 <PIPELINE>/scripts/pipeline_runtime.py prepare --job <job.json>
python3 <PIPELINE>/scripts/pipeline_runtime.py finish \
  --job <job.json> --config <ROOT>/wechat-accounts.json
```

写作前必须完整读取 [`../wechat-viral-writer/references/writing-checklist.md`](../wechat-viral-writer/references/writing-checklist.md)。Humanize 时读取 [`../humanizer-zh/SKILL.md`](../humanizer-zh/SKILL.md) 和 [`references/humanize-pass.md`](references/humanize-pass.md)，就地覆盖 `article.md`，不要把改写说明写进正文。

## 三道门禁

### Brief

正常模式至少需要：主题、思路或时间线、必须写到/避免写到的内容。公共事件档案模式还必须有已通过上游校验的 dossier；当天没有合格材料就跳过，不以传闻、模型记忆或普通热点代替。格式见 [`references/user-brief.md`](references/user-brief.md)。

`user-brief.md` 必须在 `init` 之后写，因为 `init` 会重建工作区。

### 正文

以 `begin` 返回的 `writing_contract` 为权威，并遵守：

- 标题只有一个一级标题，≤32 字；主题明确，避免周报体和空洞悬念。
- 纯正文 1500—4000 字，以 `check` 结果为准，不用字节数估算。
- 忠实 brief、dossier 和来源边界；不编造数字、引语、案例、亲历、采访或内幕。
- 按锁定结构组织，但事实与 brief 的叙事顺序优先；每段可保留 1—3 个真实关键短语的 `**强调**`。
- 不硬塞清单。历史案件和人物稿优先事实线、机制与治理影响；正文不写关注、转发或在看引导。
- `check`、`prepare`、`finish` 都会运行写作体检。最终稿必须 score ≥75 且 blocking/high 为 0；不得用假细节刷分。

### 媒体与草稿

- 素材方式先服从用户 brief；没有指示时服从账号档案。用户图优先且不覆盖。
- 原生信息模块由 `build_inline_visuals.py` 生成或校验。公共事件最多一张“公开事实脉络”，全部文案必须来自最终正文；普通文章默认不加。无效计划自动降级为空。
- AI 正文图只走 `gen_inline_images.py`：用户图优先；公共事件强制跳过 AI 图，其他题材无 Key、超时或失败都可 `skipped`。
- 封面只走 `gen_cover_image.py`：用户图优先；公共事件/正式报道走准确标题 HTML；普通观点稿按紧凑艺术指导走 `xiaohu:agnes` 无文字主视觉；随后依次降级到 HTML、Pillow、账号默认素材。
- 主题由 `choose-theme` 按 `run_id` 稳定选择；检测到公共事件档案或正式报道时自动限定为 `solemn-gray`、`news-wire`、`formal-brief`。
- `finish` 默认创建草稿；只有开发验证才使用 `--dry-run`。不得直接调用独立发布命令绕过门禁。

## 幂等与完成判定

同一 `run_id` 成功后重复执行应返回原结果；新 `run_id` 可以在同一天创建新草稿。若 `draft/add` 已发出但未读到响应，结果为 `uncertain` 且 `retry_safe=false`：禁止自动重发，先人工核对草稿箱。明确的前置失败可在修复后只重跑 `finish`。

只有同时满足以下条件才能报告成功：

1. `job.json.state == drafted`；
2. `stages.draft.status == completed`；
3. `draft-result.json` 的账号、`action == draft`、`run_id` 一致；
4. `draft_media_id` 非空且不是测试占位符。

`draft-result.json` 只能由 `finish` 生成。最终报告主题、配图来源、排版主题、正文图数、账号、HTML 路径和草稿 ID，不展示密钥。

## 按需读取

| 场景 | Reference |
|---|---|
| brief 格式与忠实扩写边界 | [`references/user-brief.md`](references/user-brief.md) |
| 结构池与近文轮换 | [`references/structure-rotation.md`](references/structure-rotation.md) |
| Humanize 尺度 | [`references/humanize-pass.md`](references/humanize-pass.md) |
| 封面降级链 | [`references/ai-cover-generation.md`](references/ai-cover-generation.md) |
| 中断、字数、图片、草稿不确定 | [`references/pipeline-failure-triage.md`](references/pipeline-failure-triage.md) |
| 工作区与阶段语义 | [`references/artifact-contract.md`](references/artifact-contract.md) |
| 深度写作声口 | [`../wechat-tech-insight-writer/SKILL.md`](../wechat-tech-insight-writer/SKILL.md) |

通用热点雷达默认关闭，也不会自动选题。公共事件档案是独立、受控且需要稳定官方结论的上游，不等于恢复热点模式。
