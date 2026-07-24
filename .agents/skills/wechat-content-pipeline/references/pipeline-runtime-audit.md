# 流水线运行器审计与维护清单

用于审计或修改 `pipeline_runtime.py`、`pipeline_job.py`、发布 dry-run、阶段状态及恢复逻辑。目标是快（不重复昂贵步骤）、准（热点与产物有机械门禁）、狠（失败位置明确、重跑不产生副作用）。

若请求明确为“最终只读审查”，本轮禁止 auto-fix、格式化、stage、commit 或改仓库文件；只允许读取当前工作树、执行不会污染仓库的验证，并把修复建议写入报告。临时探针放系统临时目录，测试尽量设置 `PYTHONDONTWRITEBYTECODE=1`。

## 1. 先核对契约与实现

按顺序对照：

1. `SKILL.md` 固定工作流；
2. `artifact-contract.md` 的阶段和产物；
3. `pipeline_runtime.py` 的 begin/prepare/finish；
4. `pipeline_job.py` 的状态转换与 gate；
5. `tests/test_pipeline_runtime.py`、`tests/test_pipeline_job.py`；
6. 所有仍提到旧阶段或旧产物的 references。

发现 CLI 新增必填参数或阶段新增 `running` 前置要求时，必须同步更新主流程命令、references 和测试 fixture。不能只改代码或只加测试。

## 2. 幂等与失败后续跑

重点验证：

- 已验证的 `draft-result.json` + `draft.status=completed` + `state=drafted` 再次 finish 时，应直接返回已有结果，不调用外部命令；但复用前还必须核对该草稿记录的发布输入指纹，不能只校验 account/action/media ID。auto-hotspot 即使命中 completed 快速恢复，也必须先按当前时间重查证据时效和完整元数据，失败时保持 completed 记录不变。
- 后段失败后重跑，只执行失败阶段及其失效下游；不得重新随机主题、重复正文渲染或重复封面渲染。
- completed 阶段不能被普通 begin/finish 回退为 running；显式 retry 才能开启新 attempt。
- 每个昂贵阶段完成时保存输入指纹。至少覆盖 article、sources、正文图片字节、影响封面/排版的配置、账号和 action；输入变化必须使对应阶段及已完成 draft 失效。
- 必须测试“草稿已 completed 后修改 article/sources/图片”的路径，确认不会在任何输入校验之前直接返回旧 media ID。
- 微信调用成功但状态落盘异常属于“结果不确定”，不能盲目再次创建草稿。若结果文件可验证则先复用。
- `draft/add` 是非幂等 POST：timeout、EOF、connection reset 可能发生在服务端已接受请求之后，不能仅凭错误字符串自动重试；没有 API 幂等键或可靠对账查询时应持久化为 uncertain，交由查询或人工核对。
- `init` 不应静默删除 running/failed 工作区；新任务覆盖须显式表达，恢复默认复用 current。

## 3. prepare 的早失败门禁

在随机主题和生成封面规格之前检查：

- discover 已完成；自动热点证据元数据完整；
- article/sources 存在且内容合法；
- humanize 已按约定完成并记录强度；
- illustrations 已完成，数量合法，Markdown 引用的本地图片真实存在；
- 标题、字数及来源结构符合契约。

不要把这些检查推迟到 finish 尾部的 draft gate，否则会白跑正文、封面和预览。

## 4. 热点准确性门禁

URL 数量不是完整的准确性门禁。自动热点至少记录并机械验证：

- 不同 hostname 的独立证据；
- 事件发布时间与检查时间；
- 是否落在账号 window/fallback 时间窗；
- 匹配账号 categories；
- 明确受影响人群；
- 搜索摘要已由正文提取或一手来源核实。

主流程示例必须包含当前 CLI 要求的证据参数。给定主题可跳过自动热点时效门禁，但不能跳过写作事实核验。

## 5. dry-run 的定义

dry-run 必须“不联网但完整验证本地发布输入”：

- 校验 HTML 严格规则和占位符；
- 实际读取每个本地正文图片，检查存在、大小和图片类型；
- 验证明示封面文件，或确认账号配置中确有默认素材 ID；
- 检查标题、账号和 action；
- 不读取凭证、不访问 token cache、不构造远端客户端、不上传素材、不调用微信 API。

