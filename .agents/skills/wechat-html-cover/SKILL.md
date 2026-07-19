---
name: wechat-html-cover
description: 使用受约束 JSON、固定 HTML/CSS 和 Chrome/Chromium 确定性生成微信公众号封面 PNG。用于完整公众号流水线必须提供 thumb_media_id，或需要准确中文标题、与正文当前排版主题一致且不调用图片模型的 1410×600 封面时；不生成正文图片。
---

# 微信公众号 HTML 封面

根据最终标题和本轮排版主题生成一张 1410×600 PNG。提供 `editorial-ledger` 与 `kinetic-type` 两套可切换模板；当前不在 Skill 内绑定账号。该 Skill 只负责封面，不分析或生成正文配图。

## 工作流

1. 从最终 `article.md` 取得标题；从任务状态取得已固定的主题标识。
2. 按 [references/spec.md](references/spec.md) 写 `cover/cover.spec.json`，明确模板、两行标题和重点词，不新增事实或宣传口号。
3. 运行：

```bash
python3 <SKILL_ROOT>/scripts/render_cover.py \
  --spec <WORK_DIR>/cover/cover.spec.json \
  --html-output <WORK_DIR>/cover/cover.html \
  --output <WORK_DIR>/cover/cover.png
```

4. 使用脚本返回的 PNG 签名和 1410×600 尺寸校验结果。成功即采用。

## 运行条件

需要 Python 3 和 Chrome/Chromium，不需要图片 API Key。脚本会自动查找常见浏览器；无法找到时设置 `WECHAT_COVER_BROWSER`。

## 硬性边界

- 只使用 `moyu-green`、`red-white`、`graphite-minimal`、`zen-whitespace`、`moyu-ticket`、`olive-journal` 六个已注册主题。
- 只使用 `editorial-ledger`、`kinetic-type` 两套注册模板；模板选择与账号映射由后续配置决定。
- 每张封面只渲染一次。浏览器进程失败时允许同一命令技术性重试一次，不创建 V2/V3。
- 不调用 Agnes、Baoyu 或任何生成式图片模型，不执行 AI 视觉检测。
- 不接受任意 HTML、JavaScript、远程字体、远程图片或外部 CSS。
- 封面失败时使用账号已有默认封面素材；两者都不可用才由草稿门禁阻止上传。
