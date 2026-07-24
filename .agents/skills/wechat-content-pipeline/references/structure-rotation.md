# 文章结构轮换（防同质 / 低创作度）

微信侧更敏感的是**正文语义骨架重复**，不是排版主题换皮。流水线用账号级 `topic-history.json` 记录每篇的结构形状，写作前强制轮换。

## 何时执行

1. 选题前后读历史（**务必加 `--rotation`**）：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py history \
  --job <WORK_DIR>/job.json --days 7 --rotation
```

2. 写作**开始前**根据 `rotation.preferred_*` / `blocked_*` 选定本轮形状，并锁定：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py shape \
  --job <WORK_DIR>/job.json \
  --structure-id conflict \
  --opening-type emotion_sting \
  --ending-type unresolved \
  --felt-sense 发紧 \
  --tension-type efficiency_vs_duty \
  --heading-count 3 \
  --body-band mid
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
| `heading_count` | `##` 个数 2–5 | 禁止连续三篇相同个数 |
| `body_band` | `short`/`mid`/`long` | 字数带宽轮换 |

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

- `short`：约 1500–1900 字  
- `mid`：约 1900–2600  
- `long`：约 2600–4000（勿为凑长注水）

## 与强情感的关系

强情感**不能**变成新模具。若连续多篇都是：

> 我很烦 → 通稿假 → 责任三点 → 我站队  

即使 `structure_id` 写了 `felt_essay`，也会同质。必须同时换 **opening / ending / tension / felt_sense / heading_count**。

## 排版

主题随机、信息模块 0–3 仍是辅。**剥成纯 Markdown 后骨架仍双胞胎 = 失败**，换主题无效。

## 失败与排障

- `shape` 报错：按 `history --rotation` 的 preferred 重选。  
- 历史缺 shape 字段：旧条目不参与计数，从本轮开始积累。  
- `--force`：仅人工确认后的例外，cron 默认禁止。
