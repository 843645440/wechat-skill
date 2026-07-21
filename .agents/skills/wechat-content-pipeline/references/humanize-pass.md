# 流水线内 Humanizer-zh 去 AI 味（写后、排版前）

在 `article.md` / `sources.md` 写完之后、`pipeline_runtime.py prepare` 之前，**必须**做一次去 AI 味。只此一次，不得循环。

## 加载哪个 Skill

优先加载已安装的 **`humanizer-zh`**（来源：GitHub `op7418/Humanizer-zh`）。  
不要用英文 `humanizer` 替代中文公众号正文。

路径优先级：

1. monorepo 内：`<wechat-skill>/.agents/skills/humanizer-zh/SKILL.md`（随本包提交，推荐）
2. 独立安装：`~/.hermes/skills/creative/humanizer-zh/SKILL.md`

Skill 名均为 **`humanizer-zh`**。

## 强度档位（默认 strong）

未指定时 **一律 `strong`**。用户或 job 显式指定时才改用其它档。

| 档位 | 做什么 | 不做什么 |
|------|--------|----------|
| `light` | 删明显 AI 词、空泛连接、三段式排比；少动句式与结构 | 不大改节奏、少加个人判断句 |
| `medium` | 去套话 + 适度打散句式与小标题措辞，语气更自然 | 不强行加“我读完…”类反应；改动幅度中等 |
| **`strong`（默认）** | 在 medium 基础上拉满节奏与判断：短句断句、口语化、标题更冲、报告腔再拆一层；可有**克制**的阅读反应（如“读完最深的感觉…”） | **仍禁止**虚构第一人称经历、伪访谈、未核验细节；不增事实；不删光 `##`/表格/必要加粗 |

强度只影响**文风改写幅度**，不改变事实门禁与字数门禁。

记账时写入档位，便于复盘：

```bash
--detail 'pass=humanizer-zh;intensity=strong'
```

## 在流水线中的位置

```text
begin → 写 article.md + sources.md → humanize（本步，默认 strong）→ prepare → inline-visuals → finish
```

阶段记账：

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name humanize --status running

# …按 humanizer-zh + 本文件强度规则就地改写 article.md …

python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name humanize --status completed \
  --detail 'pass=humanizer-zh;intensity=strong'
```

## 硬约束（覆盖 humanizer-zh 里与公众号冲突的建议）

1. **只改 `article.md`**，不改 `sources.md`，不新增事实、数据、机构表述、引语或案例。
2. **保留唯一一级标题**（可微调措辞，仍 ≤32 字，且保持“具体对象 + 动作 + 落点”）。strong 下标题可以更冲，但仍须具体、可核验，禁悬空金句。
3. **保留 `##` 小标题结构**（可改写标题文字，不要整篇打成无小标题长文）。
4. **保留语义 Markdown**：表格、少量 `**加粗**`、列表仍可用于扫读；不要为“去 AI”删光结构。
5. **字数**：改写后正文仍须落在 **1500—4000**（`prepare` 硬门禁）。去 AI 不是删成短讯，也不是注水拉长。
6. **禁止**为“有灵魂”而编造第一人称经历、伪访谈、未核验细节；strong 允许克制判断与场景化表述，但须能被 `sources.md` 支撑。
7. **禁止**聊天腔收尾（“希望对你有帮助”“让我们一起”）、emoji、英文 AI 套话直译残留。
8. 只跑 **一轮** humanize；不要 humanize → 再全文改写 → 再 humanize。
9. **默认 intensity=`strong`**；仅当用户明确要求 light/medium 时降档。

### strong 操作要点（默认执行）

- 拆长句，拉开长短节奏；少用“此外/值得注意的是/综上所述/赋能/助力/深刻变革”。
- 把报告腔改成读者能感到压力的表述，但数字、人名、机构、日期原样可核对。
- 可加少量“读完/对照体感”类反应句，**禁止**编造“我在某公司亲历…”“采访了某人…”。
- 结尾避免金句海报体；收在具体动作或速度差上。

## 完成标准

- `article.md` 已覆盖写入去 AI 后的终稿（默认 strong 质感）。
- `job.json` 中 `stages.humanize.status=completed`，detail 含 `intensity=strong`（或用户指定档）。
- 随后才能 `prepare`；`prepare` 按去 AI 后的正文统计字数并锁主题。

## 失败

若 humanize 后字数越界：在**同一轮 humanize 内**调回区间，不得进入 prepare。  
若模型几乎没改：仍标记 completed 前必须至少达到当前档位最低改动（strong：句式与语气须明显离开初稿报告腔，而非只换两三个词）。
