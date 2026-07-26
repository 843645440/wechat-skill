# 流水线运行器审计与维护清单

用于审计或修改 `pipeline_runtime.py`、`pipeline_job.py`、发布 dry-run、阶段状态及恢复逻辑。目标是快（不重复昂贵步骤）、准（门禁轻量但机械可验）、狠（失败位置明确、重跑不产生副作用）。

> 本页按**当前简化契约**（2026-07-22 起）维护：阶段为 discover/write/humanize/illustrations/format/cover/draft，产物为 `article.md`、`imgs/`、`cover/cover.png`、`article.html`、`draft-result.json`；幂等边界是 `run_id`。不存在 `sources.md`、`fact-check`、`validate`、预览、leaf count 或文件哈希 checkpoint——审计时发现代码或文档残留这些概念本身就是缺陷。

若请求明确为“最终只读审查”，本轮禁止 auto-fix、格式化、stage、commit 或改仓库文件；只允许读取当前工作树、执行不会污染仓库的验证，并把修复建议写入报告。临时探针放系统临时目录，测试尽量设置 `PYTHONDONTWRITEBYTECODE=1`。

## 1. 先核对契约与实现

按顺序对照：

1. `SKILL.md` 固定工作流；
2. `artifact-contract.md` 的阶段和产物；
3. `pipeline_runtime.py` 的 begin/prepare/finish；
4. `pipeline_job.py` 的状态转换与 gate；
5. `tests/test_pipeline_runtime.py`、`tests/test_pipeline_job.py`、`tests/test_pipeline_simplification.py`；
6. 所有仍提到旧阶段或旧产物的 references。

发现 CLI 新增必填参数或阶段新增 `running` 前置要求时，必须同步更新主流程命令、references 和测试 fixture。不能只改代码或只加测试。

## 2. 幂等与失败后续跑

重点验证：

- 同一 `run_id` 已成功（账号、`action=draft`、`run_id`、非空 `draft_media_id` 全匹配）时再次 finish：直接返回原结果，零外部调用。
- 新 `run_id` 允许同账号同日再建草稿；不存在日期级拦截。
- 后段失败后重跑，只执行失败阶段及其失效下游；不得重新随机主题或重复封面生成。
- completed 阶段不能被普通 begin/finish 回退为 running。
- 微信调用成功但状态落盘异常属于“结果不确定”，不能盲目再次创建草稿。
- `draft/add` 是非幂等 POST：timeout、EOF、connection reset 可能发生在服务端已接受请求之后，不能仅凭错误字符串自动重试；应持久化为 uncertain，交由人工核对。
- `init` 不应静默删除 running/failed/uncertain 工作区；整轮重来必须显式 `--force-new`。

## 3. prepare 的早失败门禁（轻量）

在固定随机主题之前检查：

- `article.md` 存在，标题唯一且 ≤32 字；
- 正文可读字符 1500—4000；
- humanize 已按约定完成并记录强度；
- 正文图引用 0—3 张：超过 3 张拒绝，路径越界拒绝，引用文件不存在则删除该引用继续；
- 无未替换占位符。

不要把这些检查推迟到 finish 尾部，否则会白跑排版和封面。也不要把旧契约的来源、时效、哈希检查加回来。

## 4. dry-run 的定义

dry-run 必须“不联网但完整验证本地发布输入”：

- 实际读取每个本地正文图片，检查存在、大小和真实字节类型；
- 验证明示封面文件，或确认账号配置中确有默认素材 ID；
- 检查标题、账号和 action；
- 不读取凭证、不访问 token cache、不构造远端客户端、不上传素材、不调用微信 API。

测试不能只证明“缺凭据也成功”，还要把网络 opener、客户端构造器和上传方法全部设为一旦调用即失败的 tripwire；对外部 HTTP 图片应明确离线拒绝。

## 5. 路径与清理安全

- 工作区、artifact、封面、正文图和结果文件必须基于 canonical realpath 做 containment 校验；仅用 `abspath/commonpath` 不能阻止符号链接祖先逃逸。
- 递归删除前同时校验目标及所有祖先不是逃逸 symlink，且真实目标仍位于真实 workspace root 下；不得让 `init` 通过 `work/<account>` 符号链接删除根目录外的 `current`。
- 不信任可编辑 `job.json` 中的 `job_dir`、绝对 artifact 路径或 `project_root`。运行器应将 manifest 位置绑定到工作区，并禁止从 manifest 指向的任意目录导入或执行脚本。
- 发布器处理本地图片时覆盖 `..`、绝对路径、`file:` 和 symlink 测试；上传来源必须限制在文章工作区。

## 6. 耗时采集

- 阶段 `running` 应紧贴真实动作开始。
- 优先记录子命令返回的单步 `duration_ms`。
- 重试记录 `attempt_count`、`last_attempt_duration_ms` 和 `total_duration_ms`；不要覆盖历史，也不要把人工等待算进执行耗时。

## 7. 状态与错误落盘

- 每个阶段采用统一状态转换规则，不做零散的阶段名特判。
- 状态汇总必须先处理任何 `failed`，再考虑 drafted 终态。
- 异常必须将当前阶段标为 failed，写入稳定错误类别和简短消息；不要让 prepare 的字数/配图错误或子命令失败后 job 长期停在 running。
- 新 attempt 开始时清理当前 attempt 的瞬态 details；旧 reason 放入历史，不能污染当前成功状态。

## 8. 最小测试矩阵

至少覆盖：

1. prepare 缺 humanize、字数越界、图超 3 张、路径越界时早失败，并持久化为可诊断的 failed；
2. 引用文件不存在的图被移除后草稿继续；0 图草稿可创建；
3. 同一 `run_id` 已成功的 finish 为零外部调用；新 `run_id` 同日可再建；
4. format 成功、cover/draft 任一失败后的定点续跑；
5. draft POST 超时、服务端可能已接受、结果文件落盘失败等 uncertain 分支不会盲目创建第二份草稿；
6. dry-run 缺图、损坏图片、缺封面时失败，并用网络/客户端 tripwire 证明零外联；
7. completed 阶段不会被 begin 回退；
8. 每次状态 completed 前均有 running，测试 fixture 也遵守真实状态机；
9. artifact 绝对路径、`..`、`file:`、符号链接文件/祖先、伪造 `project_root` 和递归清理逃逸均被拒绝；
10. 伪扩展名图片按真实字节类型规范化上传；损坏图跳过后其余正文继续。

执行相关测试后必须报告真实通过/失败数量；新增 RED 测试但实现尚未跟上时，要明确标记为未完成迁移，不能把整个工作树描述为可发布。绿色测试不能推翻一个已由最小探针复现的状态机、路径或幂等不变量缺陷。

## 9. 提交前验收顺序

1. 先写能复现缺陷的 RED 测试，再实施最小修复；
2. 跑新增的定向测试；
3. 跑完整测试套件（`python3 -m pytest tests/ -q`）与 `component_lint.py`；
4. 在临时工作区做隔离 dry-run，证明不污染 `work/<account>/current` 且不触发微信 API；
5. 检查工作树 staged、unstaged、untracked 与 `git diff --check`，确认无凭据和生产产物污染；
6. 进入**冻结窗口**：最终全量测试通过后不再顺手加门禁、改文案或重构；任何后续 patch 都必须至少重跑受影响定向测试，并再次跑完整测试套件；
7. 只有最终工作树完成上述闭环后才能提交或报告“优化完成”。若中途耗尽额度，明确列出最后一次绿色测试发生在哪个 patch 之前，不提交、不宣称可发布。
