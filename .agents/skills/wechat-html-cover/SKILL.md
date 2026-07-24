---
name: wechat-html-cover
description: 使用受约束 JSON、固定 HTML/CSS 和 Chrome/Chromium 确定性生成微信公众号封面 PNG。用于完整公众号流水线必须提供 thumb_media_id，或需要准确中文标题、独立封面视觉且不调用图片模型的 1410×600 封面时；不生成正文图片。
---

# 微信公众号 HTML 封面

根据最终标题生成一张 1410×600 PNG。提供 `signal-editorial`、`night-signal` 与 `redaction-poster` 三套独立于正文主题的可切换模板；当前不在 Skill 内绑定账号。该 Skill 只负责封面，不分析或生成正文配图。

## 工作流

被 `wechat-content-pipeline` 调用时，不直接执行本页命令；由 `pipeline_runtime.py prepare/finish` 自动生成规格并渲染。以下命令只用于单独生成封面或维护模板。

1. 自动选择一套模板；正文主题标识只保留在规格中用于追踪，不控制封面配色。同一任务恢复时沿用原模板。
2. 让固定脚本从最终 `article.md` 读取标题和合适的正文短句，自动拆分为两行或三行，并生成合法重点词。不要让 Agent 手写或猜测 `title_lines`、`highlights`：

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

4. 使用脚本返回的调色板对比度、PNG 签名和 1410×600 尺寸校验结果做技术门禁；这些结果不代表标题已经可读。随后检查实际像素，逐字确认标题无粘连、重叠、裁切或乱码，并确认缩略图尺度仍可辨认。中文标题出现笔画膨胀或多模板共同粘连时，按 [references/cjk-title-legibility.md](references/cjk-title-legibility.md) 做封面单测与受控收敛。两类门禁都通过后才采用。

## 运行条件

需要 Python 3 和 Chrome/Chromium，不需要图片 API Key。脚本会自动查找常见浏览器；无法找到时设置 `WECHAT_COVER_BROWSER`。AppArmor / headless_shell 探针失败见 [references/apparmor-headless-shell.md](references/apparmor-headless-shell.md)。

### Snap/Chromium 陷阱

- **不得对浏览器路径调用 `resolve()`**。`/snap/bin/chromium` 解析后变成 `/usr/bin/snap`，后者不接受 `--headless` 参数。脚本保留原始可执行入口。
- **Snap 无法可靠读写隐藏目录**（如 `~/.hermes/...`）。不要围绕沙箱问题叠加 HTTP 服务、浏览器替换或多轮临时方案；先采用最小路径：在 `$HOME` 下创建普通非隐藏暂存目录，把输入 HTML、浏览器 profile 和输出 PNG 全部放进去，成功后再把 PNG 原子移动回工作区。具体复现与验证见 [references/snap-staging-and-cover-verification.md](references/snap-staging-and-cover-verification.md)。
- **先做最小真实验证，再修改主脚本**：用同一个浏览器入口、同一份 HTML，在非隐藏目录执行一次截图；只有确认真实 PNG 可读后才固化实现，避免把路径、浏览器和网络问题混在一起排查。
- **PNG 尺寸正确不等于内容正确**。任何封面上传前都必须检查实际像素内容，确认不是 `ERR_ACCESS_DENIED`、`ERR_FILE_NOT_FOUND`、空白页或其他浏览器错误页，并确认标题完整、无乱码、无裁切溢出。只检查文件存在、字节数、PNG 签名或 1410×600 尺寸，不得报告成功。
- **失败封面不得上传**。内容未核验时停止在本地；已有有效兜底素材时使用账号默认封面，否则由草稿门禁阻止上传。

## 硬性边界

- 只使用 `moyu-green`、`red-white`、`graphite-minimal`、`zen-whitespace`、`moyu-ticket`、`olive-journal` 六个已注册主题。
- 只使用 `signal-editorial`、`night-signal`、`redaction-poster` 三套注册模板；模板选择与账号映射由后续配置决定。
- 标题必须完全位于单一高对比底色的安全区；装饰不得穿过、覆盖或裁切文字。
- 每张封面只渲染一次，浏览器硬超时 45 秒；超时会终止浏览器进程组并返回失败。浏览器技术故障允许同一命令重试一次，不创建 V2/V3。
- 不调用 Agnes、Baoyu 或任何生成式图片模型，不执行 AI 视觉检测。
- 不接受任意 HTML、JavaScript、远程字体、远程图片或外部 CSS。
- 封面失败时使用账号已有默认封面素材；两者都不可用才由草稿门禁阻止上传。
