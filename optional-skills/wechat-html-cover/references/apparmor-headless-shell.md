# AppArmor 与 headless_shell

封面探针报「浏览器内容探针执行失败」时优先查本节，而不是改模板。

## 根因

- `apparmor_restrict_unprivileged_userns=1` 时，非 root 完整 Chrome 无可用 sandbox 会 abort（`No usable sandbox`）。
- 旧逻辑若只在 root 加 `--no-sandbox`，普通用户必挂。
- 完整 Chrome for Testing 的 `--dump-dom` 在部分机器上会挂起不退出。

## 正确行为（`scripts/render_cover.py`）

1. 检测 AppArmor/userns（或 `WECHAT_COVER_NO_SANDBOX=1` / root）→ 附加 `--no-sandbox --disable-setuid-sandbox`。
2. 浏览器候选**优先** Playwright：
   `~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell`
3. 探针前创建独立 `user-data-dir` profile。
4. 失败错误信息带 stderr 片段。

## 复现

```bash
python3 .agents/skills/wechat-html-cover/scripts/render_cover.py \
  --spec work/<account>/current/cover/cover.spec.json \
  --output /tmp/cover-probe.png --timeout 45
```

期望：`status=ok`，PNG 1410×600，`browser` 路径含 headless_shell。

也见 pipeline 侧：`../wechat-content-pipeline/references/execution-recovery.md`、`session-lessons-cover-inline.md`。
