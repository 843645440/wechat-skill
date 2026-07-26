# 流水线幂等、失败不确定性与路径安全

维护 `pipeline_job.py`、`pipeline_runtime.py` 或 `wechat_publish.py` 时使用本页。目标是避免“网络失败后重复草稿”和工作清单路径逃逸。

> 本页描述**当前简化契约**（2026-07-22 起）：幂等边界是 `run_id`，不存在 `sources.md`、预览、leaf count、输入指纹或文件哈希 checkpoint。历史的指纹方案见 git 历史，不要按旧契约恢复。

## 草稿幂等边界 = `run_id`

- 每次 `init` 生成新的随机 `run_id` 并写入 `job.json`。
- 同一 `run_id` 已有成功且非空 `draft_media_id` 的结果时，`finish` 直接返回原结果，不再次调用 `draft/add`。复用前核对：账号、`action==draft`、`run_id`、`draft_media_id` 全匹配。
- 新 `run_id` 即新文章任务：同账号同一天允许继续创建草稿，不按日期拦截。
- 不使用正文、HTML、图片或封面的文件哈希判断是否重复。

## `draft/add` 是非幂等调用

创建草稿后若客户端在读取响应时 timeout、EOF 或 connection reset，无法判断微信是否已接收。此时：

1. 只调用一次，不自动重放 POST；
2. 将 draft 标为 `failed`，detail 记录 `outcome=uncertain`、`retry_safe=false`；
3. 后续自动续跑必须停止，要求人工核对微信草稿箱；
4. 核对后由操作者显式将 draft 重置为 `pending`，重置时清理旧 details；
5. 结果文件写入失败同样视为 uncertain，因为 API 可能已成功。

本地 dry-run preflight 失败不产生草稿，可标记为安全重试，但不得与正式调用混为一类。正式模式中，缺少 AppID/AppSecret、目标账号不存在、账号缺 `appid_env`/`secret_env` 等、能确定发生在 HTTP 请求前的错误统一记录为 `preflight-failed`、`retry_safe=true`；分类测试应使用发布器真实错误文本，而不是自造一条过宽正则。只有无法证明请求尚未发送的错误才进入 uncertain。

### `running` 也是不确定状态

正式调用前必须先落盘 `draft=running` 再发送 POST。进程若在请求发送后、结果落盘前退出，后续 `finish` 看到遗留 `running` 时不得继续发布；应转为 `failed/uncertain` 并要求人工对账。

即使发现 `draft-result.json`，也只有在结果结构、账号、动作、`run_id` 与非空 media_id 全部可验证时才能协调为 completed；否则仍按 uncertain 处理。

### `init` 不得擦除防重证据

同账号 `current/` 中任一阶段为 `running` 或 `failed`，尤其 draft 为 uncertain 时，普通 `init` 必须拒绝删除工作区。需要整轮重来时使用明确的危险参数（`--force-new`），并在执行前由操作者承担远端草稿对账责任。不要让“新任务覆盖旧临时目录”的便利性高于非幂等操作的审计证据。

`finish` 对同一任务加文件锁，防止两个并发调用同时进入 `draft/add`。

## 状态与失败落盘

- 状态汇总应先检查任意阶段 `failed`，再判断 drafted 等成功终态。
- prepare 的标题、字数（1500—4000）、配图数量（≤3）或路径门禁失败必须落盘，保存 `phase=prepare` 和错误摘要。
- 不要只测正常恢复；必须覆盖“响应不确定”“落盘失败”和“成功状态后出现后续失败”。

## 路径信任边界

任务清单是数据，不是可信执行配置：

- 以真实 `job.json` 所在目录作为工作区根，并校验清单中的 `job_dir` 与之相同；
- artifact 使用 `realpath` 后校验仍位于工作区，拒绝绝对路径、`..` 和指向目录外的软链接；
- 内部脚本根目录从当前 Skill 安装位置推导，不从可修改的 job manifest 读取；
- HTML 中本地正文图片必须位于 HTML 目录内，拒绝 `file://`、绝对越界路径、`../` 和软链接逃逸；
- 显式封面路径可以有独立策略，但不能因此放宽正文图片边界。

## 图片处理（可降级，非门禁）

- 正文图允许 0—3 张；引用文件缺失时删除该引用继续，不阻塞草稿。
- 上传前按文件真实字节识别图片类型（PNG/JPEG/GIF/WebP），据此设置 MIME 与规范化上传文件名；扩展名与真实类型不一致不是失败条件。
- 无法识别或微信不接受的正文图：删除该图引用后继续；没有可用正文图时按无图文章继续。
- 单张图超限跳过该图，不阻塞整篇草稿。
- local 与 HTTP 图片都应使用同一最大字节数做有界读取；不得先无界读入内存再检查大小。
- 上述降级只针对正文配图；封面必须可解码有效，失败只允许回退到账号默认 `thumb_media_id`。

## 最小回归集合

1. 同一 `run_id` 已成功时再次 `finish`：返回原 `draft_media_id`，`draft/add` 调用次数为 0。
2. 新 `run_id` 同账号同日可继续创建草稿；不存在日期级拦截。
3. `draft/add` timeout、EOF、connection reset、响应字段不完整和结果落盘失败分别验证：发布调用次数严格为 1，再次 finish 被 uncertain 门禁阻止。
4. 遗留 `draft=running` 在任何发布前转为 uncertain；缺少旧版 details 也不得自动续发。
5. 普通 `init` 拒绝删除 running/failed/uncertain 工作区；只有显式 force 路径可清理。
6. prepare 失败持久化，且全局 state 为 failed。
7. artifact 绝对路径、工作目录软链接、HTML `../` 和软链接图片被拒绝。
8. 伪扩展名图片按真实格式上传；损坏图被跳过且其余正文继续；0 图草稿可创建。
9. dry-run 对网络调用设置 tripwire，证明无微信外联。
