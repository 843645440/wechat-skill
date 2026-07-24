# 公众号草稿最终只读审计补充

用于复审草稿幂等状态机、dry-run 与不可逆微信 API 边界。与流水线内的 `pipeline-runtime-audit.md`、`draft-idempotency-and-path-safety.md` 一起使用。

## 审计范围必须稳定

1. 同时记录 unstaged、staged、untracked；普通 `git diff` 不包含未跟踪文件。若用户给定的固定哈希仅来自 `git diff --binary`，该哈希只绑定 tracked diff：必须逐个读取未跟踪文件，并在报告中准确说明哈希边界；需要“完整工作树哈希”时，另建包含 staged、unstaged、untracked 路径与字节的确定性清单再摘要，不能把普通 diff 哈希误称为完整工作树哈希。
2. 将完整 binary-safe diff 保存到系统临时目录并逐段读完，未跟踪文本逐个读取。
3. 报告前比较当前 diff 与已审快照；若审查期间变更，必须读取两份快照的 delta，并重跑受影响测试。
4. 定向探针只写系统临时目录，设置 `PYTHONDONTWRITEBYTECODE=1`；结束后重查 `git status` 和 `git diff --check`。

## 状态证据只能单调增强

不可逆草稿创建的关键不变量：任何辅助模式都不得擦除安全证据。

至少验证以下交叉组合：

- 前态：`running`、`failed + uncertain`、`completed`；
- 后续模式：正式执行、dry-run、skip；
- 再下一次：正式执行。

特别验证：

- `running → dry-run/skip → 正式执行` 仍必须阻断，不得因中间步骤变成可重试状态；
- `completed → dry-run/skip → 正式执行` 仍应复用完成结果，辅助验证不得覆盖 completed 指纹；
- dry-run、skip、状态查看、确定性重建都不得把 `running`/`uncertain`/可复用 `completed` 降级为普通 `skipped` 或 `pending`；
- 正式请求前的 running 落盘失败必须保证零请求；请求后的超时、EOF、连接重置、响应解析失败、结果文件落盘失败、最终 completed 落盘失败都只能单次，并进入 uncertain；
- 缺少目标 AppID 摘要时也要保留 `running`、输入指纹、attempt/outcome/retry-safe 等阻断证据。

通过“completed 直接复用”单测并不够：还要在 completed 与下一次正式调用之间插入 dry-run/skip；通过“正式模式拒绝 running”单测也不够：还要检查辅助模式能否洗掉 running。

## 图片与热点的负向探针

- 图片：除大小、路径和任意 magic bytes 外，验证扩展名/响应 MIME 与真实格式一致。不要只构造“单独文件头”这种容易通过的负例；还要构造**结构表面自洽但实际不可解码**的样本：无 IDAT 的伪 PNG、仅 SOI/EOI 的 JPEG、只有图像分隔字节与 trailer 的 GIF、空 VP8/VP8L chunk 的 WebP。四种格式都应验证必要结构，优先调用可靠解码器的 verify 路径；绿色测试不能推翻最小对抗样本已经复现的放行。
- dry-run：外部图片必须在任何网络调用前拒绝，并用 mock 断言微信 API 调用数为零。
- 热点：不要只测 topic 写入门禁；伪造或编辑已保存 job，在 prepare、独立 gate、finish 重测 sources、发布时间、分类、affected group，并验证证据随时间过期后会被阻断。尤其检查 `completed` 的快速恢复分支：它常在 `require_content`/gate 之前返回，可能让已过期热点在 finish 被直接复用。修复时应先重查热点，再复用 completed，同时保持 completed 状态不被失败的辅助检查覆盖。

## 输出安全

探针与报告只输出状态、布尔值、调用次数和脱敏规则名；不输出凭据值或远端草稿结果标识。