# 封面（品牌可识别 · 无完整商标图）

流水线**不再调用** `wechat-html-cover` / Chrome 截图。封面由 Agent 在 `prepare` 前写入：

```text
work/<account>/current/cover/cover.png
```

（可为 PNG/JPEG/WebP 字节；扩展名可仍用 `cover.png`，finish 按魔数识别。）

## 后端降级链（按顺序取第一个可用的，不要卡住）

| 顺序 | 后端 | 前置条件 | 记账 detail |
|---|---|---|---|
| 1 | 用户提供的封面图 | brief 给了封面路径 | `backend=user_provided` |
| 2 | 生图 API（Agnes / 当前 runtime 的 image_generate） | 有 `AGNES_API_KEY` 或 runtime 自带生图 | `backend=image_generate` |
| 3 | **离线兜底渲染**（本仓库自带，纯 Pillow） | 有 Python + 一款中文字体 | `backend=offline_render` |
| 4 | 账号默认 `thumb_media_id` | 配了 `WECHAT_<X>_THUMB_MEDIA_ID` | `backend=account_default` |

**没有生图能力不是阻塞理由。** 运行环境没有 `AGNES_API_KEY`、也没有可用浏览器时，直接走第 3 档：

```bash
python3 <PIPELINE_ROOT>/scripts/render_cover_fallback.py \
  --title "<封面文案，可比标题更短；`|` 强制换行>" \
  --highlight "<要用强调色的片段，如 26万>" \
  --subtitle "<可选，一句副标>" \
  --kicker "<账号名>" \
  --seed "<run_id>" \
  --output <WORK_DIR>/cover/cover.png
```

- 输出 1440×810 PNG，配色由 `--seed` 确定（同 run_id 可复跑、连续多篇不撞色）。
- 字体自动查找 PingFang / 冬青黑 / 华文黑体 / Noto CJK；都没有时报错并提示设置 `WECHAT_COVER_FONT`。
- `--dry-run` 只检查字体与参数，不写文件。
- 它遵守同一条品牌规则：**只排文字与色块，不画任何商标图形**。

`pipeline_runtime.py check` 在封面缺失时会直接把这条命令拼好放进 `hints`，照抄执行即可。

## 在流水线中的位置

```text
write → humanize → illustrations(baoyu分析+自有后端出图) → cover(生图) → prepare → finish
```

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name cover --status running

# 走降级链取第一个可用后端；生图时提示词写入 prompts/cover.txt，输出 cover/cover.png

python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name cover --status completed \
  --detail 'backend=<image_generate|offline_render|user_provided>;brand=<主体名>;visual_check=none'
```

## 不做视觉校验（硬）

- **禁止**多模态看图、Read 图片、OCR、审美重跑。  
- 观感以**用户草稿箱人工核对**为准。  
- `finish` 只做：存在 / 非空 / 魔数可识别。

## 品牌识别策略（默认 · 稳妥）

目标：一眼知道「在讲谁」，又降低商标侵权与山寨 Logo 风险。

### 必须有（主识别）

1. **品牌/产品名文字**清晰入画（如 `Kimi`、`Microsoft`、中文「微软」二选一或并列），字号足够封面缩略可辨。  
2. **品牌色/气质色**占主色（如微软四色块感觉、科技青、厂商常用色），形成记忆点。  
3. **文章张力场景**作辅视觉（榜单融化、合同章、焊点、服务器等），服务本篇判断，不是无关风景。

### 禁止（默认）

1. **完整官方 Logo / 注册商标图形**的高清复刻（含「画得像官方的 K 标、四色窗标准图」）。  
2. 做成**官方发布会海报**误导样式（像厂商官号）。  
3. 无主体名、只靠抽象电路——读者不知道在讲谁。

### 例外（仅当）

- 用户明确要求且自担风险；或  
- 使用**官方新闻图/授权素材包**路径（非 AI 瞎画商标）。  

否则一律走「名 + 色 + 场景」。

## 提示词骨架

```text
Wide 16:9 WeChat article cover, modern editorial magazine.
PRIMARY ID: large clean wordmark text "<BrandOrProductName>" (legible, not a trademark logo glyph).
BRAND COLORS: <e.g. Microsoft-like red green blue yellow blocks as abstract color tiles / Kimi cool blue-purple gradient>.
SCENE (secondary): <one tension metaphor from the article, e.g. melting leaderboard vs solid factory checklist>.
Mood: <felt_sense>.
NO official trademark logos, NO fake seals of endorsement, NO long Chinese paragraph text.
High contrast, thumbnail-readable brand name.
```

示例（Kimi 榜单文）：

```text
Wide 16:9 cover. Large wordmark "Kimi" top-left. Cool blue-purple tech palette.
Secondary: abstract glowing scoreboard bars melting while a solid clipboard checklist stays sharp in foreground.
No Kimi official logo mark, no Anthropic logo. Editorial, tense, clean.
```

## 与正文图

- 封面：品牌可识别 + 情绪/张力。  
- 正文图：机制/流程/对比（走 baoyu 分析 + 自有后端出图），不重复封面构图。  
