---
name: wechat-public-event-archive
description: 受控系列选题上游。仓库默认是科技/AI 系列；仅当本机 config/local 启用 public-event 预设时，才核验官方材料并策展公共事件档案。不自动公开发布。
metadata:
  hermes:
    tags: [wechat, research, public-events, automation]
    category: content
    requires_toolsets: [web]
---

# 公共事件档案自动生产

本 Skill 是 `wechat-content-pipeline` 的受控上游：它负责自动找题、官方信源核验、准入、
去重和生成事实 brief；写作、体检、排版、封面与微信草稿仍由原流水线完成。

## 不可越过的边界

- 先运行 `archive_state.py check`。优先读 `<ROOT>/config/local/public-event-archive.json`（本机，不入库），否则读仓库默认配置。
- 仓库默认 `preset=tech-ai`：这是科技/AI 系列，本 Skill **不**按公共事件档案搜案、不写涉黑涉恶。
- 只有本机配置 `preset=public-event` 且 `enabled=true` 时才允许搜案写作。`allowed=false` 时返回 `[SILENT]`。
- 只创建微信公众号草稿，绝不调用公开发布接口。
- 人物犯罪稿必须已有生效裁判；只有审查调查、立案侦查、起诉或一审未生效时不写此人。
- 重大事件稿可以没有刑事判决，但必须已有官方调查报告、责任认定或稳定的官方结论。
- 每个选题必须同时有权威机关材料和中国官方媒体佐证。没有合格选题就跳过当天，禁止降级到
  自媒体、匿名爆料、境外转述或模型记忆。
- “涉黑”“恶势力”“犯罪集团”“组织者、领导者”等称谓只照生效裁判或官方结论写。
- 不消费被害人苦难，不公开未成年人、被害人及普通家属的不必要个人信息，不补写动机、对白、
  内幕或现场细节。

## 每日执行入口

进行自动生产前，完整读取：

1. [选题与核验规则](references/selection-policy.md)
2. [每日运行手册](references/daily-runbook.md)

先运行开关和状态检查：

```bash
python3 <SKILL>/scripts/archive_state.py check --project-root <ROOT>
```

输出的 `allowed` 必须为 `true`。配置里的账号、主题白名单、信源数量和输出目标是本轮权威值，
不得由定时提示词覆盖为公开发布。

## 受控交接

研究完成后，先为选题生成稳定 `case_key`，再调用 `archive_state.py reserve`。抢占失败说明该题
已写过或被其他任务占用，应换下一个候选，不能并发重复生产。

初始化原流水线后，在它给出的 `work_dir` 中写两个文件：

- `source-dossier.json`：逐项事实、结论状态、来源 URL 和隐私标记；格式见选题规则。
- `user-brief.md`：把 dossier 转成写作 brief，明确“公共事件档案模式、克制正式、正文不配图”。

写作前必须运行 `archive_state.py validate-dossier`。校验不通过时拒绝候选，不能只凭 Agent 自检
继续生产。

随后仍以 `--source provided` 固化选题。这里的 `provided` 表示“已由受控上游核验并提供”，
不是 `auto-hotspot`，也不受 48 小时热点窗口限制。

排版只从 `solemn-gray`、`news-wire`、`formal-brief` 中选择。完成 `finish` 并确认真实草稿 ID后，
才执行 `archive_state.py complete`。`draft/add` 结果不确定时保留 reservation 并通知人工核查；明确
未创建草稿的前置失败才可 `release`，之后允许重试。

## 定时职责

Skill 不保存几点运行。Hermes 的 Cron 负责唤醒并加载本 Skill；推荐部署命令和首次验收步骤见
[Hermes 部署](references/hermes-deployment.md)。搜索、核验和写作需要 Agent 判断，禁止使用
`--no-agent`。
