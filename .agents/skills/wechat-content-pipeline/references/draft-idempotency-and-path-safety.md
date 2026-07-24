# 流水线幂等、失败不确定性与路径安全

维护 `pipeline_job.py`、`pipeline_runtime.py` 或 `wechat_publish.py` 时使用本页。目标是避免“恢复成功但内容已变”“网络失败后重复草稿”和工作清单路径逃逸。

## 草稿复用必须绑定发布输入

不得仅凭 `draft.status=completed`、结果文件存在或非空 `draft_media_id` 恢复。草稿 checkpoint 应保存发布输入指纹，并在恢复前重新计算。指纹至少覆盖：

- account、topic、discover 证据与已固定主题；
- `article.md`、`sources.md`、`article.html`；
- Markdown 正文图片的路径和文件内容；
- 封面输入必须按阶段的实际发布模式绑定：`cover=completed` 时包含本地封面及规格；`cover=skipped` 时忽略可能残留的旧文件，改为绑定实际使用的默认封面身份（只保存哈希，不落明文）；
- **目标账号实际生效的发布字段和目标 AppID 的安全摘要**，不得哈希整个多账号配置文件：修改无关账号、缓存目录等不能使当前账号 checkpoint 失效；
- 已有 `cover=completed` 的本地专属封面时，未使用的默认封面环境变量不得影响恢复指纹。

目标 AppID 摘要应在首次正式尝试前写入阶段 details。后续恢复进程如果暂时没有凭据，可沿用已记录摘要验证原 checkpoint；如果当前显式 AppID 与记录不一致，则必须失效。AppSecret 不决定草稿目标，不进入输入指纹，也不得落盘。

任一实际输入变化都必须使旧草稿失效。测试至少分别改变正文、来源、图片、目标 AppID 和目标账号发布字段；另要改变无关账号配置，证明其不会错误失效。

### 恢复检查必须做两次

第一次在重建产物前检查，命中时避免昂贵渲染；第二次必须在 HTML、封面等确定性产物修复后、调用 `draft/add` 前重新计算最终指纹。短暂损坏的产物可能被重建为与原发布输入完全相同的字节；如果省略第二次检查，就会为相同输入创建第二份草稿。

## `draft/add` 是非幂等调用

创建草稿后若客户端在读取响应时 timeout、EOF 或 connection reset，无法判断微信是否已接收。此时：

1. 只调用一次，不自动重放 POST；
2. 将 draft 标为 `failed`，detail 记录 `outcome=uncertain`、`retry_safe=false`；
3. 后续自动续跑必须停止，要求人工核对微信草稿箱；
4. 核对后由操作者显式将 draft 重置为 `pending`，重置时清理旧 details；
5. 结果文件写入失败同样视为 uncertain，因为 API 可能已成功。

本地 dry-run preflight 失败不产生草稿，可标记为安全重试，但不得与正式调用混为一类。正式模式中，缺少 AppID/AppSecret、目标账号不存在、账号缺 `appid_env`/`secret_env` 等、能确定发生在 HTTP 请求前的错误统一记录为 `preflight-failed`、`retry_safe=true`；分类测试应使用发布器真实错误文本，而不是自造一条过宽正则。只有无法证明请求尚未发送的错误才进入 uncertain。

### `running` 也是不确定状态

正式调用前必须先原子落盘 `draft=running`、`attempts=1`、`input_sha256`、`retry_safe=false` 和目标账号摘要，再发送 POST。进程若在请求发送后、结果落盘或 completed 状态落盘前退出，后续 `finish` 看到遗留 `running` 时不得继续发布；应转为 `failed/uncertain` 并要求人工对账。旧任务缺少 attempt 或目标摘要时也要保守停止，不能因字段不全假定“请求没发出”。

即使发现 `draft-result.json`，也只有在结果结构、账号、动作、非空 media_id 和对应输入全部可验证时才能协调为 completed；否则仍按 uncertain 处理。

### `init` 不得擦除防重证据

