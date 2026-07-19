# 多账号草稿与外部 Agent 触发

发布层按账号隔离凭证、`access_token` 和封面素材。原文自带远程图片时，发布脚本仍会按目标账号上传；自动内容流水线不会主动生成正文图片。账号必须已开通对应接口权限，并将执行环境的公网 IP 加入公众号白名单。

## 1. 配置账号

```bash
cp assets/wechat-accounts.example.json wechat-accounts.json
export WECHAT_A_APP_ID='...'
export WECHAT_A_APP_SECRET='...'
export WECHAT_B_APP_ID='...'
export WECHAT_B_APP_SECRET='...'
```

不要把 AppSecret 写进 JSON 或提交到 Git。`accounts` 可增加任意别名，每个别名通过 `appid_env` 和 `secret_env` 指向独立环境变量。常用固定封面可把账号专属的永久素材 ID 放进 `default_thumb_media_id_env`。

## 2. 校验并创建草稿

先列出账号并做离线检查：

```bash
python3 scripts/wechat_publish.py --config wechat-accounts.json accounts
python3 scripts/wechat_publish.py --config wechat-accounts.json send \
  --account a --html work/a/current/article.html --title '文章标题' \
  --cover work/a/current/cover/cover.png --action draft --dry-run
```

去掉 `--dry-run` 后，脚本会校验 HTML，上传封面和原文自带的远程图片，再创建草稿。素材属于各自账号；同一篇带原图的 HTML 发给 A/B 时也必须分别上传。

`wechat-content-pipeline` 的固定终点是草稿箱：

```bash
python3 scripts/wechat_publish.py --config wechat-accounts.json send \
  --account a --html work/a/current/article.html --title '文章标题' \
  --cover work/a/current/cover/cover.png --action draft --strict \
  --result-file work/a/current/draft-result.json
```

草稿成功后由人进入微信公众号草稿箱审核。自动流水线不调用 `publish`，也不把“创建草稿”误写成“群发给粉丝”。根工具保留公开发布命令，仅供用户在独立、明确要求时手动使用。

## 3. 由 Agent 定时任务触发

时间配置放在 Agent 自带的定时任务中，不写进 Skill、账号档案或仓库脚本。每次触发只需告诉 `wechat-content-pipeline`：

- 目标账号别名，例如 `a` 或 `b`。
- 可选主题；省略时由流水线联网发现最新可靠热点。

例如，Agent 的早间任务传入“为 A 账号运行完整流水线”，晚间任务传入“为 B 账号运行完整流水线”。Skill 会自行重建 `work/<account>/current/`，强制去 AI 味、随机排版并自动创建草稿。

凭证必须由云端密钥管理或运行环境变量提供，不能出现在定时任务文本、仓库配置、日志或任务产物中。首次启用前，分别对 A、B 运行一次 `--dry-run` 和真实草稿联调。
