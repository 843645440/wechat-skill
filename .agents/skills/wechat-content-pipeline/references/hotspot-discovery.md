# 自动热点发现

仅在触发请求没有提供主题时执行。

## 搜索范围

使用可用网络检索工具查找最近 48 小时信息。优先来源包括政府或监管公开文件、企业公告与产品文档、论文与标准组织、可靠媒体原始报道。

选题只保留三个业务条件：

1. 类别必须在账号档案 `topic_discovery.categories` 中。
2. 热点发布时间满足 `0 <= 当前时间 - published_at <= 48 小时`；未来时间不得放行。
3. 与最近 7 天已采用主题不是同一核心事件。

不要求至少两个来源域名，不要求每个证据 URL 都带发布时间，不要求受影响人群等元数据字段。写作时仍应核实实际使用的事实，不得把搜索摘要当作已证实事实。

## 七天语义去重

先运行：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py history \
  --job <WORK_DIR>/job.json --days 7
```

读取历史中的 `event_focus`，由 Agent 判断候选是否是同一核心事件：

- 明确同一事件：拒绝候选并换题。
- 明确不同事件：放行。
- 拿不准：默认放行，避免误阻塞。

代码不做标题完全匹配、bigram、Jaccard 或相似度阈值判断。不得把纯粹换标题当成新事件，但也不要因为行业、公司或关键词相同就机械拒绝。

## 写入最终选题

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py topic \
  --job <WORK_DIR>/job.json \
  --value "最终选题" \
  --source auto-hotspot \
  --category "<账号允许类别>" \
  --published-at "<ISO 8601 且含时区>" \
  --event-focus "<一句话核心事件>"
```

`published_at` 在此处只校验一次。选题落库后，prepare、gate 和 finish 不因生产时间流逝而再次拦截。

最终标题不超过 32 字，包含可识别主体、明确动作和现实落点。没有可靠热点时标记 `discover=failed` 并报告原因，不用旧闻、传闻或编造信息凑稿。
