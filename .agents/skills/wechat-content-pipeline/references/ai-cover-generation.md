# 生图 API 封面（品牌可识别 · 无完整商标图）

流水线**不再调用** `wechat-html-cover` / Chrome 截图。封面由 Agent 在 `prepare` 前用**当前环境生图能力**生成，写入：

```text
work/<account>/current/cover/cover.png
```

（可为 PNG/JPEG/WebP 字节；扩展名可仍用 `cover.png`，finish 按魔数识别。）

## 在流水线中的位置

```text
write → humanize → illustrations(baoyu分析+自有后端出图) → cover(生图) → prepare → finish
```

```bash
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name cover --status running

# 生图后端：当前 runtime 可用的 image_generate / Imagine / Agnes 等
# 提示词写入 prompts/cover.txt；输出 cover/cover.png

python3 <PIPELINE_ROOT>/scripts/pipeline_job.py stage \
  --job <WORK_DIR>/job.json --name cover --status completed \
  --detail 'backend=image_generate;brand=<主体名>;visual_check=none'
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
