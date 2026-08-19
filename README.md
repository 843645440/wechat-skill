> 🤝 **本项目由 甲木 × [「摸鱼小李」](https://mp.weixin.qq.com/s/EMahAzgfAbRQrYukWE7_IQ) 联名共建** —— 排版组件、主题设计与质量标准来自两人的公众号实践。特别感谢小李。

<div align="center">

# wechat-skill · 微信公众号内容 Skill

给 AI Agent 用：把成稿或主题做成可粘贴的公众号 HTML，并写入指定账号**草稿箱**。

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[English](README.en.md) ｜ 中文

</div>

流水线**只创建草稿，不公开发布**，也不等于向粉丝群发。人工审核发生在微信公众号草稿箱。

## 装好后先说这一句

把本仓库当作 Agent 工作区：

```bash
git clone https://github.com/843645440/wechat-skill.git
cd wechat-skill
```

然后对 Agent 说：

> 帮我配置公众号技能

Agent 会跑 `python3 scripts/setup_status.py`，只问还没配的项：账号、常用方式、去 AI 味、正文配图、要不要开系列选题。凭证只进环境变量，不要写进 Git。说明见 [docs/setup.md](docs/setup.md)。

不要只复制根 `SKILL.md`，否则写作和流水线不会一起加载。

## 两种用法

后半段都是同一条工作流（排版 → 封面 → 草稿）。差别只在谁出稿、拦什么。

| | 方式 1：我已有稿 | 方式 2：我给主题，AI 写 |
|---|---|---|
| 你提供 | 文章（Markdown / Word / 正文） | 主题 + 思路，或打开一个系列选题 |
| 写作 | 不写、不重写 | 必写 |
| 去 AI 味 | 可关，默认关 | 强制开 |
| 字数 / 写作分 | 不拦 | 拦（1500–4000 字，score ≥75） |
| 定时任务 | 不适合 | 可以，用你自己 Agent 的定时器 |

只丢了一个标题、没有成稿，不要走方式 1。

**方式 1 示例**

> 用 `$wechat-content-pipeline`，把这篇稿排版后写入 A 账号草稿箱。去 AI 味关掉。

**方式 2 示例**

> 使用 `$wechat-content-pipeline` 为 A 账号写到草稿箱。主题：…… 思路：……

系列选题（涉黑涉恶、贪腐、重大诈骗等）是方式 2 的一个预设，不是热搜。开关在 `config/public-event-archive.json`。必须已有生效裁判或稳定官方结论，并且同时有机关材料和中国官方媒体报道；没有合格题就跳过当天。由你的 Agent 定时任务触发，仓库里不内置 cron。

## 配图

包里有封面和正文配图能力，但是开关：

- **正文图**：默认关。用户带来的图优先，不覆盖。开了之后：先用 Agent 自带生图；没有则看 `AGNES_API_KEY`；都没有就不配图。
- **封面**：不能关成「没有封面」。用户图 → 正式报道用 HTML 准确排标题 → 可选生图 → HTML/Pillow → 账号默认封面。
- HTML 信息模块按题材自动，不算正文图。公共事件强制：无 AI 正文图，封面走准确标题。

提示词里不要写供应商名。需要脚本生图时，免费 Key 在 <https://platform.agnes-ai.cn>，环境变量是 `AGNES_API_KEY`。

## 要进草稿箱时必须配

```bash
cp assets/wechat-accounts.example.json wechat-accounts.json
```

每个账号用独立环境变量，例如 `WECHAT_A_APP_ID` / `WECHAT_A_APP_SECRET`。不要把 AppSecret、token、素材 ID 提交到 Git。

另外需要：

- 公众号已开通素材上传和草稿箱接口
- 运行环境出口 IP 已加入该公众号 IP 白名单
- 能访问 `https://api.weixin.qq.com`
- Python 3

`--dry-run` 只检查映射和 HTML，不能验证 AppSecret、白名单或草稿接口。正式启用前，为每个账号真实创建一次草稿并在后台核对。

根目录的 `publish` 命令只供人工显式发布已审核草稿，自动流水线不会调用它。

## 排版约束（脚本保证）

生成 HTML 禁止 `<style>/<script>/<div>`、`class/id`、绝对定位、grid、CSS 变量；样式全内联；文字用 `<span leaf="">` 包裹。改主题后跑：

```bash
python3 scripts/component_lint.py .
python3 scripts/validate_gzh_html.py out.html
```

主题预览：浏览器打开 `docs/gallery/index.html`。说明见 [docs/all-themes.md](docs/all-themes.md)。

## 免责与许可

- 本工具写入的是公众号**草稿**，不代替你对内容合法性、事实和审核负责。
- 公共事件稿只复述已有官方结论，不处理未决传闻，不构成法律意见。
- 项目采用 **GNU AGPL-3.0**：必须保留甲木 × 摸鱼小李的署名；修改版、Fork、二次分发以及把修改版作为网络服务提供给他人使用，都必须以 AGPL-3.0（或兼容协议）公开完整源代码。不允许闭源或仅付费分发。完整条款见 [LICENSE](LICENSE)。

## 更多

- 首次配置：[docs/setup.md](docs/setup.md)
- 命令与凭证：[docs/usage.md](docs/usage.md)
- 多账号发布：[references/multi-account-publishing.md](references/multi-account-publishing.md)
- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md)
