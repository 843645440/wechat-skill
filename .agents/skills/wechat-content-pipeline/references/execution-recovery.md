# 流水线失败收敛与恢复

用于公众号完整流水线遇到代码更新冲突、确定性封面渲染失败或外部 API 瞬时错误时。目标是保留产物、快速定位、限制重试，不把单个阶段演变成循环。

## 代码更新遇到本地改动

1. 先查看工作树，区分已跟踪改动与来源不明的未跟踪文件。
2. 只暂存会阻挡 `pull --ff-only` 的已跟踪文件，不把无关未跟踪文件放入 stash，也不删除它们。
3. 拉取远端后恢复 stash。若流水线说明发生冲突，以新版结构为主体，再人工重放仍适用的本地安全规则。
4. 运行仓库测试和组件检查后再启动新任务。

示例：

```bash
git stash push -m 'preserve-local-pipeline-guards' -- <tracked-file>
git pull --ff-only
git stash pop
```

## 标题与封面规格

在正文、HTML和封面生成前先验证最终标题是否满足封面规格：

- `title` 不超过模板限制。
- `title_lines` 拼接后与 `title` 完全一致。
- 每行不超过模板限制。
- 高亮词位于对应标题行，且不超过字段限制。

若必须改标题，同步更新 `article.md` 一级标题、`cover.spec.json`、草稿命令的 `--title`，然后重跑相关机械校验。不得只改封面标题造成草稿标题、正文记录和封面不一致。

## Chromium/Playwright 兼容

确定性 HTML 封面找不到系统 Chrome 时，优先检查 Playwright 缓存。新版 Chrome for Testing 常见路径为：

```text
~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
```

渲染器应同时搜索 `chrome-linux/chrome` 和 `chrome-linux64/chrome`。也可用 `--browser <absolute-path>` 或 `WECHAT_COVER_BROWSER` 显式指定。先运行浏览器 `--version`，再用同一 HTML 做一次最小 headless 截图，确认浏览器本身可用。

不要把浏览器发现问题改写成“浏览器不可用”的长期结论。修复候选路径或显式设置路径，并保留 PNG 签名与精确尺寸校验。

## 重试边界

- 正文原生 HTML 模块：计划校验失败时按错误修字段，不重复生成整篇文章。
- 确定性封面：不调用 AI 视觉检测，不做审美重绘，不回退生成式图片。
- 浏览器渲染：原命令最多重试一次；随后进入诊断，而不是继续盲重试。
- 微信草稿 API：瞬时 TLS EOF、连接重置、超时或 5xx 最多重试一次；成功后立刻停止。
- 每个阶段只有产物真实存在且机械校验通过后，才能标记 `completed`。

## 最终一致性检查

草稿创建后读取结果文件并确认：

- `account` 是目标账号别名。
- `action` 是 `draft`。
- `draft_media_id` 非空。
- 流水线状态为 `drafted`。
- 未调用公开发布接口。
