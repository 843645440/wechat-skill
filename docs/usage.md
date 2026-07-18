# wechat-skill 使用指南

`wechat-skill` 是一个面向云端 AI Agent 的微信公众号内容工具包。它既能单独完成写作、去 AI 味、配图或排版，也能通过编排 Skill 自动完成“选题到草稿箱”的完整流程。

## 1. Skill 组成

| Skill | 用途 |
|---|---|
| `wechat-skill` | 根 Skill：已有文章排版、HTML 校验、多账号草稿上传 |
| `wechat-tech-insight-writer` | 科技、AI、产业、企业和民生深度写作 |
| `humanizer` | 删除机械表达和 AI 写作痕迹；完整流水线中强制执行 |
| `baoyu-article-illustrator` | 分析文章并生成正文配图 |
| `baoyu-cover-image` | 生成微信公众号封面图 |
| `wechat-content-pipeline` | 联网选热点并编排以上全部阶段，最终创建草稿 |

## 2. 安装和加载

完整工具包应作为 Agent 工作区使用：

```bash
git clone https://github.com/843645440/wechat-skill.git
cd wechat-skill
```

确保云端 Agent 能读取根 `SKILL.md` 和 `.agents/skills/`。不要只复制根 Skill，否则写作、Humanizer、图片和完整工作流不会一起加载。

运行环境需要 Python 3。自动热点发现需要联网能力；自动配图需要可用的图片生成后端；创建草稿需要公众号 API 权限。

## 3. 配置公众号账号

复制无密钥模板：

```bash
cp assets/wechat-accounts.example.json wechat-accounts.json
```

为每个账号设置独立环境变量：

```bash
export WECHAT_A_APP_ID='公众号 A 的 AppID'
export WECHAT_A_APP_SECRET='公众号 A 的 AppSecret'
export WECHAT_B_APP_ID='公众号 B 的 AppID'
export WECHAT_B_APP_SECRET='公众号 B 的 AppSecret'
```

若账号已有固定封面素材，可额外设置：

```bash
export WECHAT_A_THUMB_MEDIA_ID='A 账号永久封面素材 ID'
export WECHAT_B_THUMB_MEDIA_ID='B 账号永久封面素材 ID'
```

账号别名与环境变量映射保存在 `wechat-accounts.json`；受众和内容偏好保存在 `config/wechat-content-profiles.json`。不要把 AppSecret、access token 或真实素材 ID 提交到 Git。

先做离线检查：

```bash
python3 scripts/wechat_publish.py --config wechat-accounts.json accounts
python3 scripts/wechat_publish.py --config wechat-accounts.json send \
  --account a --html article.html --title '测试文章' \
  --cover cover.png --action draft --dry-run
```

## 4. 完整自动工作流

### 不提供选题，自动抓热点

对 Agent 说：

> 使用 `$wechat-content-pipeline` 为 A 账号运行完整流程。不要预设选题，联网发现最新可靠的科技热点，完成写作、事实核验、去 AI 味、配图、随机主题排版，并自动发送到 A 账号草稿箱。

### 提供明确选题

> 使用 `$wechat-content-pipeline` 为 B 账号写一篇“AI 如何改变基层客服工作”的文章，完成全部流程并发送到 B 账号草稿箱。

用户不需要准备 `article.md`。写作阶段会自动生成它；该文件只是 Skill 之间的内部交接文件。

完整流程固定为：

1. 使用给定选题，或联网比较最新热点。
2. 写作并生成内部来源记录。
3. 核对时效事实、数据和企业表述。
4. 强制运行 Humanizer，再次核对事实。
5. 生成正文配图和封面。
6. 从已注册主题中随机选择排版主题。
7. 生成并严格校验公众号 HTML。
8. 自动创建指定账号草稿，到此结束。

流水线不会自动公开发布。人工审核发生在微信公众号草稿箱。

## 5. 在 Agent 定时任务中使用

定时由 Agent 自带的自动化能力负责，Skill 内没有 cron 或固定时间。可以建立两个外部任务：

- 早间任务提示词：`使用 $wechat-content-pipeline 为 A 账号运行完整流程；不指定选题，自动发现热点并创建草稿。`
- 晚间任务提示词：`使用 $wechat-content-pipeline 为 B 账号运行完整流程；不指定选题，自动发现热点并创建草稿。`

如定时任务直接提供选题，流水线会跳过热点选择。排版主题仍会随机选择，不按 A/B 账号写死。

## 6. 单独使用某项能力

只写文章：

> 使用 `$wechat-tech-insight-writer` 写一篇关于人形机器人进入汽车工厂的公众号文章。

只排版已有文章：

> 使用 `$wechat-skill`，把 `article.md` 用石墨极简主题排成公众号 HTML。

只去 AI 味：

> 使用 `$humanizer` 编辑 `article.md`，保留事实、数据和原观点。

只生成封面或正文配图时，分别调用 `$baoyu-cover-image` 和 `$baoyu-article-illustrator`。

## 7. 运行产物

每个账号只复用一个内部工作区：

```text
work/a/current/
work/b/current/
```

常见产物包括 `article.md`、`sources.md`、`article.html`、`article_preview.html`、`cover/cover.png` 和 `draft-result.json`。新任务会覆盖同账号上一轮临时产物；微信草稿箱中的文章不受影响。

## 8. 常见阻塞

- **没有可靠热点**：本轮停止，不使用旧闻或传闻凑稿。
- **图片后端不可用**：继续完成文章、排版和校验；没有封面或默认素材时不创建草稿。
- **公众号接口报错**：检查接口权限、IP 白名单、AppID/AppSecret 和账号别名。
- **HTML 校验失败**：运行 `python3 scripts/validate_gzh_html.py article.html`，修到 ERROR 和 WARNING 都为零。
- **出现作者占位符**：流水线会阻止上传；填写真实作者或删除整个署名组件。

开发或修改 Skill 后运行：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/component_lint.py .
```

## 9. 来源与许可

- 根排版组件和工作流按仓库根 `LICENSE` 的 AGPL-3.0 使用。
- `baoyu-article-illustrator` 与 `baoyu-cover-image` 来源于 [JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills)，许可证保存在 `.agents/skills/LICENSE`。
- `humanizer` 来源于 [blader/humanizer](https://github.com/blader/humanizer)，许可证保存在 `.agents/skills/humanizer/LICENSE`。
