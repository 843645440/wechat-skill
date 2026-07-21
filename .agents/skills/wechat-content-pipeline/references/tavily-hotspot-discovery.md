# Tavily 热点发现（流水线 discover）

本机默认网页后端可为 Tavily（见 Hermes `web.backend` / `.env` 的 `TAVILY_API_KEY`）。公众号无主题日更时按此用。

## 何时用

- 账号 `topic_discovery` 自动选题
- 需要近 24–72h 科技 / AI / 就业 / 产业可核验线索
- 已配置 Tavily 时 **优先于** DDGS 等免 key 兜底

## 推荐查询形态

多组短查询，而不是一句万能长句：

1. `{领域} 热点 {年}{月}`（如 `人工智能 热点 2026年7月`）
2. `{机构或报告名} {主题}`（如 `普华永道 人工智能 就业 晴雨表`）
3. `{大会/政策} {关键词}`（如 `WAIC 2026`、`十五五 就业 人工智能`）
4. 必要时补英文源：`AI jobs barometer China 2026`

每组 `web_search` limit 5–8，合并去重后再筛。

## 过滤

- 对照账号 `categories` / `avoid`
- 丢掉：纯情绪稿、无日期、明显标题党且无机构背书、无法抽出可核对数字的页
- 保留：机构报告、官媒/行业报对报告的转述、政府规划、大会官网

## 入选后必做

对 1–3 个候选 URL `web_extract`：

- 只采用正文中的数字、日期、职务与引述
- 界面新闻等转载页若带广告免责，仍以文中普华永道等机构表述为准，并在 `sources.md` 标明转述来源与日期
- 素材不够 1500 字可核验信息 → 换题，不注水

## 双 key（运维）

- `TAVILY_API_KEY` 主用，`TAVILY_API_KEY_2` 备用
- 本机 Tavily 插件在 401/402/403/429 时自动切换；状态在 `~/.hermes/cache/tavily-active-key-index`
- 改 `.env` 后 gateway/cron 需加载新环境（`/reload` 或重启对应进程）

## 与半程演示

用户只要「搜索→写作→去 AI 味」样稿时：用 Tavily 完成 discover+extract 即可，不必 `pipeline_job init`；终稿贴聊天，停在 humanize。
