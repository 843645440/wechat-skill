# 文章结构轮换（防同质 / 低创作度）

微信侧更敏感的是**正文语义骨架重复**，不是排版主题换皮。流水线用账号级 `topic-history.json` 记录每篇的结构形状，写作前强制轮换。

## 何时执行

1. 选题前后读历史（**务必加 `--rotation`**）：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py history \
  --job <WORK_DIR>/job.json --days 7 --rotation
```

2. 写作**开始前**锁定本轮形状。默认用 `--auto`（按轮换计划自动生成合法组合，同
   `run_id` 结果稳定，池耗尽自动放宽，永不死锁）：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py shape \
  --job <WORK_DIR>/job.json --auto
```

⚠️ **`--auto` 只保证轮换合法，它不懂题材。** `felt_sense` 与 `tension_type` 是内容相关字段，
自动结果可能与本篇相悖（例如给一篇讲违法解雇的稿子分到「欣慰」「振奋」）。**写作前必须复核这两项**，
不符就在 `--auto` 上叠加覆盖，其余字段仍自动：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py shape \
  --job <WORK_DIR>/job.json --auto \
  --felt-sense 讽刺 --tension-type efficiency_vs_duty
```

也可完全手工指定全部字段（此时自行对照 `rotation.preferred_*` / `blocked_*`）：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py shape \
  --job <WORK_DIR>/job.json \
  --structure-id conflict --opening-type emotion_sting --ending-type unresolved \
  --felt-sense 发紧 --tension-type efficiency_vs_duty \
  --heading-count 3 --body-band mid
```

3. 再 `begin` → 按已锁定 `article_shape` 写 `article.md`。  
   **禁止**先写完再随便填一个与正文不符的 shape。  
   轮换冲突时 `shape` 会失败；只有人工排障才允许 `--force`。

## 字段说明

| 字段 | 含义 | 轮换规则 |
|------|------|----------|
| `structure_id` | 主结构（见结构池） | 近 **7** 篇同一 id **≤2**；且避开近 **3** 篇已用 |
| `opening_type` | 开头类型 | 近 **5** 篇**不重复**；慎用 `date_announce` |
| `ending_type` | 结尾类型 | 近 **5** 篇**不重复** |
| `tension_type` | 矛盾类型 | 近 **5** 篇同一类型 **≤2** |
| `felt_sense` | 主情绪（短中文） | 近 **3** 篇尽量不雷同（Agent 自检） |
| `heading_count` | `##` 个数 2–5 | 禁止连续三篇相同个数；成稿至少 `heading_count-1` 个（不少于 2） |
| `body_band` | `short`/`mid`/`long` | 字数带宽轮换；`check`/`prepare`/`finish` 硬拦 |

### structure_id 池

| id | 读者一眼感 |
|----|------------|
| `felt_essay` | 主观强情感随笔 |
| `conflict` | 利害冲突驱动 |
| `myth_bust` | 先打通稿误区 |
| `workflow_day` | 一条工作流/一天 |
| `judgment_first` | 判断/站队前置 |
| `sting_list` | 清单刺点（真变化+被吹大） |
| `qa_drive` | 自问自答推进 |
| `quick_take` | 短快评（信息薄时） |
| `event_read` | 事件解读（仍用「我」） |
| `tech_explain` | 科技解释 |
| `company_compete` | 企业竞争 |
| `industry_game` | 产业博弈 |
| `tech_livelihood` | 科技民生 |
| `non_invest_finance` | 非投资财经 |

### opening_type

`emotion_sting` | `contrast` | `myth` | `scene` | `judgment_first` | `date_announce`（不推荐）

### ending_type

`duty_point` | `unresolved` | `actionable_question` | `hook_return` | `brief_approval`

### tension_type

`efficiency_vs_duty` | `demo_vs_deploy` | `cheap_vs_trust` | `speed_vs_safety` | `access_vs_privacy` | `hype_vs_adoption` | `other`

### body_band

硬门禁 2500–5000 字。`--auto` 会按结构信息密度给目标带宽（新闻/快评偏短，机制/产业偏长），并避开上一篇的 band。区间是闭区间，边界值（3300/4200）允许落在相邻两档：

- `short`：2500–3300 字（`quick_take` / `event_read`、正式报道）
- `mid`：3300–4200 字（默认）
- `long`：4200–5000 字（机制、产业、对比多；勿为凑长注水）

## 与强情感的关系

强情感**不能**变成新模具。若连续多篇都是：

> 我很烦 → 通稿假 → 责任三点 → 我站队  

即使 `structure_id` 写了 `felt_essay`，也会同质。必须同时换 **opening / ending / tension / felt_sense / heading_count**。

## 排版

主题随机、信息模块 0–3 仍是辅。**剥成纯 Markdown 后骨架仍双胞胎 = 失败**，换主题无效。

## 失败与排障

- `shape` 报错：按 `history --rotation` 的 preferred 重选。  
- 历史缺 `structure_id` 的条目不入轮换窗口；同一 `run_id` 更新而非新增。  
- `--force`：仅人工确认后的例外，cron 默认禁止。
