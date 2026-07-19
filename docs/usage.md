# wechat-skill 使用指南

`wechat-skill` 是面向云端 AI Agent 的微信公众号内容工具包。它能单独完成写作、去 AI 味或排版，也能通过编排 Skill 自动完成“选题到草稿箱”的完整流程。

## 1. Skill 组成

| Skill | 用途 |
|---|---|
| `wechat-skill` | 根 Skill：已有文章排版、HTML 校验、多账号草稿上传 |
| `wechat-tech-insight-writer` | 科技、AI、产业、企业和民生深度写作 |
| `humanizer` | 删除机械表达和 AI 写作痕迹；完整流水线中强制执行 |
| `wechat-inline-visuals` | 从正文提取信息，插入与当前排版主题一致的公众号原生 HTML 模块 |
| `wechat-html-cover` | 用编辑报刊风或动态字构风 HTML/CSS 模板生成确定性封面 PNG |
| `wechat-content-pipeline` | 联网选热点并编排全部阶段，最终创建草稿 |
| `baoyu-*`、`agnes-image-gen` | 可选独立图片能力；完整流水线不会调用 |

## 2. 安装和加载

完整工具包应作为 Agent 工作区使用：

```bash
git clone https://github.com/843645440/wechat-skill.git
cd wechat-skill
```

确保云端 Agent 能读取根 `SKILL.md` 和 `.agents/skills/`。不要只复制根 Skill，否则写作、Humanizer、原生信息模块、封面和完整工作流不会一起加载。

运行环境需要 Python 3。Chrome/Chromium 只用于生成封面；正文信息模块是公众号原生 HTML，不需要浏览器截图或图片 API Key。自动热点发现需要联网能力，创建草稿需要公众号 API 权限。

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

封面渲染器会自动查找 Chrome、Chromium 或 Playwright Chromium。只有自动发现失败时才设置：

```bash
export WECHAT_COVER_BROWSER='/path/to/chrome-or-chromium'
```

可以用仓库测试规格做一次离线封面渲染，不连接图片 API：

```bash
python3 .agents/skills/wechat-html-cover/scripts/render_cover.py \
  --spec tests/fixtures/html-cover.json \
  --html-output /tmp/wechat-cover.html \
  --output /tmp/wechat-cover.png
```

若账号已有固定封面素材，可设置：

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

不提供选题时，对 Agent 说：

> 使用 `$wechat-content-pipeline` 为 A 账号运行完整流程。联网发现最新可靠的科技热点，完成写作、事实核验、去 AI 味、随机主题排版、同主题原生信息模块和封面，并自动发送到 A 账号草稿箱。

提供明确选题时：

> 使用 `$wechat-content-pipeline` 为 B 账号写一篇“AI 如何改变基层客服工作”的文章，完成全部流程并发送到 B 账号草稿箱。

完整流程固定为：

1. 使用给定选题，或联网比较最新热点。
2. 写作、来源记录和事实核验。
3. 强制运行 Humanizer，再次核对事实。
4. 随机选择注册主题并完成基础排版。
5. 从正文提取 0—3 个观点、比较、流程或已核验数据，直接插入当前主题 HTML。
6. 用固定 HTML/CSS 生成唯一的封面 PNG。
7. 严格校验公众号 HTML。
8. 自动创建指定账号草稿，到此结束。

正文阶段不创建 PNG、SVG 或截图，不调用生图 API，不做 AI 视觉检测，也不上传正文视觉素材。流水线不会公开发布；人工审核发生在微信公众号草稿箱。

## 5. 在 Agent 定时任务中使用

定时由 Agent 自带自动化能力负责，Skill 内没有 cron 或固定时间。可以建立两个外部任务：

- 早间：`使用 $wechat-content-pipeline 为 A 账号运行完整流程；不指定选题，自动发现热点并创建草稿。`
- 晚间：`使用 $wechat-content-pipeline 为 B 账号运行完整流程；不指定选题，自动发现热点并创建草稿。`

定时任务直接提供选题时，流水线跳过热点选择。排版主题仍随机选择，不按账号写死。

## 6. 单独使用某项能力

只写文章：

> 使用 `$wechat-tech-insight-writer` 写一篇关于人形机器人进入汽车工厂的公众号文章。

只排版已有文章并自动提取信息模块：

> 使用 `$wechat-skill`，把 `article.md` 用石墨极简主题排成公众号 HTML。

只生成原生信息模块：

> 使用 `$wechat-inline-visuals`，从已排版的文章提取信息并按当前主题插入原生 HTML 模块。

只生成稳定封面：

> 使用 `$wechat-html-cover`，根据最终标题和当前主题生成公众号封面。

封面模板可选 `editorial-ledger` 与 `kinetic-type`。两套模板均跟随正文主题色，目前不按 A/B 账号写死；需要固定账号规则时再修改账号档案。

只有明确希望使用生成式图片时，才单独调用 `$baoyu-cover-image`、`$baoyu-article-illustrator` 或 `$agnes-image-gen`；它们不属于默认流水线。

## 7. 运行产物

每个账号只复用一个内部工作区：

```text
work/a/current/
work/b/current/
```

产物包括 `article.md`、`sources.md`、`inline-visuals.json`、`article.html`、`article_preview.html`、`cover/cover.spec.json`、`cover/cover.html`、`cover/cover.png` 和 `draft-result.json`。新任务覆盖同账号上一轮临时产物；微信草稿箱不受影响。

## 8. 常见阻塞

- **没有可靠热点**：本轮停止，不使用旧闻或传闻凑稿。
- **原生模块计划校验失败**：修正锚点或删除无证据模块；不要补造事实。
- **找不到浏览器**：安装 Chrome/Chromium，或设置 `WECHAT_COVER_BROWSER`；只影响封面。
- **封面生成失败**：同一命令最多技术性重试一次；有永久封面则降级使用，没有封面则不创建草稿。
- **公众号接口报错**：检查接口权限、IP 白名单、AppID/AppSecret 和账号别名。
- **HTML 校验失败**：运行 `python3 scripts/validate_gzh_html.py article.html`，修到 ERROR 和 WARNING 都为零。
- **出现作者占位符**：流水线会阻止上传；填写真实作者或删除署名组件。

开发或修改 Skill 后运行：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/component_lint.py .
```

## 9. 来源与许可

- 根排版组件、`wechat-inline-visuals`、`wechat-html-cover` 和编排工作流按仓库根 `LICENSE` 的 AGPL-3.0 使用。
- `baoyu-article-illustrator` 与 `baoyu-cover-image` 来源于 [JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills)，许可证保存在 `.agents/skills/LICENSE`。
- `humanizer` 来源于 [blader/humanizer](https://github.com/blader/humanizer)，许可证保存在 `.agents/skills/humanizer/LICENSE`。
