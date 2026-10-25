---
name: xiaohu-gen
description: 可选的脚本生图客户端。优先使用 Agent 运行时自带的生图工具；没有自带能力且配置了 AGNES_API_KEY 时，才调用本目录脚本。用于流水线封面或正文配图的脚本降级，不指定其它供应商。
---

# 可选生图客户端

先用当前 Agent 自带的生图能力。提示词和设计说明里不要写供应商名。

没有自带生图、也没有 `AGNES_API_KEY` 时：**正文不配图**。封面由流水线继续走 HTML / Pillow / 账号默认素材，不能空封面。

免费 API Key：<https://platform.agnes-ai.cn>

## 何时用这个脚本

只有流水线脚本或用户明确要求走脚本后端时才调用：

```bash
python3 <this-skill>/scripts/agnes_generate.py \
  --prompt-file <绝对路径> \
  --output <输出.png> \
  --ratio <16:9|2.35:1|21:9> \
  --size 1K
```

- 环境变量：`AGNES_API_KEY`（必需）
- 默认接口：`https://api.agnes-ai.cn/v1/images/generations`
- 可用 `AGNES_IMAGE_ENDPOINT` / `AGNES_IMAGE_MODEL` 覆盖，不要把 Key 写进命令行

封面比例 `2.35:1` 会映射为 `21:9`。公众号插图用 `1K` 即可。

## 流水线约定

- 用户已给图或 Agent 已写入 `imgs/` 并插入正文引用：脚本视为已有图，不再生成。
- 公共事件 / 正式报道：禁止 AI 正文插画；封面走准确标题 HTML。
- 生成失败、超时、缺 Key：正文 `skipped`，封面降级，不把整篇任务标失败。
