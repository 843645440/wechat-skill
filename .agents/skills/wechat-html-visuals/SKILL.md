---
name: wechat-html-visuals
description: 使用受约束的 JSON 内容和固定 HTML/CSS 模板，确定性生成微信公众号封面、观点卡、对比图、流程图和数据卡，并通过 Chrome/Chromium 截图为 PNG。用于文章需要稳定中文、准确编号和可重复构图，或需要替代不稳定 AI 生图与视觉检测循环时。
---

# 微信公众号 HTML 视觉图

把文章信息转换为结构化视觉卡片，再用本地浏览器渲染成 PNG。不要调用生成式图片模型，也不要对结果执行 AI 视觉检查。

## 必要条件

需要 Python 3 和 Chrome/Chromium。渲染器会自动查找常见浏览器路径；云端环境也可通过 `HTML_VISUAL_BROWSER` 指定可执行文件。该流程不需要图片 API Key。

## 工作流

1. 从最终文章和 `sources.md` 选择适合视觉化的现有信息，不新增事实、数字、产品名称或结论。
2. 正文默认生成 2—3 张图，优先覆盖不同功能：一个核心判断、一个流程或比较、一个成本/影响分配。短文可以只生成 1—2 张。
3. 按 [references/spec.md](references/spec.md) 写 JSON：
   - 封面：`cover/cover.spec.json`
   - 正文：`illustrations/specs/NN-{slug}.json`
4. 对每个 JSON 调用：

```bash
python3 <SKILL_ROOT>/scripts/render_visual.py \
  --spec <ABSOLUTE_SPEC.json> \
  --output <ABSOLUTE_OUTPUT.png> \
  --html-output <ABSOLUTE_OUTPUT.html>
```

5. 将正文 PNG 的相对路径插入 `article.md`，封面固定输出为 `cover/cover.png`。

## 模板选择

- `cover`：文章封面，固定 1410×600；允许准确标题和副标题。
- `insight`：2—4 个观点或影响对象。
- `comparison`：两个对象、路线或阶段的并列比较。
- `process`：3—5 个有顺序的步骤；编号由模板生成，不在 JSON 中手写。
- `metrics`：2—4 个已有数据或关键量，不得为了视觉效果补造数字。

正文模板固定 1200×800。主题只从 `emerald`、`indigo`、`amber`、`slate` 中选择；同一篇文章保持一个主题。

## 硬性边界

- 每张图只渲染一次。浏览器进程崩溃时允许原命令技术性重试一次，不做 V2/V3 审美循环。
- 渲染器已经检查 JSON 字段、字符长度、PNG 签名和精确尺寸；通过即使用，不再调用视觉模型检查乱码、构图或装饰细节。
- 字段过长时先缩短 JSON 再渲染，不依赖 CSS 隐藏溢出内容。
- 不接受任意 HTML、JavaScript、远程字体、远程图片或外部 CSS。所有文字均 HTML 转义，所有样式来自项目模板。
- 内部截图 HTML 可以使用 `<div>`、`class`、`<style>` 和 Grid；它不会粘贴进公众号正文，不受根排版 HTML 约束。最终插入正文的只有 PNG。
- 不使用表情符号、伪代码、装饰字母、随机数字或无来源标签。装饰元素由 CSS 几何图形提供。

## 失败处理

- JSON 不合规：按错误提示修改字段后再首次渲染。
- 找不到浏览器：设置 `HTML_VISUAL_BROWSER` 或安装 Chrome/Chromium；保留已生成的 HTML。
- PNG 尺寸或签名不正确：只允许对同一命令重试一次；仍失败就将图片阶段标记为失败或降级，不切换到 AI 生图。

完整字段限制和示例见 [references/spec.md](references/spec.md)。
