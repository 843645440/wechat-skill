---
name: agnes-image-gen
description: 使用 Agnes Image 2.1 Flash API 从已保存的提示词生成 PNG 图片，或使用 URL、本地图片作为参考进行图生图。用于微信公众号封面、正文插图以及 baoyu-cover-image、baoyu-article-illustrator 需要确定性栅格图片后端时；需要通过 AGNES_API_KEY 提供凭证。
---

# Agnes 图片生成后端

调用 `agnes-image-2.1-flash` 生成真正的栅格图片。本 Skill 是项目图片渲染后端；封面和插图 Skill 仍负责选图、风格、构图和提示词。

## 必要配置

从运行环境读取 `AGNES_API_KEY`。只在 HTTPS Authorization 请求头中使用它，不把 Key 写入提示词、命令参数、文件、stdout 或任务产物。

可选环境变量：

- `AGNES_IMAGE_MODEL`：默认 `agnes-image-2.1-flash`。
- `AGNES_IMAGE_ENDPOINT`：默认官方生成端点；除非迁移服务，否则不要修改。
- `AGNES_IMAGE_SIZE`：默认 `2K`。

## 生成流程

1. 确认调用方已经把完整最终提示词写入独立文件。不要接受只存在于对话里的临时提示词。
2. 确定输出路径、尺寸和宽高比。公众号封面的 `2.35:1` 会自动映射为 Agnes 支持的 `21:9`。
3. 文生图不传 `--ref`；图生图为每张参考图片传一次 `--ref`。本地图片会转成 Data URI，公共 HTTPS URL 会原样传递。
4. 调用脚本并读取 stdout 的单行 JSON 结果：

```bash
python3 <SKILL_ROOT>/scripts/generate.py \
  --prompt-file <ABSOLUTE_PROMPT_FILE> \
  --output <ABSOLUTE_OUTPUT.png> \
  --size 2K --ratio 16:9 \
  [--ref <ABSOLUTE_IMAGE_OR_HTTPS_URL>]...
```

5. 生成失败时根据 JSON 错误修正配置或提示词。脚本会对限流和服务器错误自动重试一次；不要在认证失败时切换到未经用户授权的供应商。

正文多图没有原生批量接口时，可并行执行最多四个独立命令。每个命令必须使用自己的提示词文件和输出路径。

## 图生图

参考图片仅支持公共 HTTPS URL、`data:image/...` URI 或本地图片路径。不要把需要 Cookie、登录态或私有请求头的 URL 交给 API。保持原构图时，要在提示词中明确写出必须保留的主体、视角和布局。

## 验证配置

使用 `--dry-run` 检查提示词、比例、参考图片和 `AGNES_API_KEY` 是否就绪；它不会调用 API，也不会打印提示词或 Key：

```bash
python3 <SKILL_ROOT>/scripts/generate.py \
  --prompt-file <PROMPT_FILE> --output <OUTPUT.png> \
  --ratio 21:9 --dry-run
```

接口字段和返回结构见 [references/api.md](references/api.md)。
