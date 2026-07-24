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

在正文 HTML 生成前运行 `build_cover_spec.py --article ...`，自动验证最终标题：

- `title` 不超过模板限制。
- `title_lines` 拼接后与 `title` 完全一致。
- 每行不超过模板限制。
- 高亮词由脚本自动生成并位于合法标题行。

Agent 不手写分行或高亮。若标题超过 32 字，只修改一次 `article.md` 一级标题，再重新生成规格；草稿命令从同一标题读取，不得只改封面。

## Chromium/Playwright 兼容

确定性 HTML 封面找不到系统 Chrome 时，优先检查 Playwright 缓存。优先使用 headless_shell，再回退完整 Chrome for Testing：

```text
~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell
~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
```

渲染器应同时搜索 `chrome-linux/chrome`、`chrome-linux64/chrome` 以及 `chromium_headless_shell` 路径。也可用 `--browser <absolute-path>` 或 `WECHAT_COVER_BROWSER` 显式指定。先运行浏览器 `--version`，再用同一 HTML 做一次最小 headless 截图，确认浏览器本身可用。

**AppArmor / 无沙箱环境**：Ubuntu 23.10+ 若启用 `apparmor_restrict_unprivileged_userns`，非 root 下完整 Chrome 会直接以 `No usable sandbox` 中止，探针报“浏览器内容探针执行失败”。渲染器在检测到该限制（或 `WECHAT_COVER_NO_SANDBOX=1`、root）时必须自动附加 `--no-sandbox --disable-setuid-sandbox`。不要把这类环境问题当成封面模板错误。

**优先 headless_shell**：在部分服务器上完整 Chrome for Testing 的 `--dump-dom` 可能挂起不退出，而 Playwright 的 `chrome-headless-shell` 能稳定完成内容探针与截图。候选浏览器顺序应把 headless_shell 放在完整 Chrome 之前。

**Snap 启动器路径陷阱**：`/snap/bin/chromium` 是 Snap 包装脚本，`Path.resolve()` 会将其解析为 `/usr/bin/snap`，而 `snap` 命令不接受 `--headless` 参数。修复方式：使用 `Path.absolute()` 而非 `Path.resolve()` 保留原始启动器路径。

若使用 Snap 安装的 Chromium，浏览器可能能读取 `file://` HTML，却不能把 `--screenshot` 直接写入点目录下的任务路径（如 `~/.hermes/...`）。最小截图显示“已写入”但目标文件不存在时，不要继续重试渲染器：先把截图输出到 `/home/<user>/cover-staging.png` 这类 Snap 可写路径，校验 PNG 签名与 1410×600 尺寸，再复制到任务的 `cover/cover.png`。复制后再次机械校验目标文件。

**浏览器退出竞态**：Chromium 可能在退出后才完成 PNG 写入。轮询逻辑在检测到进程退出后应立即再次检查 PNG 文件，而不是等待超时。如果 PNG 在进程退出后立即出现且尺寸正确，应视为成功。

不要把浏览器发现问题改写成“浏览器不可用”的长期结论。修复候选路径或显式设置路径，并保留 PNG 签名与精确尺寸校验。

## 默认封面与阶段状态校验

- 只有发布配置中真实存在非空 `thumb_media_id`，才可记录 `default_thumb_media_id=true`。账号别名存在、凭证可用或门禁暂时放行，都不能证明默认封面已配置。
- 封面渲染失败时，应先读取发布配置验证默认封面；无法验证就记录 `false`，让门禁阻止草稿创建，不能凭假设推进。
- `pipeline_job.py stage` 可能合并而不是清空旧 `details`。阶段从 `skipped` 恢复为 `completed` 后，要检查 `show` 输出，避免残留的 `default_thumb_media_id=true` 与新生成的 `cover.png` 同时存在。最终状态只保留与实际发布路径一致的信息。
- 在调用微信 API 前，做与发布脚本一致的封面预检：要么 `--cover` 指向已校验 PNG，要么账号配置确有默认 `thumb_media_id`。门禁通过不能替代这一步。

## 重试边界

- 正文原生 HTML 模块：只生成一次计划。校验或插入失败时立即覆盖为当前主题空计划，以纯正文继续；不修字段、不再生成、不重试。
- 封面：生图 API 产物；不调用 AI 视觉检测，不做审美重绘；HTML 封面已停用。
- 浏览器渲染：单次硬超时 45 秒；超时或技术故障时原命令最多重试一次，随后使用默认封面或由门禁停止。
- 微信草稿 API：瞬时 TLS EOF、连接重置、超时或 5xx 最多重试一次；成功后立刻停止。
- 每个阶段只有产物真实存在且机械校验通过后，才能标记 `completed`。

## 最终一致性检查

草稿创建后读取结果文件并确认：

- `account` 是目标账号别名。
- `action` 是 `draft`。
- `draft_media_id` 非空。
- 流水线状态为 `drafted`。
- 未调用公开发布接口。
