# Baoyu 正文配图集成

## 适用范围

当公众号流水线不再使用原生 HTML 信息模块，而要在文章正文中使用可发布的配图时采用此约定。

## 固定顺序

1. 完成 `article.md`、事实核验与 `humanizer-zh`。
2. 将 `illustrations` 标记为 `running`，再用 `baoyu-article-illustrator` 生成 1—3 张正文图；不得把图片中不可核验的数字、结论当作事实来源。
3. 将图片保存到当前工作目录的 `imgs/`，将完整提示词保存到 `prompts/`。
4. 在 `article.md` 中插入相对路径 Markdown，例如：`![研究流程示意](imgs/research-workflow.png)`。
5. 仅在图片与提示词真实落盘、Markdown 已插入后，将 `illustrations` 标记为 `completed`，记录 `image_count=N` 与 `skill=baoyu-article-illustrator`。
6. 再执行 `prepare` 与 `finish`；渲染器会把 Markdown 图片转成公众号 HTML 的响应式 `<img>`。

## 门禁

- `illustrations` 不允许跳过或用空计划降级。
- `image_count` 必须在 1—3 之间。
- 最终 `article.html` 的 `<img>` 数量必须等于 `image_count`；不一致时停止草稿发布。
- 图片必须是正文图片，而非信息卡/模块截图；不要再创建 `inline-visuals.json` 或传递 `--plan`。

## 验证

至少运行：

```bash
python3 -m unittest tests.test_pipeline_job tests.test_pipeline_runtime tests.test_article_renderer tests.test_wechat_publish
```

端到端验证用隔离副本和 `finish --dry-run`，检查输出中的 `image_count`、生成的 `article.html` 的图片数，以及 `article_preview.html` 是否存在；不得调用微信草稿 API。不要把 `--dry-run` 与 `--skip-draft` 叠加：后者可能在草稿输入预检前直接返回，造成假通过。