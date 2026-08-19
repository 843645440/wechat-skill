# 封面生成与降级

流水线封面的唯一入口是：

```bash
python3 <PIPELINE>/scripts/gen_cover_image.py --job <job.json> --record-stage
```

不要由 Agent 临场选择后端、手写提示词或补记阶段。脚本从最终 `article.md` 读取标题，
把封面写入 `work/<account>/current/cover/cover.png`，并自动记录 `cover` 阶段。

## 固定降级链

| 顺序 | 条件 | 结果 |
|---|---|---|
| 1 | `cover/cover.png` 已存在 | 原样保留，`backend=user_provided` |
| 2 | `cover.backend=image_generate` 且 Agnes 可用 | 走 `xiaohu:agnes`，`backend=image_generate` |
| 3 | 生图失败，或策略为 `offline_render` | Pillow 确定性渲染，`backend=offline_render` |
| 4 | 前三档失败，但账号已有默认素材 | `finish` 使用账号 `thumb_media_id` |
| 5 | 全部不可用 | `cover=failed`，停止草稿创建 |

正文图可以没有，封面不能没有。无 Key、网络超时或生成响应异常不是工作流故障；脚本会把
`generate_failed_because` 写入结果并自动尝试离线渲染。只有离线渲染也失败且账号无默认素材时
才需要人工处理。

## 策略与参数

- `config/wechat-content-profiles.json` 的 `cover.backend=offline_render`：直接跳过生图。
- `cover.backend=image_generate`：先调用
  `.agents/skills/xiaohu-gen/scripts/agnes_generate.py`，默认 16:9，再离线兜底。
- 用户明确要求跳过生图时，可给命令加 `--skip-generate`。
- 离线字体自动查找 PingFang、冬青黑、华文黑体和 Noto CJK；都没有时设置
  `WECHAT_COVER_FONT=<字体文件绝对路径>`。

## 品牌与视觉边界

- 用主体名、品牌色和一个服务文章张力的场景建立识别，不复刻完整官方 Logo。
- 不做成容易误认成官方发布会海报的样式，不放长段文字、水印或签名。
- 不做 Agent 视觉/OCR 循环；`finish` 只做文件存在、魔数与上传可用性检查，观感在草稿箱人工核对。

故障处理见 [pipeline-failure-triage.md](pipeline-failure-triage.md)。
