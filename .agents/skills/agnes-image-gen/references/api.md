# Agnes Image 2.1 Flash API

来源：[Agnes 官方教学文档](https://agnes-ai.com/zh-Hans/docs/agnes-image-21-flash)，接入实现以该页面在 2026-07-18 公布的字段为准。

## 请求

- Endpoint：`POST https://apihub.agnes-ai.com/v1/images/generations`
- Authorization：`Bearer $AGNES_API_KEY`
- Model：`agnes-image-2.1-flash`
- 文生图必填：`model`、`prompt`、`size`
- 图生图：将 URL 或 Data URI 数组放入 `extra_body.image`

支持的档位为 `1K`、`2K`、`3K`、`4K`。原生比例为 `1:1`、`3:4`、`4:3`、`16:9`、`9:16`、`2:3`、`3:2`、`21:9`。项目将公众号封面常用的 `2.35:1` 映射为最接近的 `21:9`。

## Base64 返回

文生图设置顶层 `return_base64: true`。图生图设置：

```json
{
  "extra_body": {
    "image": ["data:image/png;base64,..."],
    "response_format": "b64_json"
  }
}
```

成功图片位于 `data[0].b64_json`。脚本也兼容 `data[0].url`，但只下载 HTTPS URL。不要把 `response_format` 放在请求体顶层，也不要为图生图传递 `tags`。

## 运行约束

- 官方建议客户端超时设置为 60–360 秒；脚本默认 180 秒。
- 当前价格可能变化，自动任务不应依赖文档中的临时促销价格。
- 401/403 通常表示 Key 或账号权限问题；429 表示限流；5xx 表示服务端故障。
