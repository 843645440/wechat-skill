# 真实效果验收：用一篇草稿替代继续代码审查

## 触发条件

当用户明确要求“不再根据代码审”“直接测试一篇”“按实际效果审”时，切换到本流程：

- 冻结代码，不再继续静态审计、补测试、提交或推送。
- 不修改全局配置，不碰未授权账号。
- 用一篇真实文章跑完整流水线，以最终**草稿箱人工观感**为证据。

这不是常规生产任务，也不是 dry-run。目标是验证真实端到端效果，因此只有用户明确授权时才创建草稿；始终止于草稿箱，不公开发布。

## 隔离工作区

为避免覆盖账号日常任务，可使用独立临时基目录：

```bash
BASE=$(mktemp -d /tmp/wechat-live-effect-XXXXXX)
python3 <PIPELINE_ROOT>/scripts/pipeline_job.py init \
  --project-root <PROJECT_ROOT> \
  --work-dir "$BASE" \
  --account <AUTHORIZED_TEST_ACCOUNT> \
  --topic "<TEST_TOPIC>"
```

注意：`--work-dir` 接受的是基目录，`init` 实际返回的任务路径是：

```text
<BASE>/<account>/current/job.json
```

后续命令必须使用 `init` 输出的真实 `job.json` 路径。

## 一篇真实稿的执行范围

1. 使用给定主题；未给主题时选一个边界清楚、可核验的主题。
2. 正文、shape 轮换、一次 strong humanize、0—3 张正文图、**生图封面**、随机主题，按现行契约执行。
3. **禁止** Agent 用视觉模型 / Read 图片 / OCR /「逐字核对像素」审封面或正文图——云端 Agent 通常无视觉，且耗时无收益；**效果以用户打开草稿箱人工核对为准**。
4. 机械门禁仅保留：文件落盘、字数、路径、草稿 API 字段完整。
5. `prepare` 成功后才运行正式 `finish`。一次只启动一个 `finish` 进程。

## 验收标准（无视觉）

不要因工具返回 success 就宣称“用户观感合格”，但 Agent **也不必**打开图片做审美判断。报告应包含：

- `state=drafted`、非空真实 `draft_media_id`
- 标题、字数、主题、正文图数量、封面是否上传
- 产物路径：`article.md` / `article.html` / `cover/cover.png`
- 明确提示：**请用户在草稿箱人工核对**封面、配图与排版

### 禁止的“验收”动作

- 调用多模态/视觉模型看图  
- 用 Read 工具“看” PNG/JPG 并描述是否糊字  
- 为视觉瑕疵自动重跑 `finish` 产生第二份草稿（除非用户明确要求重做）

### 允许的机械检查

- 文件存在、非空、魔数可识别（PNG/JPEG/WebP）  
- 字数区间、标题长度、路径不越界  
- 草稿 API 返回字段与 `run_id` 一致  

## 草稿后的安全边界

一旦正式 `finish` 已创建草稿：

- 先核验 `job.state=drafted`、`draft.status=completed` 和非空 `draft_media_id`。
- 观感问题留给用户草稿箱判断；未授权时不要自动再 `finish`。
- 效果报告聚焦真实结果字段与路径，不要转回冗长代码审查。
