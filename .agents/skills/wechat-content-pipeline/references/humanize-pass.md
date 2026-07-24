# 流水线内 Humanizer-zh（写后、排版前）

`article.md` 写完后、`prepare` 前必须跑一轮，只一轮。

## 加载

1. `<wechat-skill>/.agents/skills/humanizer-zh/SKILL.md`  
2. 同目录 `references/wechat-pipeline-constraints.md`  
3. 本文件  

默认 **intensity=strong**。

## 目标（覆盖「去 AI = 变中立」）

成功标准：读起来像**懂行的人在带火气/兴奋/发紧地说话**，  
不是更干净的 briefing，也不是空洞鸡汤。

- 保留并**加强**已有的第一人称与具体情绪。  
- 删 AI 套话、报告腔、对称三段式。  
- 标题更像脱口刺点；若仍是汇报体必须改掉。  
- **不新增**事实、亲历、人物、数据、引语。

## 阶段记账

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name humanize --status running
# …改写 article.md…
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name humanize --status completed \
  --detail 'pass=humanizer-zh;intensity=strong;voice=strong-emotion'
```

## 硬约束

1. 只改 `article.md`。  
2. 唯一 `#` 标题，≤32 字，信息锚点 + 情感/判断钩子。  
3. 保留 `##` 与必要表格/加粗。  
4. 字数 1500—4000。  
5. 禁止编造亲历与伪访谈。  
6. **允许并鼓励**：我很烦、我发紧、我讨厌、有一瞬间我很兴奋、说真的……  
7. 禁止聊天收尾、emoji、希望对你有帮助。  
8. 只跑一轮；在本 stage 内改到过关。

### strong 操作

- 拆长句；删「赋能/值得注意的是/本文的判断是」。  
- 若初稿偏中立简报：在**不增事实**前提下注入主观反应与节奏，把机制接到「我为什么上火」。  
- 若初稿情绪悬浮：把形容词改成钉在权限/签字/验收/成本上的具体发堵。  
- 结尾避免海报金句；可留不适与追问。

### 完成 / 失败

- 完成：专栏主观 + 强情感可感 + 非说明书 + 事实未膨胀。  
- 失败：几乎没改、仍像汇报、情绪被抹平、字数越界 → 同 stage 内重写到过关，不得 mark completed。
