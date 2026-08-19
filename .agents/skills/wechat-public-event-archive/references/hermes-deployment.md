# Hermes 云端部署

推荐使用 Hermes 原生 Skill-backed Cron。这个任务需要联网研究、事实判断和写作，因此不要用
系统 `crontab`，也不要使用 Hermes 的 `--no-agent` 脚本模式。

## 1. 固定项目路径并信任项目 Skill

以下以 `/srv/wechat-skill` 为例，实际路径可以替换：

```bash
cd /srv/wechat-skill
hermes skills trust /srv/wechat-skill
hermes skills list
```

Hermes 会发现仓库中的 `.agents/skills/`。Cron 是非交互会话，不会自行弹窗请求信任，所以必须
提前执行 `hermes skills trust`。

## 2. 配置时区和 Cron 工具集

```bash
hermes config set timezone Asia/Shanghai
hermes tools
```

在 `hermes tools` 中选择 `cron` 平台，至少启用联网搜索/网页读取、terminal、文件读取与写入。
不要给定时会话公开发布权限；微信只需要仓库脚本读取环境变量并创建草稿。

完成公众号环境变量、云主机固定出口 IP 白名单和账号 `b` 的一次人工真实草稿验收后再启用日更。

## 3. 启动常驻网关

云端 Linux 推荐系统服务：

```bash
sudo hermes gateway install --system
hermes cron status
```

## 4. 创建每日任务

下面示例每天北京时间 09:00 运行，投递目标按你的 Hermes 平台替换：

```bash
hermes cron create "0 9 * * *" \
  "运行公共事件档案每日任务。严格读取仓库 config/public-event-archive.json；开关关闭或没有合格选题时返回 [SILENT]。有合格题材时只生成账号 b 的微信公众号草稿，绝不公开发布，并报告选题、来源和草稿 ID。" \
  --skill wechat-public-event-archive \
  --workdir /srv/wechat-skill \
  --deliver telegram \
  --name "wechat-public-event-daily"
```

Cron 会启动全新会话，因此提示词必须自包含；真正的长规则由挂载 Skill 提供，不要把规则全文
复制进 prompt。

为避免日后切换聊天模型导致无人值守任务停止或意外增加费用，创建后给这个 job 固定 provider
和 model：

```bash
hermes cron edit wechat-public-event-daily --provider '<provider>' --model '<model>'
```

## 5. 先手动触发，再等定时

```bash
hermes cron run wechat-public-event-daily
hermes cron runs wechat-public-event-daily --limit 5
hermes cron list
```

检查公众号草稿箱、`work/b/current/job.json`、`draft-result.json` 和
`state/public-event-archive.sqlite3`。首次运行不通过时先暂停：

```bash
hermes cron pause wechat-public-event-daily
```

修正后手动触发验证，再 `hermes cron resume wechat-public-event-daily`。

## 开关

真正的生产开关是 `config/public-event-archive.json` 的 `enabled`：

- `true`：Cron 到点后允许研究和生成草稿。
- `false`：Cron 仍存在，但立即静默退出，不搜索、不消耗写作调用、不创建草稿。

时间表属于 Hermes，内容生产许可属于仓库配置。暂停几天优先关 `enabled`；维护 Hermes 或彻底
停掉调度时再使用 `hermes cron pause`。