同账号 `current/` 中任一阶段为 `running` 或 `failed`，尤其 draft 为 uncertain 时，普通 `init` 必须拒绝删除工作区。需要整轮重来时使用明确的危险参数（如 `--force-new`），并在执行前由操作者承担远端草稿对账责任。不要让“新任务覆盖旧临时目录”的便利性高于非幂等操作的审计证据。

## 状态与失败落盘

- 状态汇总应先检查任意阶段 `failed`，再判断 drafted、validated 等成功终态。
- prepare 的字数、来源、配图或阶段顺序门禁失败必须落盘，保存 `phase=prepare` 和错误摘要。
- validate checkpoint 同时绑定 HTML 和预览文件哈希；预览损坏不能错误复用。
- 不要只测正常恢复；必须覆盖“输入改变”“响应不确定”“落盘失败”和“成功状态后出现后续失败”。

## 路径信任边界

任务清单是数据，不是可信执行配置：

- 以真实 `job.json` 所在目录作为工作区根，并校验清单中的 `job_dir` 与之相同；
- artifact 使用 `realpath` 后校验仍位于工作区，拒绝绝对路径、`..` 和指向目录外的软链接；
- 内部脚本根目录从当前 Skill 安装位置推导，不从可修改的 job manifest 读取；
- HTML 中本地正文图片必须位于 HTML 目录内，拒绝 `file://`、绝对越界路径、`../` 和软链接逃逸；
- 显式封面路径可以有独立策略，但不能因此放宽正文图片边界。

### 图片验证必须有资源和结构边界

local 与 HTTP 图片都应使用同一最大字节数做有界读取；不得先无界读入内存再检查大小。dry-run 虽然禁止微信外联，仍必须对本地正文图和封面执行与正式模式相同的大小、MIME、magic bytes 和真实路径校验。

magic bytes 不能只检查最短前缀：PNG、JPEG、GIF、WebP 必须先核对签名/声明类型，再由 Pillow 执行 `verify` 和全帧 `load`，拒绝 CRC、chunk/segment、图像数据或结束结构损坏的文件。当前环境缺少完整解码器时安全失败，不得退回只看首尾标记的弱校验；测试必须包含不可解码外壳、截断文件、伪后缀和超过上限的本地文件。

## 自动热点元数据闭环

自动热点不能只存两个 URL。topic 阶段应机械验证并保存：

- 至少两个不同来源域名；
- 每个证据 URL 对应的发布时间和时区；
- 账号允许的 category；
- 明确的 affected group；
- 首选及回退时效窗口。

prepare 再读取真实 `sources.md`，要求其中包含 discover 阶段保存的全部证据 URL，防止用无关链接凑域名。

## 最小回归集合

1. 未变化输入恢复旧草稿；正文、来源、图片、目标 AppID 和目标账号发布字段变化均不恢复；无关账号配置变化仍恢复。
2. `draft/add` timeout、EOF、connection reset、响应字段不完整和结果落盘失败分别验证：发布调用次数严格为 1，再次 finish 被 uncertain 门禁阻止。
3. 遗留 `draft=running` 在任何渲染、客户端构造或发布前转为 uncertain；缺少旧版 details 也不得自动续发。
4. HTML/封面先损坏、后被确定性重建为原字节时，第二次恢复检查复用旧草稿，发布调用次数为 0。
5. 普通 `init` 拒绝删除 running/failed/uncertain 工作区；只有显式 force 路径可清理。
6. prepare 失败持久化，且全局 state 为 failed。
7. artifact 绝对路径、工作目录软链接、HTML `../` 和软链接图片被拒绝；本地超大图片和截断图片被拒绝。
8. dry-run 对 `urlopen` 和客户端构造器设置 network tripwire，证明无微信外联，同时本地图片仍执行完整门禁。
9. 自动热点缺时间、过期、错误类别、缺受影响人群或 sources 不对应时失败。
10. 先跑定向 RED/GREEN，再跑完整 unittest、核心语法检查、组件 lint、敏感信息扫描、隔离 dry-run、生产工作区前后指纹和 `git diff --check`；全部通过且最终只读审查无 P0/P1 后才能提交。
