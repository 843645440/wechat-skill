#!/usr/bin/env python3
"""热点雷达：**默认关闭**的选题捕获开关。

为什么默认关：
本仓库的默认模式是「用户命题」——用户给主题和思路，流水线负责写。自动扫热点是
另一种模式，它会把「写什么」的决定权从人手里拿走。所以它必须是一个**用户主动
打开的开关**，而不是一个悄悄生效的默认行为。

开关在哪：
`config/writer-config.json` → `hot_topic_radar.enabled`（默认 `false`）。
临时试一次可以加 `--force`，但 `--force` 不会改配置，下次仍然是关的。

这个脚本做什么、不做什么：
- **做**：并发去若干公开榜单取标题 → 跨榜单聚类 → 按「上榜数 + 关键词命中 + 排名」
  打分 → 输出候选选题清单，每条带三个可用的切入角。
- **不做**：不自动选题、不自动写 brief、不自动开流水线。它只把「今天有什么」摆到
  桌面上，**选哪条、怎么写，仍然是人的决定**。

失败处理与本仓库其余脚本一致：单个源失败不影响其他源，退出码恒为 0，
失败原因写进 `sources[].error`。没有网络时得到的是一份空清单，不是一个崩溃。

不需要任何 API key。
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR.parent / "config" / "writer-config.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BAIDU_BOARD_RE = re.compile(r"<!--s-data:(.*?)-->", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------- 取数

def fetch(url, timeout, extra_headers=None):
    """取页面。`extra_headers` 是给挑食的站点用的。

    微博的 hotSearch 接口没有 Referer 会直接 403——不是要登录，只是要一个来路。
    这类站点差异必须能在配置里表达，否则每加一个源就得改一次代码。
    """
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/html, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    headers.update(extra_headers or {})
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def walk(node, path):
    """按点分路径取值，支持列表下标：`data.realtime` / `data.0.items`。"""
    if not path:
        return node
    for part in path.split("."):
        if node is None:
            return None
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


def clean_title(value):
    if not isinstance(value, str):
        return ""
    value = TAG_RE.sub("", value)
    value = re.sub(r"&[a-zA-Z#0-9]+;", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_json_source(text, spec):
    payload = json.loads(text)
    rows = walk(payload, spec.get("path", ""))
    if not isinstance(rows, list):
        raise ValueError(f"path `{spec.get('path')}` 不是列表")
    title_field = spec.get("title_field", "title")
    items = []
    for row in rows:
        title = clean_title(walk(row, title_field) if isinstance(row, dict) else row)
        if title:
            items.append(title)
    return items


def parse_baidu_source(text, spec):
    match = BAIDU_BOARD_RE.search(text)
    if not match:
        raise ValueError("页面里没有 s-data 数据块（百度改版了）")
    payload = json.loads(match.group(1))
    cards = walk(payload, "data.cards") or []
    items = []
    for card in cards:
        for row in (card.get("content") or []):
            title = clean_title(row.get("query") or row.get("word"))
            if title:
                items.append(title)
    if not items:
        raise ValueError("s-data 里没有解析出条目")
    return items


def parse_rss_source(text, spec):
    root = ElementTree.fromstring(text.encode("utf-8"))
    items = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag in ("item", "entry"):
            for child in node:
                if child.tag.rsplit("}", 1)[-1] == "title":
                    title = clean_title(child.text or "")
                    if title:
                        items.append(title)
                    break
    if not items:
        raise ValueError("RSS 里没有 item/entry")
    return items


PARSERS = {"json": parse_json_source, "baidu": parse_baidu_source,
           "rss": parse_rss_source}


def pull_source(spec, timeout):
    """单个榜单：成功返回标题列表，失败返回错误描述。绝不抛出。"""
    name = spec.get("name", "unnamed")
    try:
        parser = PARSERS[spec.get("kind", "json")]
    except KeyError:
        return {"name": name, "ok": False, "count": 0,
                "error": f"未知 kind：{spec.get('kind')}（可选 {sorted(PARSERS)}）"}
    try:
        text = fetch(spec["url"], timeout, spec.get("headers"))
        items = parser(text, spec)[: spec.get("limit", 50)]
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        return {"name": name, "ok": False, "count": 0, "error": f"网络失败：{exc}"}
    except (ValueError, KeyError, ElementTree.ParseError) as exc:
        return {"name": name, "ok": False, "count": 0,
                "error": f"解析失败：{type(exc).__name__}: {exc}"}
    return {"name": name, "ok": True, "count": len(items), "items": items,
            "weight": float(spec.get("weight", 1.0)),
            "ranked": bool(spec.get("ranked", spec.get("kind", "json") != "rss"))}


# ---------------------------------------------------------------- 聚类与打分

def bigrams(text):
    flat = re.sub(r"[\s\W_]+", "", text)
    return {flat[i:i + 2] for i in range(max(0, len(flat) - 1))}


def similar(left, right):
    a, b = bigrams(left), bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def cluster(entries, threshold):
    """把不同榜单上说同一件事的条目并成一条。

    同一个事件在微博叫「某某回应」、在头条叫「某某事件始末」，不聚类就会得到
    一份看着很长其实全是重复的清单，人还得自己再去重一遍。
    """
    groups = []
    for entry in entries:
        for group in groups:
            if similar(entry["title"], group["title"]) >= threshold:
                group["members"].append(entry)
                group["sources"].add(entry["source"])
                if entry["rank"] < group["best_rank"]:
                    group["best_rank"] = entry["rank"]
                    group["title"] = entry["title"]
                break
        else:
            groups.append({
                "title": entry["title"], "members": [entry],
                "sources": {entry["source"]}, "best_rank": entry["rank"],
            })
    return groups


def score_group(group, include, exclude, max_rank):
    """跨榜出现 > 关键词命中 > 榜内排名。三项都可解释，不做黑盒加权。"""
    titles = " ".join(m["title"] for m in group["members"])
    if any(word and word in titles for word in exclude):
        return None
    cross = min(len(group["sources"]), 3)
    cross_score = 40.0 * cross / 3
    hits = [word for word in include if word and word in titles]
    keyword_score = 30.0 if hits else 0.0
    # RSS 是按时间倒序发的，不是按热度排的。拿「第几条」当热度用会让任何一个
    # 高频更新的科技站永远霸占榜首——它只是发得勤，不是这条更热。
    ranked = any(m.get("ranked", True) for m in group["members"])
    if ranked:
        rank_score = 30.0 * max(0.0, 1 - group["best_rank"] / max(1, max_rank))
    else:
        rank_score = 15.0
    weight = max(m.get("weight", 1.0) for m in group["members"])
    total = (cross_score + keyword_score + rank_score) * weight
    reasons = [f"{len(group['sources'])} 个榜单同时在说"]
    reasons.append(f"最好排名第 {group['best_rank'] + 1}" if ranked else "时间线来源，不计排名")
    if hits:
        reasons.append("命中关注词：" + "、".join(hits[:4]))
    return round(min(100.0, total), 1), reasons, sorted(group["sources"])


# 三个切入角模板。给角度而不是给成稿——选题的判断权留在人手里，
# 但「这条能怎么写」不该让用户从零开始想。
ANGLES = [
    "机制拆解：这件事**具体是怎么运转的**？谁按了哪个按钮、哪一步出了错、"
    "通稿里被形容词盖住的那个动作是什么。",
    "代价与责任：**谁承担后果**？成本落在哪个岗位、哪笔预算、哪个人的工时上。"
    "情绪要钉在权限、验收、签字这些可核验的东西上。",
    "判断标准：读者看完**能拿走什么判断**？什么情况下该跟进、什么情况下"
    "这事和你无关。给边界，别给口号。",
]


# ---------------------------------------------------------------- 主流程

def load_config(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"读不到配置：{exc}")
    except ValueError as exc:
        raise SystemExit(f"配置不是合法 JSON：{exc}")


def run(config, args):
    radar = config.get("hot_topic_radar", {})
    if not radar.get("enabled") and not args.force:
        return {
            "status": "disabled",
            "reason": "热点雷达是默认关闭的开关，仓库默认走「用户命题」模式。",
            "how_to_enable": [
                f"永久打开：把 {args.config} 里 "
                "hot_topic_radar.enabled 改成 true",
                "只试一次：给本命令加 --force（不改配置，下次仍然是关的）",
            ],
            "candidates": [],
        }

    specs = [s for s in radar.get("sources", []) if s.get("enabled", True)]
    if not specs:
        return {"status": "empty", "reason": "配置里没有启用任何数据源",
                "candidates": []}

    timeout = args.timeout or radar.get("timeout_seconds", 8)
    with ThreadPoolExecutor(max_workers=min(8, len(specs))) as pool:
        results = list(pool.map(lambda s: pull_source(s, timeout), specs))

    entries = []
    max_rank = 1
    for result in results:
        if not result.get("ok"):
            continue
        for rank, title in enumerate(result["items"]):
            entries.append({"title": title, "source": result["name"],
                            "rank": rank, "weight": result["weight"],
                            "ranked": result["ranked"]})
            max_rank = max(max_rank, rank + 1)

    include = radar.get("keywords_include", [])
    exclude = radar.get("keywords_exclude", [])
    groups = cluster(entries, radar.get("cluster_threshold", 0.45))

    candidates = []
    for group in groups:
        scored = score_group(group, include, exclude, max_rank)
        if scored is None:
            continue
        score, reasons, sources = scored
        if score < radar.get("min_score", 30):
            continue
        candidates.append({
            "title": group["title"],
            "score": score,
            "sources": sources,
            "why": reasons,
            "aliases": sorted({m["title"] for m in group["members"]}
                              - {group["title"]})[:4],
            "angles": ANGLES,
        })
    candidates.sort(key=lambda c: (-c["score"], c["title"]))
    # 单一来源限额：不加这条，一个高频更新的科技站能把整张清单占满，
    # 而清单的价值恰恰在于「今天有哪几件不同的事」。跨榜条目不受限。
    limit_per_source = radar.get("max_per_source", 3)
    wanted = args.top or radar.get("top_n", 8)
    used, top = {}, []
    for item in candidates:
        if len(item["sources"]) == 1:
            source = item["sources"][0]
            if used.get(source, 0) >= limit_per_source:
                continue
            used[source] = used.get(source, 0) + 1
        top.append(item)
        if len(top) >= wanted:
            break

    failed = [{"name": r["name"], "error": r["error"]}
              for r in results if not r.get("ok")]
    return {
        "status": "ok" if top else "empty",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"),
        "sources": [{"name": r["name"], "ok": r.get("ok", False),
                     "count": r.get("count", 0)} for r in results],
        "failed_sources": failed,
        "total_entries": len(entries),
        "candidates": top,
        "next": (
            "这份清单是给人看的，不是给流水线自动消费的。"
            "选中一条之后：把它写成 user-brief.md（主题 + 你自己的判断 + 必须写到的点），"
            "再跑 wechat-content-pipeline 的 init。"
            "**不要**把候选标题原样当选题——榜单标题是新闻标签，不是你的观点。"
        ),
    }


def render_markdown(result):
    if result["status"] == "disabled":
        lines = ["# 热点雷达：未开启", "", result["reason"], ""]
        lines += [f"- {item}" for item in result["how_to_enable"]]
        return "\n".join(lines)
    lines = [f"# 今日选题候选（{result.get('generated_at', '')}）", ""]
    ok = [s for s in result.get("sources", []) if s["ok"]]
    lines.append(
        f"数据源 {len(ok)}/{len(result.get('sources', []))} 可用，"
        f"共 {result.get('total_entries', 0)} 条，聚类后取前 {len(result['candidates'])} 条。"
    )
    for failure in result.get("failed_sources", []):
        lines.append(f"- ⚠️ {failure['name']}：{failure['error']}")
    lines.append("")
    if not result["candidates"]:
        lines.append("今天没有达到分数线的候选。**这也是一个结论**："
                     "没有值得写的热点时，不要硬写——回到用户命题模式。")
        return "\n".join(lines)
    for index, item in enumerate(result["candidates"], start=1):
        lines.append(f"## {index}. {item['title']}　`{item['score']}`")
        lines.append(f"- 上榜：{'、'.join(item['sources'])}")
        lines.append(f"- 理由：{'；'.join(item['why'])}")
        if item["aliases"]:
            lines.append(f"- 别名：{' / '.join(item['aliases'])}")
        lines.append("- 可选切入角：")
        lines += [f"  {i}. {angle}" for i, angle in enumerate(item["angles"], start=1)]
        lines.append("")
    lines.append(f"下一步：{result['next']}")
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description="热点雷达（默认关闭的开关）：聚合公开榜单，产出可写的选题候选",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help="writer-config.json 路径")
    parser.add_argument("--force", action="store_true",
                        help="忽略配置开关跑一次（不改配置）")
    parser.add_argument("--top", type=int, help="输出条数，覆盖配置里的 top_n")
    parser.add_argument("--timeout", type=int, help="单个数据源超时秒数")
    parser.add_argument("--markdown", action="store_true", help="输出给人看的清单")
    parser.add_argument("--out", help="把 JSON 结果另存到这个路径")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    try:
        result = run(config, args)
    except Exception as exc:  # noqa: BLE001 - 雷达挂掉不该拖垮调用方
        result = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}",
                  "candidates": []}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(render_markdown(result) if args.markdown
          else json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
