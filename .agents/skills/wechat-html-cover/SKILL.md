---
name: wechat-html-cover
description: 使用受约束 JSON、固定 HTML/CSS 和 Chrome/Chromium 确定性生成微信公众号封面 PNG。用于完整公众号流水线必须提供 thumb_media_id，或需要准确中文标题、与正文当前排版主题一致且不调用图片模型的 1410×600 封面时；不生成正文图片。
---

# 微信公众号 HTML 封面

根据最终标题和本轮排版主题生成一张 1410×600 PNG。提供 `editorial-ledger` 与 `kinetic-type` 两套可切换模板；当前不在 Skill 内绑定账号。该 Skill 只负责封面，不分析或生成正文配图。

## 工作流

被 `wechat-content-pipeline` 调用时，不直接执行本页命令；由 `pipeline_runtime.py prepare/finish` 自动生成规格并渲染。以下命令只用于单独生成封面或维护模板。

1. 从任务状态取得已固定的主题标识，自动选择一套模板；同一任务恢复时沿用原模板。
2. 让固定脚本从最终 `article.md` 读取标题和合适的正文短句，自动拆分两行并生成合法重点词。不要让 Agent 手写或猜测 `title_lines`、`highlights`：

```bash
python3 <SKILL_ROOT>/scripts/build_cover_spec.py \
  --article <WORK_DIR>/article.md \
  --theme <SELECTED_THEME> --template <TEMPLATE> \
  --output <WORK_DIR>/cover/cover.spec.json
```

规格不通过时先修正最终文章标题；不得只缩短封面文字。详细限制见 [references/spec.md](references/spec.md)。

3. 运行一次截图：

```bash
python3 <SKILL_ROOT>/scripts/render_cover.py \
  --spec <WORK_DIR>/cover/cover.spec.json \
  --html-output <WORK_DIR>/cover/cover.html \
  --output <WORK_DIR>/cover/cover.png --timeout 45
```

4. 使用脚本返回的 PNG 签名和 1410×600 尺寸校验结果。成功即采用。

## 运行条件

需要 Python 3 和 Chrome/Chromium，不需要图片 API Key。脚本会自动查找常见浏览器；无法找到时设置 `WECHAT_COVER_BROWSER`。

## 硬性边界

- 只使用 `moyu-green`、`red-white`、`graphite-minimal`、`zen-whitespace`、`moyu-ticket`、`olive-journal` 六个已注册主题。
- 只使用 `editorial-ledger`、`kinetic-type` 两套注册模板；模板选择与账号映射由后续配置决定。
- 每张封面只渲染一次，浏览器硬超时 45 秒；超时会终止浏览器进程组并返回失败。浏览器技术故障允许同一命令重试一次，不创建 V2/V3。
- 不调用 Agnes、Baoyu 或任何生成式图片模型，不执行 AI 视觉检测。
- 不接受任意 HTML、JavaScript、远程字体、远程图片或外部 CSS。
- 封面失败时使用账号已有默认封面素材；两者都不可用才由草稿门禁阻止上传。
