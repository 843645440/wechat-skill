# Baoyu 正文配图集成（分析用 baoyu · 出图用自有后端）

## 分工

| 步骤 | 用谁 | 做什么 |
|------|------|--------|
| 分析文章、选插入点、定 Type×Style×Palette、写提示词文件 | **`baoyu-article-illustrator`** | 读 `../baoyu-article-illustrator/SKILL.md`，按 workflow 产出 outline + `prompts/` |
| 真正生成栅格图 | **当前环境自有生图后端** | `image_generate` / Imagine / Agnes / 运行时原生工具等；**不要**为迁就环境跳过 baoyu 分析步骤 |
| 流水线编排 | `wechat-content-pipeline` | stage 记账、路径、0—3 张、可降级 |

流水线模式默认：**跳过 baoyu 的「向用户确认风格」交互**（等价用户已授权全自动：`直接生成` / 按档案默认），但仍必须：

1. 分析正文选位；  
2. 先落盘完整 prompt 文件再出图；  
3. 用**自有后端**按 prompt 出图到 `imgs/`；  
4. 插入 Markdown；  
5. **不做视觉审图**。

## 固定顺序

1. `article.md` + humanize 完成。  
2. `illustrations` → `running`。  
3. 加载 baoyu-article-illustrator：  
   - 分析 1—3 个最增值插图位（机制、对比、流程优先；少用纯装饰）。  
   - 选定 type/style/palette（可用档案默认或 `editorial` + 文章气质）。  
   - 写入 `prompts/NN-{type}-{slug}.md`（或 `prompts/` 下等价结构）。  
4. **出图**：对每个 prompt，调用**当前 runtime 自有**生图工具（非 baoyu 内部专用 CLI 亦可），保存到 `imgs/`。  
   - 失败单张重试 1 次；全部失败 → `illustrations=skipped`，无图继续。  
5. 在 `article.md` 对应段落后插入 `![说明](imgs/...)`。  
6. `illustrations` → `completed`（或 `skipped`），detail 可含 `analyzer=baoyu;backend=image_generate;count=N;visual_check=none`。  
7. 再跑封面生图 → `prepare` → `finish`。

## 内容要求

- 图必须服务**理解**：流程、对比、架构、代价分配；禁止与正文无关的炫图。  
- 图中少字；需要标签时用短英文或极简中文，错字则重生成 prompt，**禁止**画完用代码涂字。  
- 不得把图中数字当未核验事实写回正文。  
- 不要创建 `inline-visuals.json`。

## 门禁

- 0—3 张；路径不越界。  
- **禁止**跳过 baoyu 分析、直接随手写一句 prompt 出图（测试捷径不算正式契约）。  
- **禁止**视觉/OCR 审图；用户草稿箱人工核对。  