`--dry-run` 与“完全跳过草稿输入检查”的诊断参数不能叠加造成假通过；应互斥或明确优先级，并有测试覆盖。测试不能只证明“缺凭据也成功”，还要把网络 opener、客户端构造器和上传方法全部设为一旦调用即失败的 tripwire；对外部 HTTP 图片应明确离线拒绝。

## 5.1 路径与清理安全

- 工作区、artifact、封面、正文图和结果文件必须基于 canonical realpath 做 containment 校验；仅用 `abspath/commonpath` 不能阻止符号链接祖先逃逸。
- 递归删除前同时校验目标及所有祖先不是逃逸 symlink，且真实目标仍位于真实 workspace root 下；不得让 `init` 通过 `work/<account>` 符号链接删除根目录外的 `current`。
- 不信任可编辑 `job.json` 中的 `job_dir`、绝对 artifact 路径或 `project_root`。运行器应将 manifest 位置绑定到工作区，并禁止从 manifest 指向的任意目录导入或执行脚本。
- 发布器处理本地图片时覆盖 `..`、绝对路径、`file:` 和 symlink 测试；除非明确是通用 CLI 的用户授权路径，否则上传来源必须限制在文章工作区。

## 6. 耗时采集

- 阶段 `running` 应紧贴真实动作开始，不能在 prepare 中启动 format、等到稍后 finish 才结束。
- 优先记录子命令返回的单步 `duration_ms`。
- 重试记录 `attempt_count`、`last_attempt_duration_ms` 和 `total_duration_ms`；不要覆盖历史，也不要把人工等待算进执行耗时。
- write 与 fact-check 若并行，只能报告并行墙钟时间或分别显式计时，不能把同一时间段伪装成两个独立耗时。

## 7. 状态与错误落盘

- 每个阶段采用统一状态转换规则，不做零散的阶段名特判。
- 状态汇总必须先处理任何 `failed`，再考虑历史 draft 的 `validated`/`drafted` 终态；旧 dry-run 成功不得掩盖后续 format/cover/validate 失败。
- 异常必须将当前阶段标为 failed，写入稳定错误类别和简短消息；不要让 prepare 的字数/来源/配图错误或子命令失败后 job 长期停在 running。
- 新 attempt 开始时清理当前 attempt 的瞬态 details；旧 reason、兜底标志和 attempts 放入历史，不能污染当前成功状态。
- 用组合状态探针验证 summarizer，例如 `draft=skipped(dry_run passed) + format=failed` 必须得到 failed，而不是 validated-dry-run。

## 8. 最小测试矩阵

至少覆盖：

1. prepare 缺 humanize / illustrations 时早失败，并验证 job 持久化为可诊断的 failed，而非残留 running；
2. prepare 后 article、sources 或图片字节变化时 finish 拒绝旧快照；
3. 已 drafted 且输入指纹未变的 finish 为零外部调用；已 drafted 后任一发布输入变化时不得直接返回旧 media ID；
4. format 成功、cover/validate/draft 任一失败后的定点续跑；
5. draft POST 超时、服务端可能已接受、结果文件落盘失败等 uncertain 分支不会盲目创建第二份草稿；
6. dry-run 缺图、损坏图片、缺封面时失败，并用网络/客户端 tripwire 证明零外联；
7. 自动热点缺证据、同域证据、过期事件、类别不匹配时失败；
8. completed 阶段不会被 begin 回退，历史 dry-run 成功不会掩盖后续 failed；
9. 每次状态 completed 前均有 running，测试 fixture 也遵守真实状态机；
10. artifact 绝对路径、`..`、`file:`、符号链接文件/祖先、伪造 `project_root` 和递归清理逃逸均被拒绝。

执行相关测试后必须报告真实通过/失败数量；新增 RED 测试但实现尚未跟上时，要明确标记为未完成迁移，不能把整个工作树描述为可发布。绿色测试不能推翻一个已由最小探针复现的状态机、路径或幂等不变量缺陷。

