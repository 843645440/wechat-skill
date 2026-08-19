# 封面生成与降级

流水线封面的唯一入口是：

```bash
python3 <PIPELINE>/scripts/gen_cover_image.py --job <job.json> --record-stage
```

不要由 Agent 临场选择后端、手写提示词或补记阶段。脚本从最终 `article.md` 读取标题，
把封面写入 `work/<account>/current/cover/cover.png`，并自动记录 `cover` 阶段。

## 自适应路由与降级链

| 顺序 | 条件 | 结果 |
|---|---|---|
| 1 | `cover/cover.png` 已存在 | 原样保留，`backend=user_provided` |
| 2 | 公共事件档案、枪击/伤亡/案件等正式报道 | HTML 准确排标题，`backend=html_render`；不生成现场插画 |
| 3 | 普通观点稿且策略允许生图 | 按类型/色板/渲染/情绪维度生成无文字 2.35:1 主视觉，`backend=image_generate` |
| 4 | 生图失败或策略禁用生图 | 再试准确标题 HTML；失败后 Pillow，`backend=offline_render` |
| 5 | 前四档失败，但账号已有默认素材 | `finish` 使用账号 `thumb_media_id` |
| 6 | 全部不可用 | `cover=failed`，停止草稿创建 |

正文图可以没有，封面不能没有。无 Key、网络超时或生成响应异常不是工作流故障；脚本会把
`generate_failed_because` 写入结果并自动尝试离线渲染。只有离线渲染也失败且账号无默认素材时
才需要人工处理。

## 策略与参数

- `config/wechat-content-profiles.json` 的 `cover.backend=adaptive`：正式题材走 HTML，普通观点稿走艺术指导生图。
- `cover.backend=offline_render`：跳过生图，优先 HTML，再用 Pillow。
- `cover.backend=image_generate`：非正式题材先调用
  `.agents/skills/xiaohu-gen/scripts/agnes_generate.py`，固定 2.35:1，再离线兜底；正式题材仍禁止 AI 现场插画。
- 用户明确要求跳过生图时，可给命令加 `--skip-generate`。
- 离线字体自动查找 PingFang、冬青黑、华文黑体和 Noto CJK；都没有时设置
  `WECHAT_COVER_FONT=<字体文件绝对路径>`。

## 品牌与视觉边界

- 普通观点稿用 Baoyu 式设计维度（类型、色板、渲染、风格、情绪）生成艺术指导；运行时不读取整份可选 Skill。
- AI 主视觉不生成任何文字、数字、Logo、水印或签名，避免乱码标题；文章标题由公众号卡片显示。
- 正式报道封面必须准确排出最终一级标题，不使用案发现场想象图。
- 不做成容易误认成官方发布会海报的样式，不放长段文字、水印或签名。
- 不做 Agent 视觉/OCR 循环；`finish` 只做文件存在、魔数与上传可用性检查，观感在草稿箱人工核对。

故障处理见 [pipeline-failure-triage.md](pipeline-failure-triage.md)。
