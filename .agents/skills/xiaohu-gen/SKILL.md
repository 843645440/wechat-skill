---
name: xiaohu-gen
description: 统一图片生成路由（别名：小虎生图）。信息图/流程图/文字密集类使用 xiaoyi (gpt-image-2)，人像/风景/艺术创作类使用 Agnes。支持双 key 降级和 200s 超时。
---

# 统一图片生成路由

根据图片类型自动选择后端：信息图/流程图/文字密集类 → xiaoyi (gpt-image-2)，人像/风景/艺术创作类 → Agnes (agnes-image-2.1-flash)。

## 路由规则

### 使用 xiaoyi (gpt-image-2) 的场景

- **信息图 (infographic)**：包含多个步骤、数据可视化、流程说明
- **流程图 (flowchart/diagram)**：箭头、连接线、节点关系
- **文字密集型图片**：需要大量可读文字、标签、注释
- **教育类图解**：教程、说明书、知识卡片
- **技术图表**：架构图、系统图、网络拓扑

**判断关键词**：infographic, flowchart, diagram, process, steps, tutorial, educational, technical chart, with labels, readable text, typography

### 使用 Agnes 的场景

- **人像摄影**：人物写真、肖像、模特
- **风景/场景**：自然风光、城市景观、室内场景
- **艺术创作**：插画、概念艺术、风格化作品
- **产品摄影**：商品展示、静物
- **抽象/创意**：非文字主导的视觉创作

**判断关键词**：portrait, person, landscape, scenery, artistic, illustration, product photo, abstract, creative

## 后端配置

### xiaoyi (gpt-image-2)

- **Endpoint**: `https://xiaoyiapi.xyz/v1/images/generations`
- **Primary Key**: 环境变量 `XIAOYI_API_KEY_PRIMARY`
- **Secondary Key**: 环境变量 `XIAOYI_API_KEY_SECONDARY`
- **Timeout**: 200s per key
- **Failover**: Primary 失败 → Secondary → 报告失败（不重试）

### Agnes (agnes-image-2.1-flash)

- **Endpoint**: `https://apihub.agnes-ai.com/v1/images/generations`
- **API Key**: 环境变量 `AGNES_API_KEY`
- **Timeout**: 130s
- **推荐尺寸**: 1K（2K 约 150s 且长连接易断，公众号封面/插图 1K 足够）
- **响应格式**: `extra_body.response_format` 设为 `url` 返回图片 URL，否则返回 b64_json

## 执行流程

### Step 1: 判断图片类型

分析用户提示词，判断属于哪个类别：

- 包含路由规则中的 xiaoyi 关键词 → 走 xiaoyi 路径
- 包含路由规则中的 Agnes 关键词 → 走 Agnes 路径
- 模糊情况默认 → Agnes（人像/艺术更常见）

**Completion criterion**: 明确选择 xiaoyi 或 Agnes，并能说明理由。

### Step 2A: xiaoyi 路径（双 key 降级）

#### 2A.1: 尝试 Primary Key

```bash
curl -s https://xiaoyiapi.xyz/v1/images/generations \
  -H "Authorization: Bearer $XIAOYI_API_KEY_PRIMARY" \
  -H "Content-Type: application/json" \
  --max-time 200 \
  -d '{
  "model": "gpt-image-2",
  "prompt": "<USER_PROMPT>",
  "size": "<SIZE>",
  "n": 1
}'
```

**尺寸映射**：
- 1:1 → `1024x1024`
- 16:9 → `1536x1024`
- 9:16 → `1024x1536`

**Completion criterion**: 响应包含 `"data":[{"b64_json":"..."}]` 且非空。成功 → Step 3。失败 → Step 2A.2。

#### 2A.2: 尝试 Secondary Key

```bash
curl -s https://xiaoyiapi.xyz/v1/images/generations \
  -H "Authorization: Bearer $XIAOYI_API_KEY_SECONDARY" \
  -H "Content-Type: application/json" \
  --max-time 200 \
  -d '{
  "model": "gpt-image-2",
  "prompt": "<USER_PROMPT>",
  "size": "<SIZE>",
  "n": 1
}'
```

**Completion criterion**: 响应包含非空 `b64_json`。成功 → Step 3。失败 → **停止并报告用户，不再重试**。

### Step 2B: Agnes 路径

```bash
curl -s https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer $AGNES_API_KEY" \
  -H "Content-Type: application/json" \
  --max-time 130 \
  -d '{
  "model": "agnes-image-2.1-flash",
  "prompt": "<USER_PROMPT>",
  "size": "<SIZE>",
  "ratio": "<RATIO>",
  "extra_body": {
    "response_format": "url"
  }
}'
```

**Agnes 尺寸映射**（size + ratio 组合）：

| Ratio | 1K | 2K | 3K | 4K |
|-------|-----|-----|-----|-----|
| 1:1 | 1024x1024 | 2048x2048 | 3072x3072 | 4096x4096 |
| 3:4 | 864x1152 | 1728x2304 | 2592x3456 | 3456x4608 |
| 4:3 | 1152x864 | 2304x1728 | 3456x2592 | 4608x3456 |
| 16:9 | 1312x736 | 2624x1472 | 3936x2208 | 5248x2944 |
| 9:16 | 736x1312 | 1472x2624 | 2208x3936 | 2944x5248 |
| 2:3 | 832x1248 | 1664x2496 | 2496x3744 | 3328x4992 |
| 3:2 | 1248x832 | 2496x1664 | 3744x2496 | 4992x3328 |
| 21:9 | 1568x672 | 3136x1344 | 4704x2016 | 6272x2688 |

**公众号封面**：2.35:1 → 使用 `21:9` ratio。

**Completion criterion**: 响应包含 `url` 字段或 `b64_json`。如果是 URL，用 curl 下载保存。失败 → 报告用户。

### Step 3: 解码并保存（xiaoyi 专用）

```python
import base64
img_bytes = base64.b64decode(b64_json_data)
with open('<OUTPUT_PATH>.png', 'wb') as f:
    f.write(img_bytes)
```

**Completion criterion**: 文件存在且 size > 0。

### Step 4: 交付图片

使用 `MEDIA:<output_path>` 发送给用户。

**Completion criterion**: 用户收到图片文件。

## 常见陷阱

1. **路由判断错误**：信息图用了 Agnes 会导致文字模糊、排版混乱；人像用了 xiaoyi 可能过于生硬。严格按关键词判断。

2. **xiaoyi 重试超限**：Primary + Secondary 都失败后，**必须停止**。不要循环尝试或切换到未授权的 key。

3. **Agnes 尺寸选择**：默认 1K。2K 约 150s 且长连接易断，公众号封面/插图 1K 足够。

4. **忘记导出 AGNES_API_KEY**：Agnes 脚本依赖环境变量，未配置会直接报错。

5. **提示词文件缺失**：Agnes 要求 `--prompt-file` 指向绝对路径文件，不接受对话中的临时字符串。

6. **xiaoyi 响应结构校验**：200 OK 但 `"data":[]` 或 `b64_json` 为空也算失败，需降级。

## 验证清单

- [ ] 根据提示词正确判断路由（xiaoyi vs Agnes）
- [ ] xiaoyi 路径：Primary Key 尝试 → 失败则 Secondary → 再失败则报告
- [ ] Agnes 路径：环境变量已配置，使用 1K 尺寸
- [ ] 文件保存成功，size > 0
- [ ] 通过 MEDIA 交付给用户
- [ ] 无重试循环或额外尝试