## 9. “快准狠”实现顺序

优先按以下顺序落地，避免只加门禁却没有恢复收益，或只做缓存却复用脏产物：

1. **先早失败**：`prepare` 在随机主题、排版和封面前检查 humanize、来源、字数、标题、配图声明、Markdown 图片引用和本地文件；失败不能改变后续阶段状态。
2. **再做内容寻址检查点**：format 保存 `article_sha256`/`html_sha256`；cover 保存 `cover_spec_sha256`/`cover_sha256`。只有阶段 completed、产物存在且输入指纹一致时才能复用；输入改变必须重跑对应阶段及下游。
3. **最后保护外部副作用**：若 draft 已 completed，只有当 `draft-result.json` 的 account/action/media ID 和已记录的发布输入指纹均匹配时，`finish` 才能先返回已有草稿；不能因本地预览或封面缺失再创建第二份草稿，也不能在上游输入已变化时返回旧草稿。外部调用成功但落盘不完整时进入“结果不确定”分支，先查结果再决定是否重试。
4. **按副作用语义重试**：标题过长、HTML 不合法、缺图、规格错误等确定性失败立即停止；封面等本地可重复步骤的瞬时故障可按契约重试。对 `draft/add` 这类非幂等 POST，timeout/EOF/连接中断属于结果不确定，不能套用通用瞬时错误正则直接重放。
5. **阶段计时必须来自真实状态机**：高成本阶段一律 `pending → running → completed/failed`；禁止直接 completed，否则 `duration_ms=0` 会掩盖瓶颈。测试 fixture 也不得绕过这条规则。

### 提交前验收顺序

1. 先写能复现缺陷的 RED 测试，再实施最小修复；
2. 跑新增的定向测试；
3. 跑完整测试套件；
4. 在临时工作区做隔离 dry-run，证明不污染 `work/a/current`、`work/b/current` 且不触发微信 API；随后对同一临时 job 再跑一次 `finish --dry-run`，比较 format/cover/validate 的 `started_at`、`duration_ms` 与指纹，证明昂贵检查点确实复用，而不只是命令返回成功；
5. 检查当前工作树的 staged、unstaged 与 untracked 文件、diff、凭据和生产产物污染。**不得用 `git diff` 或 `git diff --binary | sha256sum` 单独绑定终审快照**，因为它们遗漏 untracked；运行 `scripts/full-worktree-snapshot.py`，用 `git diff --binary HEAD` 加按路径排序的 untracked 路径、模式与字节生成组合哈希，并把文件总数一并交给审查者；
6. 异步审查者必须在开始和结束时都运行 `scripts/full-worktree-snapshot.py --verify <SHA256>`。任一时点失配就只报告“快照失配”，旧测试、旧行号和旧审查结论全部作废；主会话不得把迟到的旧快照审查当成当前结论。若审查期间工作树被并发修改，重新读取受影响文件、重跑相关验证并冻结新哈希，不得把不同时间点的代码、diff 和测试结果拼成一个“绿色”结论；
7. **先判断失败属于产品还是验收脚本**：JSON 解析假设、硬编码产物路径、展示字段类型或临时 HOME 导致的浏览器发现差异，只能说明验收 harness 失败。先读取真实 CLI 输出/manifest、修正 harness 并重跑；产品断言尚未执行时，不得报告产品失败。反过来，不能因为 harness 最终通过就忽略已经由最小探针复现的产品缺陷；
8. 进入**冻结窗口**：最终全量测试通过后不再顺手加门禁、改文案或重构。任何代码、测试、fixture、契约或 skill 支持文件的后续 patch 都会使旧的绿色结果和快照哈希失效，必须至少重跑受影响定向测试，并再次跑完整测试套件；
9. 预留足够工具调用额度给“最终全量测试 → lint/compile/diff-check → 状态确认 → commit”。额度不足时立即停止扩展范围，不要继续加 P1/P2 改动；
10. 只有最终工作树完成上述闭环后才能提交或报告“优化完成”。若工具额度或时间在中途耗尽，明确列出最后一次绿色测试发生在哪个 patch 之前、哪些改动仅有定向测试，不提交、不宣称可发布。