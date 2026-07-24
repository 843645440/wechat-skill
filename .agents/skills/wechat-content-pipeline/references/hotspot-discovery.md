# 自动热点发现

仅在触发请求没有提供主题时执行。

## 搜索范围

使用可用网络检索工具查找最近 48 小时信息。优先来源包括政府或监管公开文件、企业公告与产品文档、论文与标准组织、可靠媒体原始报道。

## 选题业务条件（前 3 项硬性 + 故事核硬性）

1. 类别必须在账号档案 `topic_discovery.categories` 中。
2. 热点发布时间满足 `0 <= 当前时间 - published_at <= 48 小时`；未来时间不得放行。
3. 与最近 7 天已采用主题不是同一核心事件。
4. **必须能写清故事核**（缺一不可，否则换题）：
   - `event_focus`：哪个主体发生了什么核心变化（一句话）。
   - `hook`：读者为什么要点开（一句话，面向账号受众）。
   - `tension`：核心矛盾（如效率 vs 责任、演示 vs 部署、便宜 vs 可信）。
   - `reader_stakes`：目标读者可能感到的具体代价、压力或误判风险。

不要求至少两个来源域名，不要求每个证据 URL 都带发布时间。写作时仍应核实实际使用的事实，不得把搜索摘要当作已证实事实。

## 优先选什么 / 不要选什么

**优先：**

- 有清晰 tension，且能触发作者**具体情绪**（烦、发紧、兴奋、无力等），不是纯功能清单。
- 对账号 `audience` 有切身 stakes（工作流、成本、责任、公共服务体验等）。
- 通稿容易讲歪、值得带火气纠偏或深挖代价的事件。
- 能在 32 字内做出“信息锚点 + 情感刺点”标题的题材。

**降权或跳过：**

- 只有发布会形容词、写不出矛盾与情绪的“又发布了”。
- 只能写成中立说明书/参数介绍的材料。
- 与近 7 天 event_focus 同事件仅换皮。
- 无法核验的传闻、股市诱导、敏感政治动员类。

没有合格故事核时标记 `discover=failed` 并报告原因，**不用**旧闻或说明书题凑数。

## 七天语义去重

先运行：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py history \
  --job <WORK_DIR>/job.json --days 7
```

读取历史中的 `event_focus`（及若有的 `tension`），由 Agent 判断候选是否是同一核心事件：

- 明确同一事件：拒绝候选并换题。
- 明确不同事件：放行。
- 拿不准：默认放行，避免误阻塞。

代码不做标题完全匹配、bigram、Jaccard 或相似度阈值判断。不得把纯粹换标题当成新事件。

## 写入最终选题

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py topic \
  --job <WORK_DIR>/job.json \
  --value "最终选题（可与标题不同，但应含可读的故事核指向）" \
  --source auto-hotspot \
  --category "<账号允许类别>" \
  --published-at "<ISO 8601 且含时区>" \
  --event-focus "<一句话核心事件>" \
  --hook "<为什么要点开>" \
  --tension "<核心矛盾>" \
  --reader-stakes "<读者切身代价或压力>"
```

`published_at` 在此处只校验一次。选题落库后，prepare、gate 和 finish 不因生产时间流逝而再次拦截。

写作阶段必须把 `hook` / `tension` / `reader_stakes` 吃进 `article.md`（见 `wechat-tech-insight-writer`）。  
最终标题不超过 32 字，**禁止**纯汇报体；规则见写作 style-guide。

没有可靠热点或写不出故事核时标记 `discover=failed` 并报告原因，不用旧闻、传闻或编造信息凑稿。
