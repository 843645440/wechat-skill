# wechat-skill 使用指南

`wechat-skill` 是面向云端 AI Agent 的微信公众号内容工具包。刚装好时对 Agent 说「帮我配置公众号技能」，见 [setup.md](setup.md)。有两种用法：用户成稿只排版，或给主题让 AI 写；后半段同一条流水线，只创建草稿。

## 1. Skill 组成

默认目录 `.agents/skills/` 只放全自动链路真正需要的核心 Skill：

| Skill | 用途 |
|---|---|
| `wechat-skill` | 根 Skill：已有文章排版、HTML 校验、多账号草稿上传 |
| `wechat-tech-insight-writer` | 科技、AI、产业、企业和民生深度写作 |
| `wechat-content-pipeline` | 按用户 brief 编排写作、humanize、配图、封面、排版并创建草稿（默认不自动选题） |
| `wechat-public-event-archive` | 用户开启后自动核验中国重大公共事件并把合格选题交给主流水线 |
| `humanizer-zh` | 写后去 AI 味；声口服从 brief，正式报道保持克制 |
| `xiaohu-gen` | 可选脚本生图客户端；优先用 Agent 自带生图，否则用 AGNES_API_KEY |

`wechat-inline-visuals`、`wechat-html-cover`、`baoyu-cover-image` 位于 `optional-skills/`。它们不会被自动发现；主流水线只调用前两者的确定性脚本，并把 Baoyu 的设计维度压成小型运行策略，不加载三份完整 Skill。只有明确需要独立能力时才安装其中一个，见 [`optional-skills/README.md`](../optional-skills/README.md)。

## 2. 安装和加载

完整工具包应作为 Agent 工作区使用：

```bash
git clone https://github.com/843645440/wechat-skill.git
cd wechat-skill
```

确保云端 Agent 能读取根 `SKILL.md` 和 `.agents/skills/`。不要只复制根 Skill，否则写作、图片后端和完整工作流不会一起加载。默认部署无需安装 `optional-skills/`。

运行环境需要 Python 3。正文由固定渲染器生成公众号 HTML；默认封面/正文图走统一图片脚本（用户也可自备图）。创建草稿需要公众号 API 权限与 IP 白名单。默认不自动选题。

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

正式报道的流水线封面和单独使用 `wechat-html-cover` 时需要浏览器。没有浏览器会自动降级到 Pillow，不阻塞草稿。封面渲染器会自动查找 Chrome、Chromium 或 Playwright Chromium。只有自动发现失败时才设置：

```bash
export WECHAT_COVER_BROWSER='/path/to/chrome-or-chromium'
```

可以用仓库测试规格做一次离线封面渲染，不连接图片 API：

