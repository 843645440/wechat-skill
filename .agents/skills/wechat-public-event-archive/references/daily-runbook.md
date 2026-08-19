# 每日运行手册

`<ARCHIVE>` 为本 Skill 目录，`<PIPELINE>` 为 `../wechat-content-pipeline`，`<ROOT>` 为项目根目录。

## 1. 开关与历史

```bash
python3 <ARCHIVE>/scripts/archive_state.py check --project-root <ROOT>
python3 <ARCHIVE>/scripts/archive_state.py list --project-root <ROOT> --limit 100
```

`allowed=false` 时停止并返回 `[SILENT]`。不要在定时任务里修改开关。

## 2. 搜索、核验与候选排序

使用联网搜索比较 3—8 个候选。先找权威机关材料，再找中国官方媒体报道；打开原文核对，不以
搜索结果摘要定案。逐个套用 `selection-policy.md` 的人物或事件门禁，剩余候选按配置权重排序。

若没有候选通过全部硬门禁，停止并返回一条简短说明；定时投递不希望收到空跑通知时返回
`[SILENT]`。

## 3. 抢占选题

至少传入两条最终采用的官方来源：

```bash
python3 <ARCHIVE>/scripts/archive_state.py reserve \
  --project-root <ROOT> \
  --key '<case_key>' \
  --subject '<人物或事件>' \
  --category '<配置允许的类别>' \
  --source-url '<权威机关原文 URL>' \
  --source-url '<官方媒体原文 URL>'
```

保存返回的 `reservation_id`。若 `reserved=false`，换下一个候选。

## 4. 建立受控 brief

读取 `<PIPELINE>/SKILL.md` 和写作清单，随后初始化：

```bash
python3 <PIPELINE>/scripts/pipeline_job.py init \
  --project-root <ROOT> --account <check 输出的 account> --topic '<选题>'
```

在 `job_contract.paths.work_dir` 中写 `source-dossier.json` 和 `user-brief.md`。Brief 至少写明：

- 公共事件档案模式；克制、正式、事实优先。
- 生效裁判或官方结论及其日期。
- 按来源 ID 标注的时间线、主要事实和处理结果。
- 必须写到：结论状态、治理影响、公开信息边界。
- 不要写：猎奇细节、推测动机、被害人隐私、行动号召、防骗清单、关注转发段。
- 配图：正文不配图；封面使用流水线离线方案。

写作开始前验证 dossier：

```bash
python3 <ARCHIVE>/scripts/archive_state.py validate-dossier \
  --project-root <ROOT> --file <source-dossier.json> \
  --reservation-id '<reservation_id>'
```

只有 `valid=true` 才能继续。校验失败说明结论状态、信源类型、claim 映射或隐私门禁不完整；修正
公开材料能够支持的字段，不能用推测补齐。

然后运行原流水线的 `topic --source provided`、`shape --auto`、`begin`。`event_focus` 用一句可核验
事实概括，不制造悬念。

## 5. 写作、体检与排版

根据 brief 和 dossier 写 `article.md`、`digest.txt`。每个事实都必须能回到 claim，不从模型记忆
增补案件细节。运行 `check`，最多进行两轮针对性修正；仍未达到 score 75 或仍有 high/blocking
问题时停止，不为过关添加虚构数字或情节。

按原流水线完成 humanize、正文图阶段和封面。正文图应自然 `skipped`。在 `prepare` 前限定主题：

```bash
python3 <PIPELINE>/scripts/pipeline_job.py choose-theme --job <job.json> \
  --theme solemn-gray --theme news-wire --theme formal-brief
```

随后运行 `prepare` 和 `finish`。只允许 `draft`，不调用独立发布命令。

## 6. 状态收尾

真实草稿创建成功：

```bash
python3 <ARCHIVE>/scripts/archive_state.py complete \
  --project-root <ROOT> --key '<case_key>' --reservation-id '<reservation_id>' \
  --run-id '<run_id>' --draft-id '<draft_media_id>'
```

确认远端不可能已有草稿的前置失败：

```bash
python3 <ARCHIVE>/scripts/archive_state.py release \
  --project-root <ROOT> --key '<case_key>' --reservation-id '<reservation_id>' \
  --reason '<明确失败原因>'
```

研究后发现候选不符合硬门禁：使用 `reject`，避免未来重复消耗核验成本。`draft/add` 已发出但结果
不确定时执行 `uncertain`，随后通知人工检查草稿箱；不得自动重发：

```bash
python3 <ARCHIVE>/scripts/archive_state.py uncertain \
  --project-root <ROOT> --key '<case_key>' --reservation-id '<reservation_id>' \
  --reason 'draft/add 已发出但结果不确定，等待人工核对'
```

人工确认草稿存在后用原 reservation 执行 `complete`；确认不存在后才可 `release`。

成功报告只包含：选题、类别、生效裁判/官方结论、采用的官方来源、主题、账号和草稿 ID；不得
展示任何密钥。