```bash
python3 optional-skills/wechat-html-cover/scripts/render_cover.py \
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

## 4. 完整工作流（用户命题）

提供主题与思路后，对 Agent 说：

> 使用 `$wechat-content-pipeline` 为 B 账号写一篇“AI 如何改变基层客服工作”的文章，思路：……，完成全部流程并发送到 B 账号草稿箱。

完整流程固定为：

1. 接收用户 brief（主题 + 思路，硬门禁；缺失则追问，不联网找题）。
2. `shape --auto` 按轮换计划自动锁定本篇结构（防同质，永不死锁；显式字段可覆盖）。
3. `begin` 验证 brief、`event_focus` 和结构后输出 `writing_contract` → 写作忠实 brief 的 `article.md`（1500—4000 字），建议补 `digest.txt` 摘要 → `check` 自检到 ok。普通观点稿可用账号强情感声口；公共事件档案覆盖为克制正式。
4. `humanizer-zh` 一轮去 AI 味，强度与声口服从 brief。
5. `choose-theme` 先固定主题；`build_inline_visuals.py` 为公共事件生成至多一张只引用正文原句的 HTML 事实脉络，普通稿默认为空。
6. `gen_inline_images.py --record-stage` 处理 0—3 张正文图（已有图优先；公共事件禁用 AI 图；其他题材仅在有生图能力或 `AGNES_API_KEY` 时生成）。
7. `gen_cover_image.py --record-stage` 写入封面：正式报道走准确标题 HTML，普通观点稿可脚本生图，再降级到 HTML、Pillow、账号默认素材。
8. `prepare` 对 humanize 后最终稿执行 score ≥75、blocking=0 的硬门禁并校验标题、字数、图数和路径；`finish` 发布前重检一次，随后排版并创建指定账号草稿。

云端 Agent 必须使用固定入口：`pipeline_job.py init/topic/history/shape/stage/show` 和 `pipeline_runtime.py begin/check/prepare/finish`。不得为某篇文章临时写排版脚本或视觉检测循环。`finish` 默认创建草稿；只有开发验证时才使用 `--dry-run`。

流水线不会公开发布；人工审核发生在微信公众号草稿箱。自动热点发现已默认关闭，仅当账号档案显式开启且用户要求时才可用。

## 5. 命题生产（推荐用法）

默认**不**自动发现热点。每次由你提供主题与大致思路，例如：

> 使用 `$wechat-content-pipeline` 为账号 a 写到草稿箱。  
> 主题：……  
> 思路：……（时间线/论点/必须写到/不要写……）  
> 配图：（可选）封面与正文图路径  

Agent 应落盘 `user-brief.md`，`--source provided`，不得自行换题。详见 `.agents/skills/wechat-content-pipeline/references/user-brief.md`。

若仍配置定时任务，任务内容必须是「处理收件箱里的用户 brief」或人工粘贴的主题，**不要**写「不指定选题，自动发现热点」。

## 6. 单独使用某项能力

只写文章：

> 使用 `$wechat-tech-insight-writer` 写一篇关于人形机器人进入汽车工厂的公众号文章。

只排版已有文章并自动提取信息模块：

> 使用 `$wechat-skill`，把 `article.md` 用橄榄手记主题排成公众号 HTML。

以下三项须先从 `optional-skills/` 安装对应目录。只生成原生信息模块并一次排好正文：

> 使用 `$wechat-inline-visuals`，从文章提取信息，并用当前主题的固定渲染器生成正文和原生 HTML 模块。

只生成稳定封面：

> 使用 `$wechat-html-cover`，根据最终标题和当前主题生成公众号封面。

封面模板可选 `signal-editorial`、`night-signal` 与 `redaction-poster`。三套模板拥有独立固定配色，不跟随正文主题，目前不按 A/B 账号写死；需要固定账号规则时再修改账号档案。

只有脱离流水线单独创作封面时才调用 `$baoyu-cover-image`。完整流水线不读取这些可选 Skill 的说明，但会复用 HTML 渲染/校验脚本与压缩后的封面设计维度。

## 7. 运行产物

每个账号只复用一个内部工作区：

```text
work/a/current/
work/b/current/
```

产物包括 `article.md`、`inline-visuals.json`、`imgs/`、`prompts/`、`cover/cover.png`、`article.html` 和 `draft-result.json`。每次 `init` 生成新的 `run_id`；同账号同日可多篇。微信草稿箱不受影响。

## 8. 常见阻塞

- **缺主题或思路**：流水线停止并追问，不联网找题凑稿。
- **最终稿体检未通过**：humanize 后仍须 score ≥75 且 blocking=0；按报错里的完整报告命令修稿，不补假数字刷分。
- **字数不在 1500—4000**：`prepare` 拒绝；补真实内容或删冗余，禁止注水。
- **正文图失败**：单图重试一次，仍失败则跳过；全部失败按无图文章继续，不阻塞草稿。
- **没有生图 API / 没有浏览器**：不是阻塞。运行统一封面命令，它会自动降级到 Pillow：

  ```bash
  python3 .agents/skills/wechat-content-pipeline/scripts/gen_cover_image.py \
    --job work/a/current/job.json --record-stage
  ```

  需要一款中文字体；都找不到时设置 `WECHAT_COVER_FONT=<字体文件绝对路径>`。
- **封面生成失败**：四档后端全不可用时，只有配置了账号默认 `thumb_media_id` 才能继续。
- **公众号接口报错**：检查接口权限、IP 白名单、AppID/AppSecret 和账号别名。
- **草稿结果不确定（timeout/EOF）**：标记 `uncertain`，人工核对草稿箱，不自动重发。
- **出现作者占位符**：流水线会阻止上传；填写真实作者或删除署名组件。
- **单独排版任务 HTML 校验失败**：运行 `python3 scripts/validate_gzh_html.py article.html`，修到 ERROR 和 WARNING 都为零（此校验用于根 Skill 手动排版；流水线内为轻量检查）。

开发或修改 Skill 后运行：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/component_lint.py .
```

## 9. 来源与许可

- 根排版组件、编排工作流、`optional-skills/wechat-inline-visuals` 与 `optional-skills/wechat-html-cover` 按仓库根 `LICENSE` 的 AGPL-3.0 使用。
- `baoyu-cover-image` 来源于 [JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills)，MIT 许可证保存在 `optional-skills/baoyu-cover-image/LICENSE`。
