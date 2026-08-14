#!/usr/bin/env python3
"""稿件体检：把「信息量 / 利他性 / 可读性 / 抓人」四件事变成可执行的确定性检查。

为什么要有这个脚本
------------------
流水线里的 `pipeline_runtime.py check` 管的是**结构合法性**——标题几个、字数够不够、
图片路径越没越界。它不会告诉你「第 7 段连着 480 字没有一个具体信息，读者在这里流失」。
而公众号真正的胜负手恰恰在后者：2026 年公众号推荐把**完读率**抬成第一权重指标，
读者点开后读不到 30% 就退出会被判低质（第三方运营号的实测结论，非官方口径，
出处见 references/distribution-2026.md）。

「文章好不好」不能靠模型自己感觉。模型会觉得自己写得很好——这是它的系统性偏差。
所以这里把可量化的部分全部量化：价值锚间距、段落长度分布、钩子密度、利他物是否存在。
剩下不可量化的部分（观点是否真的成立、情绪是否真诚）留给人和 references。

设计原则（和本仓库其余脚本一致）
--------------------------------
- **退出码恒为 0**（除非命令行参数非法）：体检不合格是结果，不是故障。
- stdout 只有一行 JSON，机器可读；`--markdown` 才给人看。
- 每条问题都带 `fix`：告诉模型**怎么改**，而不是只说「不够好」。
- 阈值全部集中在 THRESHOLDS，可被 `--config` 覆盖，不散落在代码里。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 阈值

THRESHOLDS = {
    # 正文长度（与流水线硬门禁保持一致，这里只做提示不做拦截）
    "body_min": 1500,
    "body_max": 4000,
    # 标题
    "title_max": 32,
    "title_sting_window": 16,
    # 开头：进入正题之前允许的铺垫字数。超过就是在浪费最贵的那 3 秒。
    "lede_max_chars": 150,
    # 价值锚：每多少字至少要有一个具体信息（数字/对比/因果/结论/小标题）
    "anchor_gap_max": 300,
    # 钩子：每多少字至少要有一次转折/悬念/提问，把读者拽向下一段
    "hook_gap_max": 500,
    # 段落：微信是竖屏手机阅读，长段落是完读率杀手
    "para_soft_max": 180,
    "para_hard_max": 260,
    "para_long_ratio_max": 0.25,
    # 句子
    "sentence_long_chars": 50,
    "sentence_long_ratio_max": 0.20,
    # 小标题密度：平均每多少字应有一个 ## 小标题
    "heading_gap_max": 800,
    # 加粗关键短语：够长的段落里每段 1—3 个
    "bold_para_min_chars": 60,
    "bold_per_para_max": 3,
    # 注水词密度（每千字）
    "filler_per_kchars_max": 4.0,
    # 及格线
    "pass_score": 75,
    # 中文手机阅读速度（字/分钟），用来估算阅读时长
    "read_speed": 400,
}

# ---------------------------------------------------------------- 词表

# 价值锚：读者能「带走」的具体信息落点。
ANCHOR_PATTERNS = [
    (r"\d+(?:\.\d+)?\s*(?:%|％|倍|万|亿|千|百|块|元|美元|人|天|小时|分钟|秒|年|月|周|次|个|条|张|页|字|行|k|K|w|W)", "数字"),
    (r"(?:19|20)\d{2}\s*年", "年份"),
    (r"不是[^，。；！？]{1,20}(?:，|、)?而是", "对比"),
    (r"(?:比|相比|相对于)[^，。；！？]{1,20}(?:更|还要|少|多|快|慢|贵|便宜|高|低)", "对比"),
    (r"(?:区别|差别|不同)(?:在于|是|就在)", "对比"),
    (r"(?:恰恰相反|反过来说|反过来|换个方向)", "对比"),
    (r"(?:原因是|因为|之所以|导致|意味着|本质上是|结果就是|所以才)", "因果"),
    (r"(?:官方|文档|公告|财报|白皮书|源码|接口|API|SDK)", "信源"),
    # 外文专名（产品名、公司名、技术名）本身就是信息落点：读者能拿它去搜索。
    # 早期版本漏了这一条，导致「英特尔披露的重点是用 Google Cloud 补算力」这种
    # 有实质信息的句子被判成空段。
    (r"[A-Za-z][A-Za-z0-9+.#_-]{1,}", "外文专名"),
    (r"[「『“《][^」』”》]{2,24}[」』”》]", "引述"),
]

# 标题刺点：光有个外文品牌名不算刺点，得有让人「非点开不可」的那一下。
# 单列一套而不是复用 ANCHOR_PATTERNS，是因为标题的判据比正文严得多——
# 正文里出现「Google Cloud」是信息，标题里出现「Google Cloud」只是名词。
TITLE_STING_PATTERNS = [
    r"\d",
    # 中文数字量词：「三条判断」「五个坑」和「3 条判断」是同一种刺点，
    # 只认阿拉伯数字会漏掉一半的中文标题。
    r"[一二三四五六七八九十百千万两]\s*(?:条|个|种|点|步|招|年|天|次|倍|成|块|周|月|分钟|小时)",
    r"不是[^，。]{1,20}(?:，|、)?而是",
    r"(?:比|相比)[^，。]{1,16}(?:更|还|少|多|快|慢|贵|便宜)",
    r"[?？！!]",
    r"(?:别|不要|不用|没必要|未必|根本|其实不|不值得|先别)",
    r"(?:坑|翻车|踩雷|白干|白忙|亏|代价|后果|真相|误会|想错|搞错|错在)",
    r"(?:如果你|普通人|新手|老板|打工人|程序员|做号|中小)",
    r"(?:怎么选|该不该|要不要|值不值|能不能|凭什么|为什么)",
]

# 可指认的主体：读者在推荐页**只看得到标题**。一个只有判断、没有主语的标题
# （「省下的 90% 成本没有消失，它原来是某个人的工资」）读起来很有力，但读者
# 说不出这写的是谁、哪件事，于是不会点。刺点解决「想不想点」，主体解决
# 「知不知道这是什么」——两者缺一不可，早期版本只查了前者。
#
# ⚠️ 这套正则认不出所有主体（比如「多智能体」这种没有外文、没有量词的技术名词
# 就会被漏判）。所以它是 medium 级提醒，不是硬拦；命中时人工确认一下即可。
SUBJECT_SIGNALS = [
    r"[A-Za-z][A-Za-z0-9+.#_-]{1,}",
    r"[《【「『][^》】」』]{1,20}[》】」』]",
    r"[\d一二三四五六七八九十两几百千万]+\s*"
    r"(?:人|万|亿|部|家|台|款|条|位|名|场|次|元|块|岁|届|届生|城|省|市)",
    r"(?:群演|演员|编剧|导演|工程师|程序员|老师|医生|护士|司机|骑手|主播|"
    r"员工|新人|应届生|求职者|老板|甲方|客户|用户|读者|作者|运营|销售|"
    r"运维|测试|设计师|翻译|会计|律师|农民|工人|学生|家长|老人|保安|快递)",
    r"(?:公司|大学|医院|法院|银行|工厂|车间|门店|机场|车站|小区|食堂|车间|园区)",
    r"[一-龥]{2,4}(?:市|省|县|区|镇|村|店|厂|园|局|院|所|队|团|网|报|台|社)(?![一-龥])",
]

# 泛指代词：标题里出现这些又找不到主体，基本可以确定读者不知道你在说什么。
VAGUE_REFERENTS = (
    r"(?:它们|它|他们|某个人|某些人|某个|某些|这一切|一切|这件事|那件事|"
    r"这东西|某种东西|这类事|那些人)"
)

# 钩子：把读者从这一段拽进下一段的力。
HOOK_PATTERNS = [
    r"(?:但是|但|然而|可是|不过)",
    r"(?:问题是|麻烦在于|要命的是|更要命|更糟的是|坑就在)",
    r"(?:你可能会问|你可能觉得|你也许会说|别急|先别)",
    r"(?:我一开始也|我原本以为|我以为|结果发现|后来才知道)",
    r"(?:反直觉|反常识|听起来|听上去)",
    r"(?:关键在于|真正的问题|真正要命的)",
    r"[^。！\n]{4,40}[？?]\n?",
]

# 利他物：读者读完能拿走的东西。没有这个，文章就是「白看一场」。
BENEFIT_PATTERNS = [
    (r"(?:怎么选|如何选|该选|选哪个|怎么判断|如何判断|判断标准|怎么看)", "判断标准"),
    (r"(?:什么时候(?:用|该用|别用|不要用|适合))", "适用边界"),
    (r"(?:如果你(?:是|在|要|正))", "对号入座"),
    (r"(?:避坑|别踩|不要犯|常见错误|最容易错的)", "避坑"),
    (r"(?:第一步|第二步|先做|再做|最后做|照着做|直接抄)", "可执行步骤"),
    (r"^\s*(?:[-*+]|\d+[.、)])\s+", "清单"),
    (r"(?:前提是|边界是|只在|仅当|除非)", "边界条件"),
    (r"(?:一句话|总结成一句|记住这条|结论先说|结论是)", "可带走结论"),
    (r"(?:带走|拿走|抄走|存下来)", "可带走结论"),
    (r"(?:下次|以后|从今天起|从现在开始|从明天)", "可执行步骤"),
]

# 注水词：占字数但不增信息。命中多说明在凑长度。
FILLER_WORDS = [
    "众所周知", "不难看出", "不难发现", "毫无疑问", "值得一提的是", "值得注意的是",
    "总而言之", "综上所述", "总的来说", "总体而言", "在一定程度上", "某种意义上",
    "我们可以看到", "我们知道", "大家都知道", "可以说是", "不得不说",
    "在当今", "随着社会的发展", "随着科技的发展", "随着时代",
]

# 套话开场：前 30 字撞上这些，等于把最贵的三秒扔了。
CLICHE_OPENERS = [
    r"^在当今", r"^随着[^，。]{0,12}(?:的)?(?:发展|进步|到来|普及)",
    r"^近年来", r"^众所周知", r"^如今[，,]", r"^在这个[^，。]{0,10}的时代",
    r"^提到[^，。]{1,12}[，,]相信", r"^说起[^，。]{1,12}[，,]大家",
]
READING_CLICHE_OPENERS = [
    r"^最近在读", r"^最近读了", r"^读完了", r"^今天想聊聊这本书",
    r"^这本书(?:告诉|讲的是|让我|给了)", r"^作者在书中",
    r"^读完《", r"^合上这本书",
]
REVIEW_TITLE_RE = re.compile(r"读后感|书评|读书笔记|读《|荐书|读完")
CITE_RE = re.compile(r"[「『“][^」』”]{6,}[」』”]")

TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
FENCE_RE = re.compile(r"^\s*```")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.、)])\s+")
QUOTE_RE = re.compile(r"^\s*>\s?")
MD_NOISE_RE = re.compile(r"[*`_>#\[\]()!]|https?://\S+")
SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;…]+")


# ---------------------------------------------------------------- 解析

def strip_md(text):
    """去掉 Markdown 噪音，只留读者眼睛真正看到的字。"""
    text = IMAGE_RE.sub("", text)
    text = BOLD_RE.sub(r"\1", text)
    text = MD_NOISE_RE.sub("", text)
    return text.strip()


def parse_blocks(article):
    """把 Markdown 切成带行号的块。行号是给人看的——问题必须能定位到具体位置。"""
    blocks = []
    in_fence = False
    buffer, buffer_line = [], 0
    for index, raw in enumerate(article.splitlines(), start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = raw.rstrip()
        if not line.strip():
            if buffer:
                blocks.append({"kind": "para", "line": buffer_line,
                               "raw": "\n".join(buffer)})
                buffer = []
            continue
        title_match = TITLE_RE.match(line)
        heading_match = HEADING_RE.match(line)
        if title_match or heading_match:
            if buffer:
                blocks.append({"kind": "para", "line": buffer_line,
                               "raw": "\n".join(buffer)})
                buffer = []
            kind = "h1" if title_match else "h2"
            body = (title_match or heading_match).group(1 if title_match else 2)
            blocks.append({"kind": kind, "line": index, "raw": body})
            continue
        if IMAGE_RE.fullmatch(line.strip()):
            if buffer:
                blocks.append({"kind": "para", "line": buffer_line,
                               "raw": "\n".join(buffer)})
                buffer = []
            blocks.append({"kind": "image", "line": index, "raw": line})
            continue
        if not buffer:
            buffer_line = index
        buffer.append(line)
    if buffer:
        blocks.append({"kind": "para", "line": buffer_line, "raw": "\n".join(buffer)})

    for block in blocks:
        block["text"] = strip_md(block["raw"])
        block["chars"] = len(re.sub(r"\s+", "", block["text"]))
        block["is_list"] = bool(LIST_RE.match(block["raw"].lstrip()))
        block["is_quote"] = bool(QUOTE_RE.match(block["raw"].lstrip()))
    return blocks


def body_stream(blocks):
    """把正文拼成一条连续的字符流，并记住每个字来自哪个块。

    价值锚间距、钩子间距都是「沿着读者的阅读顺序」度量的，所以必须先有这条流。
    小标题算正文的一部分（读者确实会读到），但 h1 和图片不算。
    """
    stream, origins, offsets = [], [], {}
    cursor = 0
    for position, block in enumerate(blocks):
        if block["kind"] in ("h1", "image"):
            continue
        text = re.sub(r"\s+", "", block["text"])
        if not text:
            continue
        offsets[position] = cursor
        cursor += len(text)
        stream.append(text)
        origins.extend([position] * len(text))
    return "".join(stream), origins, offsets


def structural_anchors(blocks, offsets):
    """小标题和加粗短语本身就是价值锚，但它们的标记在 strip_md 里已经被抹掉了。

    所以要按块回填偏移量：小标题落在块首，加粗短语落在它在块内文本中的位置。
    漏掉这一步的后果是「作者已经明确标记了重点」的段落反而被判成空段。
    """
    found = []
    for position, block in enumerate(blocks):
        if position not in offsets:
            continue
        base = offsets[position]
        if block["kind"] == "h2":
            found.append(base)
            continue
        flat = re.sub(r"\s+", "", block["text"])
        for phrase in BOLD_RE.findall(block["raw"]):
            needle = re.sub(r"\s+", "", strip_md(phrase))
            if not needle:
                continue
            index = flat.find(needle)
            if index >= 0:
                found.append(base + index)
    return found


def marker_positions(text, patterns):
    """返回所有命中位置（去重排序）。patterns 可以是纯正则串，也可以是 (正则, 标签)。"""
    found = []
    for item in patterns:
        pattern = item[0] if isinstance(item, tuple) else item
        for match in re.finditer(pattern, text, re.MULTILINE):
            found.append(match.start())
    return sorted(set(found))


def worst_gap(positions, total_chars):
    """最长的一段「什么都没发生」的区间，返回 (长度, 起点)。

    注意首尾也算：开头 400 字没有任何价值锚，和中间 400 字没有一样致命。
    """
    if total_chars <= 0:
        return 0, 0
    edges = [0] + list(positions) + [total_chars]
    span, start = 0, 0
    for left, right in zip(edges, edges[1:]):
        if right - left > span:
            span, start = right - left, left
    return span, start


def locate(origins, offset, blocks):
    """把字符流上的偏移量翻译成「第几行」，让问题可以被直接点开。"""
    if not origins:
        return 0
    index = min(max(offset, 0), len(origins) - 1)
    return blocks[origins[index]]["line"]


def ratio_score(value, good, bad):
    """把一个「越小越好」的比值线性映射到 0—1。good 及以下满分，bad 及以上零分。"""
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return (bad - value) / (bad - good)


# ---------------------------------------------------------------- 各维度

def check_hook(blocks, stream, origins, thresholds, problems, genre="insight"):
    """开头 20 分：标题 + 前 150 字。这是转化漏斗最窄的地方，单独拎出来打分。"""
    notes, score = [], 20.0
    titles = [b for b in blocks if b["kind"] == "h1"]
    if not titles:
        problems.append({
            "dim": "hook", "severity": "high", "line": 1,
            "what": "没有一级标题",
            "fix": "第一行写 `# 标题`，其余层级用 ##",
        })
        score -= 8
        title = ""
    else:
        title = re.sub(r"\s+", "", titles[0]["text"])
        notes.append(f"标题 {len(title)} 字")
        if len(title) > thresholds["title_max"]:
            problems.append({
                "dim": "hook", "severity": "high", "line": titles[0]["line"],
                "what": f"标题 {len(title)} 字，超过 {thresholds['title_max']} 字",
                "fix": "砍到 32 字内。列表页只稳定展示前 16 字左右，把刺点提到最前面",
            })
            score -= 5
        window = title[: thresholds["title_sting_window"]]
        if not marker_positions(window, TITLE_STING_PATTERNS):
            problems.append({
                "dim": "hook", "severity": "medium", "line": titles[0].get("line", 1),
                "what": f"标题前 {thresholds['title_sting_window']} 字没有锚点（数字/对比/断言/疑问）",
                "fix": "把最刺的那半句提到前面：具体数字、"
                       "「不是 A 而是 B」的反差、或一句得罪人的断言。"
                       "读者在信息流里只看得见前半截",
            })
            score -= 4
        if len(title) < 10:
            problems.append({
                "dim": "hook", "severity": "low", "line": titles[0]["line"],
                "what": f"标题只有 {len(title)} 字，信息量不足",
                "fix": "补一个具体锚点（谁、多少、代价是什么）",
            })
            score -= 2
        if genre == "reading" and REVIEW_TITLE_RE.search(title):
            problems.append({
                "dim": "hook", "severity": "high", "line": titles[0]["line"],
                "what": "标题写成了书评/读后感",
                "fix": "标题只写判断或现象，书名不要进标题。"
                       "例如不要「读《穷查理宝典》有感」，写「手里只有一把锤子时」",
            })
            score -= 6

    lede = stream[: thresholds["lede_max_chars"]]
    openers = list(CLICHE_OPENERS)
    if genre == "reading":
        openers.extend(READING_CLICHE_OPENERS)
    for pattern in openers:
        if re.search(pattern, lede):
            problems.append({
                "dim": "hook", "severity": "high",
                "line": locate(origins, 0, blocks),
                "what": "开头是套话铺垫（「在当今 / 随着……的发展」这一类）",
                "fix": "删掉第一句，直接从具体场景、具体数字或一句反常识断言开始。"
                       "读者划到你的前 30 字只给 3 秒",
            })
            score -= 5
            break

    anchors = marker_positions(lede, ANCHOR_PATTERNS)
    first_anchor = anchors[0] if anchors else None
    if first_anchor is None:
        problems.append({
            "dim": "hook", "severity": "high",
            "line": locate(origins, 0, blocks),
            "what": f"前 {thresholds['lede_max_chars']} 字里没有任何具体信息，全是铺垫",
            "fix": "把文章里最硬的那个事实（数字、冲突、代价）搬到开头 100 字内。"
                   "先给结论再给背景，不要先给背景",
        })
        score -= 6
    else:
        notes.append(f"第 {first_anchor + 1} 字进入正题")
    return max(0.0, score), notes


def check_value_density(blocks, stream, origins, offsets, thresholds, problems):
    """信息量 25 分：读者每读 300 字，必须换到一个新的具体信息。"""
    notes, score = [], 25.0
    total = len(stream)
    anchors = sorted(set(
        marker_positions(stream, ANCHOR_PATTERNS)
        + structural_anchors(blocks, offsets)
    ))
    density = len(anchors) / max(1, total / 1000)
    notes.append(f"价值锚 {len(anchors)} 处（每千字 {density:.1f}）")

    gap, start = worst_gap(anchors, total)
    if gap > thresholds["anchor_gap_max"]:
        severity = "high" if gap > thresholds["anchor_gap_max"] * 1.6 else "medium"
        problems.append({
            "dim": "value_density", "severity": severity,
            "line": locate(origins, start, blocks),
            "what": f"连续 {gap} 字没有具体信息（阈值 {thresholds['anchor_gap_max']} 字）",
            "fix": "在这一段里塞进至少一个：具体数字、"
                   "「不是 A 而是 B」的对比、一条因果链，或点名一个可核实的信源。"
                   "如果塞不进去，说明这一段本来就没内容，直接删",
        })
        score -= 9 if severity == "high" else 5
    notes.append(f"最长无锚区间 {gap} 字")

    filler_hits = []
    for word in FILLER_WORDS:
        for match in re.finditer(re.escape(word), stream):
            filler_hits.append((match.start(), word))
    per_k = len(filler_hits) / max(1.0, total / 1000)
    notes.append(f"注水词 {len(filler_hits)} 处（每千字 {per_k:.1f}）")
    if per_k > thresholds["filler_per_kchars_max"]:
        worst = sorted({w for _, w in filler_hits})[:5]
        problems.append({
            "dim": "value_density", "severity": "medium",
            "line": locate(origins, filler_hits[0][0], blocks),
            "what": f"注水词每千字 {per_k:.1f} 处，超过 {thresholds['filler_per_kchars_max']}",
            "fix": f"删掉这类词并把句子改实：{'、'.join(worst)}。"
                   "「众所周知」后面那句如果真的众所周知，就该删；如果不是，就该给出处",
        })
        score -= 5

    paras = [b for b in blocks if b["kind"] == "para" and b["chars"] >= 40]
    duplicated = []
    for left, right in zip(paras, paras[1:]):
        similarity = trigram_similarity(left["text"], right["text"])
        if similarity > 0.55:
            duplicated.append((right["line"], similarity))
    if duplicated:
        line, similarity = duplicated[0]
        problems.append({
            "dim": "value_density", "severity": "medium", "line": line,
            "what": f"和上一段重复度 {similarity:.0%}（共 {len(duplicated)} 处）",
            "fix": "两段说的是同一件事，合并成一段，或者给第二段换一个新角度/新证据",
        })
        score -= 4
    return max(0.0, score), notes


def trigram_similarity(left, right):
    """字符三元组 Jaccard——够用的「这两段是不是在说同一件事」判据，且完全确定。"""
    def grams(text):
        text = re.sub(r"\s+", "", text)
        return {text[i:i + 3] for i in range(max(0, len(text) - 2))}
    a, b = grams(left), grams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def check_reader_benefit(blocks, stream, origins, thresholds, problems):
    """利他性 20 分：读者读完能带走什么？带不走 = 白看一场。"""
    notes, score = [], 20.0
    kinds = set()
    positions = []
    for pattern, label in BENEFIT_PATTERNS:
        for match in re.finditer(pattern, stream, re.MULTILINE):
            kinds.add(label)
            positions.append(match.start())
    # 清单形态要按块判定：拼接后的字符流里没有行首
    if any(b["is_list"] for b in blocks):
        kinds.add("清单")
    notes.append("利他物：" + ("、".join(sorted(kinds)) if kinds else "无"))

    if not kinds:
        problems.append({
            "dim": "reader_benefit", "severity": "high",
            "line": locate(origins, 0, blocks),
            "what": "全文没有任何读者可以带走的东西",
            "fix": "至少补一种：①判断标准（什么情况该选 A）②适用边界（什么时候别用）"
                   "③可执行步骤 ④一句可转述的结论。注意按题材选形态——"
                   "历史复盘就给清楚的事实线与结局，别硬塞「普通人怎么防」",
        })
        score -= 12
    elif len(kinds) == 1:
        problems.append({
            "dim": "reader_benefit", "severity": "medium",
            "line": locate(origins, positions[0] if positions else 0, blocks),
            "what": f"利他物只有一种（{next(iter(kinds))}），读者拿走的东西太薄",
            "fix": "再加一种不同形态：有了判断标准就补边界条件，有了清单就补一句可转述的结论",
        })
        score -= 5

    tail_start = int(len(stream) * 0.75)
    tail = stream[tail_start:]
    if tail and not any(re.search(p, tail, re.MULTILINE) for p, _ in BENEFIT_PATTERNS):
        problems.append({
            "dim": "reader_benefit", "severity": "medium",
            "line": locate(origins, tail_start, blocks),
            "what": "最后四分之一没有任何落点，结尾在空转",
            "fix": "结尾必须收回到读者身上：一句可以直接转述给同事的结论，"
                   "或一个明确的「如果你是 X，就 Y」。别用「让我们拭目以待」收尾",
        })
        score -= 5

    bold_phrases = BOLD_RE.findall("\n".join(b["raw"] for b in blocks))
    notes.append(f"加粗关键短语 {len(bold_phrases)} 处")
    if not bold_phrases:
        problems.append({
            "dim": "reader_benefit", "severity": "medium", "line": 1,
            "what": "全文没有加粗，扫读的人抓不到任何东西",
            "fix": "每段挑 1—3 个**关键短语**加粗。加粗的必须是判断和结论，不是形容词",
        })
        score -= 4
    return max(0.0, score), notes


def check_readability(blocks, thresholds, problems):
    """可读性 20 分：竖屏手机上，段落长度和句子长度直接决定有没有人读得下去。"""
    notes, score = [], 20.0
    paras = [b for b in blocks if b["kind"] == "para" and b["chars"] > 0]
    if not paras:
        return 0.0, ["无正文段落"]

    long_paras = [b for b in paras if b["chars"] > thresholds["para_soft_max"]]
    huge_paras = [b for b in paras if b["chars"] > thresholds["para_hard_max"]]
    long_ratio = len(long_paras) / len(paras)
    notes.append(
        f"段落 {len(paras)} 段，均 {sum(b['chars'] for b in paras) // len(paras)} 字，"
        f"超长 {len(long_paras)} 段"
    )
    if huge_paras:
        problems.append({
            "dim": "readability", "severity": "high", "line": huge_paras[0]["line"],
            "what": f"有 {len(huge_paras)} 个段落超过 {thresholds['para_hard_max']} 字"
                    f"（最长 {max(b['chars'] for b in huge_paras)} 字）",
            "fix": "在手机上这是一整屏黑压压的字。按语义切成 2—3 段，"
                   "每段只讲一件事，一段一个呼吸",
        })
        score -= 6
    elif long_ratio > thresholds["para_long_ratio_max"]:
        problems.append({
            "dim": "readability", "severity": "medium", "line": long_paras[0]["line"],
            "what": f"{long_ratio:.0%} 的段落超过 {thresholds['para_soft_max']} 字",
            "fix": f"把超过 {thresholds['para_soft_max']} 字的段落拆开，"
                   "目标是大部分段落落在 60—150 字",
        })
        score -= 4
    else:
        score -= 4 * (1 - ratio_score(long_ratio, 0.10,
                                      thresholds["para_long_ratio_max"]))

    sentences = []
    for block in paras:
        for piece in SENTENCE_SPLIT_RE.split(block["text"]):
            piece = re.sub(r"\s+", "", piece)
            if piece:
                sentences.append((len(piece), block["line"]))
    if sentences:
        avg = sum(n for n, _ in sentences) / len(sentences)
        longs = [(n, line) for n, line in sentences
                 if n > thresholds["sentence_long_chars"]]
        long_sentence_ratio = len(longs) / len(sentences)
        notes.append(f"平均句长 {avg:.0f} 字，长句占比 {long_sentence_ratio:.0%}")
        if long_sentence_ratio > thresholds["sentence_long_ratio_max"]:
            worst = max(longs)
            problems.append({
                "dim": "readability", "severity": "medium", "line": worst[1],
                "what": f"{long_sentence_ratio:.0%} 的句子超过 "
                        f"{thresholds['sentence_long_chars']} 字（最长 {worst[0]} 字）",
                "fix": "长句拆短句。中文口语的节奏是短句推进、偶尔一个长句作缓冲，"
                       "反过来就变成公文",
            })
            score -= 4
        else:
            score -= 4 * (1 - ratio_score(long_sentence_ratio, 0.08,
                                          thresholds["sentence_long_ratio_max"]))

    headings = [b for b in blocks if b["kind"] == "h2"]
    body_chars = sum(b["chars"] for b in paras)
    notes.append(f"小标题 {len(headings)} 个")
    expected = max(1, round(body_chars / thresholds["heading_gap_max"]))
    if len(headings) < expected:
        problems.append({
            "dim": "readability", "severity": "medium",
            "line": paras[min(len(paras) - 1, 3)]["line"],
            "what": f"正文 {body_chars} 字只有 {len(headings)} 个小标题，"
                    f"建议至少 {expected} 个",
            "fix": "每 500—800 字给一个 ## 小标题。小标题要能单独读懂，"
                   "本身就是一句结论，不要写「背景介绍」这种目录词",
        })
        score -= 3

    # 清单块天然会有多个加粗（每个条目一个），不该按普通段落的上限判。
    over_bold = [b for b in paras
                 if not b["is_list"]
                 and len(BOLD_RE.findall(b["raw"])) > thresholds["bold_per_para_max"]]
    naked = [b for b in paras
             if b["chars"] >= thresholds["bold_para_min_chars"]
             and not BOLD_RE.search(b["raw"]) and not b["is_list"]]
    if over_bold:
        problems.append({
            "dim": "readability", "severity": "low", "line": over_bold[0]["line"],
            "what": f"有 {len(over_bold)} 段加粗超过 {thresholds['bold_per_para_max']} 处",
            "fix": "全都加粗等于全都没加粗。每段只留最该被记住的那 1—2 句",
        })
        score -= 2
    if len(naked) > len(paras) * 0.6:
        problems.append({
            "dim": "readability", "severity": "low", "line": naked[0]["line"],
            "what": f"{len(naked)}/{len(paras)} 个长段落一个加粗都没有",
            "fix": "给扫读的人留抓手：每个较长段落挑 1 个**关键短语**加粗",
        })
        score -= 2
    return max(0.0, score), notes


def check_retention(blocks, stream, origins, thresholds, problems):
    """抓人 15 分：读者是被一次次「下一句是什么」拽着往下走的。"""
    notes, score = [], 15.0
    total = len(stream)
    hooks = marker_positions(stream, HOOK_PATTERNS)
    notes.append(f"钩子 {len(hooks)} 处（每千字 {len(hooks) / max(1, total / 1000):.1f}）")

    gap, start = worst_gap(hooks, total)
    notes.append(f"最长无钩区间 {gap} 字")
    if gap > thresholds["hook_gap_max"]:
        severity = "high" if gap > thresholds["hook_gap_max"] * 1.6 else "medium"
        problems.append({
            "dim": "retention", "severity": severity,
            "line": locate(origins, start, blocks),
            "what": f"连续 {gap} 字平铺直叙，没有转折/悬念/提问"
                    f"（阈值 {thresholds['hook_gap_max']} 字）",
            "fix": "在这一段收尾处埋一次转向：一句「但问题是……」、"
                   "一个把读者代入的提问、或一个和上文相反的事实。"
                   "读者会在平铺的第三屏退出",
        })
        score -= 7 if severity == "high" else 4

    questions = len(re.findall(r"[？?]", stream))
    if questions == 0:
        problems.append({
            "dim": "retention", "severity": "low",
            "line": locate(origins, 0, blocks),
            "what": "全文没有一个问句，读者始终是旁观者",
            "fix": "至少设一个把读者拉进来的问题：「如果这事落到你头上呢？」",
        })
        score -= 2

    paras = [b for b in blocks if b["kind"] == "para"]
    if paras:
        # 回扣不一定落在最后一段——很多好结尾是「倒数第三段点题、最后一段一句话收」。
        # 只看最后一段会把这种写法误判成没有闭环，所以按结尾 300 字整体判。
        opener, closer = stream[:80], stream[-300:]
        callback = recall_overlap(opener, closer)
        notes.append(f"结尾回扣开头 {callback:.0%}")
        if opener and closer and callback < 0.08:
            problems.append({
                "dim": "retention", "severity": "low",
                "line": paras[-1]["line"],
                "what": f"结尾对开头的回扣只有 {callback:.0%}，文章缺一个闭环",
                "fix": "结尾把开头那个场景/人物/数字再提一次并给出结论。"
                       "读者会因为「原来是这么回事」而愿意转发",
            })
            score -= 2
    return max(0.0, score), notes


def recall_overlap(opener, closer, size=2):
    """开头的字词有多少比例在结尾重新出现——比关键词提取稳，因为中文没有空格。

    早期版本用 `[一-龥]{2,8}` 正则「提词」，但贪婪匹配会把整句切成 8 字一块的
    无意义碎片，于是任何文章都被判成没有回扣。改成字符 n-gram 召回率之后，
    「开头讲的那个人/那个数字，结尾又提了一次」这件事才真的量得出来。
    """
    def grams(text):
        text = re.sub(r"\s+", "", text)
        return {text[i:i + size] for i in range(max(0, len(text) - size + 1))}
    head, tail = grams(opener), grams(closer)
    if not head:
        return 0.0
    return len(head & tail) / len(head)


# ---------------------------------------------------------------- 主流程

def grade_of(score):
    for bound, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if score >= bound:
            return letter
    return "E"


def check_reading_voice(blocks, stream, problems):
    """读书线额外门禁：必须是自己的判断 + 原句，不能是书评。"""
    notes, score = [], 0.0
    if not CITE_RE.search(stream):
        problems.append({
            "dim": "value_density", "severity": "high", "line": 1,
            "what": "全文没有引用书里的原句（需要「」或“”包住至少 6 个字）",
            "fix": "从 reading-slice.md 摘 1–3 句原话放进正文当证据，不要用「作者大概是想说」",
        })
    reviewish = len(re.findall(
        r"这本书值得|推荐大家|强烈推荐|必读书|读后感|金句打卡|作者生平",
        stream,
    ))
    if reviewish:
        problems.append({
            "dim": "reader_benefit", "severity": "medium", "line": 1,
            "what": "正文里有书评腔（推荐/必读/金句打卡/作者生平）",
            "fix": "删掉荐书句，改成「我会在哪个场合用错」或这个模型的边界",
        })
    return notes


def analyze(article, thresholds, genre="insight"):
    blocks = parse_blocks(article)
    stream, origins, offsets = body_stream(blocks)
    if not stream:
        # 空正文（只有标题、只有图、只有代码块）不该跑满分制——各维度的「没发现问题」
        # 会叠出一个 40 多分的假成绩，读起来像「写得一般」，而实际上什么都没有。
        return {
            "status": "fix", "score": 0.0, "grade": "E", "body_chars": 0,
            "read_seconds": 0, "dimensions": {}, "blocking_count": 1,
            "problems": [{
                "dim": "length", "severity": "high", "line": 1,
                "what": "没有正文（只有标题/图片/代码块）",
                "fix": "按 begin 输出的 writing_contract 写正文，"
                       f"目标 {thresholds['body_min']}—{thresholds['body_max']} 字",
            }],
            "next": "先写正文再体检",
        }
    problems = []
    dims = {}
    dims["hook"] = check_hook(
        blocks, stream, origins, thresholds, problems, genre=genre,
    ) + (20,)
    dims["value_density"] = check_value_density(
        blocks, stream, origins, offsets, thresholds, problems) + (25,)
    dims["reader_benefit"] = check_reader_benefit(
        blocks, stream, origins, thresholds, problems) + (20,)
    dims["readability"] = check_readability(blocks, thresholds, problems) + (20,)
    dims["retention"] = check_retention(
        blocks, stream, origins, thresholds, problems) + (15,)
    if genre == "reading":
        check_reading_voice(blocks, stream, problems)

    body_chars = len(stream)
    if body_chars < thresholds["body_min"]:
        problems.append({
            "dim": "length", "severity": "high", "line": 1,
            "what": f"正文 {body_chars} 字 < {thresholds['body_min']}（流水线硬门禁）",
            "fix": "补真实机制、人群、成本细节。禁止用注水词凑字数——"
                   "凑出来的字会在 value_density 上再扣一次",
        })
    elif body_chars > thresholds["body_max"]:
        problems.append({
            "dim": "length", "severity": "high", "line": 1,
            "what": f"正文 {body_chars} 字 > {thresholds['body_max']}（流水线硬门禁）",
            "fix": "先删重复段落和注水句，再删最弱的那个论点",
        })

    total = round(sum(value[0] for value in dims.values()), 1)
    order = {"high": 0, "medium": 1, "low": 2}
    problems.sort(key=lambda p: (order.get(p["severity"], 3), p.get("line", 0)))
    blocking = [p for p in problems if p["severity"] == "high"]

    return {
        "status": "fix" if (blocking or total < thresholds["pass_score"]) else "ok",
        "score": total,
        "grade": grade_of(total),
        "body_chars": body_chars,
        "read_seconds": round(body_chars / thresholds["read_speed"] * 60),
        "dimensions": {
            name: {"score": round(value[0], 1), "max": value[2], "notes": value[1]}
            for name, value in dims.items()
        },
        "blocking_count": len(blocking),
        "problems": problems,
        "next": (
            "按 problems 顺序修（high 必须修完），改完重跑本脚本；"
            f"score ≥ {thresholds['pass_score']} 且 blocking_count = 0 才算过"
            if blocking or total < thresholds["pass_score"]
            else "体检通过，回到流水线继续 humanize → prepare → finish"
        ),
    }


def render_markdown(result):
    lines = [
        f"# 稿件体检 {result['grade']}（{result['score']}/100）",
        "",
        f"正文 {result['body_chars']} 字 · 预计读完 {result['read_seconds']} 秒 · "
        f"阻塞问题 {result['blocking_count']} 个",
        "",
        "| 维度 | 得分 | 观测 |",
        "| --- | --- | --- |",
    ]
    labels = {
        "hook": "开头/标题", "value_density": "信息量",
        "reader_benefit": "利他性", "readability": "可读性", "retention": "抓人",
    }
    for name, value in result["dimensions"].items():
        lines.append(
            f"| {labels.get(name, name)} | {value['score']}/{value['max']} | "
            f"{'；'.join(value['notes'])} |"
        )
    lines.append("")
    if not result["problems"]:
        lines.append("没有发现问题。")
    for index, problem in enumerate(result["problems"], start=1):
        mark = {"high": "🔴", "medium": "🟡", "low": "⚪"}[problem["severity"]]
        lines.append(f"{index}. {mark} **第 {problem['line']} 行**｜{problem['what']}")
        lines.append(f"   - 修法：{problem['fix']}")
    lines.append("")
    lines.append(f"下一步：{result['next']}")
    return "\n".join(lines)


def score_title(title, thresholds, genre="insight"):
    """给单个标题打分（100）。标题是整条漏斗最窄的一道闸门，值得单独算。

    刺点类型也一并返回：三个候选如果全是同一类刺点，等于只想出了一个标题——
    这个信息比总分更有用，所以要能被调用方看到。
    """
    flat = re.sub(r"\s+", "", title)
    window = flat[: thresholds["title_sting_window"]]
    notes, score = [], 100.0

    if len(flat) > thresholds["title_max"]:
        over = len(flat) - thresholds["title_max"]
        score -= min(30, 6 * over)
        notes.append(f"超长 {over} 字（上限 {thresholds['title_max']}）")
    elif len(flat) < 10:
        score -= 15
        notes.append(f"只有 {len(flat)} 字，信息量不足")

    labels = {
        r"\d": "数字",
        r"[一二三四五六七八九十百千万两]\s*(?:条|个|种|点|步|招|年|天|次|倍|成|块|周|月)": "数字",
        r"不是[^，。]{1,20}(?:，|、)?而是": "反差",
        r"(?:比|相比)[^，。]{1,16}(?:更|还|少|多|快|慢|贵|便宜)": "反差",
        r"(?:别|不要|不用|没必要|未必|根本|其实不|不值得|先别)": "否定断言",
        r"(?:坑|翻车|踩雷|白干|白忙|亏|代价|后果|真相|误会|想错|搞错|错在)": "代价",
        r"(?:如果你|普通人|新手|老板|打工人|程序员|做号|中小)": "对号入座",
        r"(?:怎么选|该不该|要不要|值不值|能不能|凭什么|为什么)": "决策疑问",
        r"[?？！!]": "疑问感叹",
    }
    front, anywhere = set(), set()
    for pattern, label in labels.items():
        if re.search(pattern, window):
            front.add(label)
        elif re.search(pattern, flat):
            anywhere.add(label)

    if not front and not anywhere:
        score -= 35
        notes.append("完全没有刺点：加一个数字、一个反差、或一句得罪人的断言")
    elif not front:
        score -= 18
        notes.append(
            f"刺点（{'、'.join(sorted(anywhere))}）在后半截，"
            f"列表页只稳定露出前 {thresholds['title_sting_window']} 字，把它提到前面"
        )
    else:
        notes.append("刺点：" + "、".join(sorted(front)))

    has_subject = any(re.search(p, flat) for p in SUBJECT_SIGNALS)
    vague = re.search(VAGUE_REFERENTS, flat)
    if not has_subject:
        score -= 25 if vague else 14
        notes.append(
            ("用了「" + vague.group(0) + "」这类泛指，且找不到可指认的主体："
             if vague else "找不到可指认的主体（产品名/作品名/人群/地名/数字实体）：")
            + "读者在推荐页只看得到标题，说不出「这写的是谁、哪件事」就不会点。"
            "确认标题里有没有一个具体的主语（这条正则会漏判纯中文技术名词，人工核一下）"
        )

    if re.search(r"(?:的一些|几点|浅谈|漫谈|随笔|思考|探讨|之我见)", flat):
        score -= 20
        notes.append("周报腔：「思考/浅谈/几点」是过程词，读者要的是结果")
    if genre == "reading" and REVIEW_TITLE_RE.search(flat):
        score -= 30
        notes.append("书评/读后感标题：改成判断或现象，书名不要进标题")
    if re.search(r"^[^，。？！]{6,}(?:引入|接入|上线|发布|推出|开放)[^，。？！]*[，,]", flat):
        score -= 15
        notes.append("通报体：只说发生了什么，没说关读者什么事")
    if not re.search(r"[一-龥]", flat):
        score -= 10
        notes.append("没有中文实词")

    return {
        "title": title,
        "score": round(max(0.0, score), 1),
        "chars": len(flat),
        "stings": sorted(front),
        "late_stings": sorted(anywhere),
        "has_subject": has_subject,
        "notes": notes,
    }


def rank_titles(titles, thresholds, genre="insight"):
    ranked = sorted(
        (score_title(t, thresholds, genre=genre) for t in titles),
        key=lambda r: (-r["score"], r["chars"]),
    )
    kinds = {s for item in ranked for s in item["stings"] + item["late_stings"]}
    advice = []
    if len(titles) < 3:
        advice.append("候选少于 3 个：不同刺点各写一个（数字 / 反差 / 损失），再挑")
    if len(kinds) <= 1 and len(titles) >= 3:
        advice.append(
            "三个候选用的是同一类刺点，等于只想出了一个标题。"
            "换个方向再写一个：把收益框架改成损失框架（「教你省钱」→「别再花冤枉钱」）"
        )
    if ranked and not any(item["has_subject"] for item in ranked):
        advice.append(
            "所有候选都找不到可指认的主体。标题要同时回答两件事："
            "**谁/什么东西**（主体）+ **怎么了**（刺点）。"
            "只有判断没有主语的标题，读者在推荐页判断不出跟自己有没有关系"
        )
    if ranked and ranked[0]["score"] < 70:
        advice.append("最好的候选也不到 70 分：先想清楚这篇最狠的一句话是什么，再写标题")
    return {
        "status": "ok" if ranked and ranked[0]["score"] >= 70 else "fix",
        "best": ranked[0]["title"] if ranked else "",
        "ranked": ranked,
        "advice": advice,
        "next": "选定后写进 article.md 的一级标题；正文前三分之一必须兑现标题里的承诺",
    }


def load_thresholds(config_path):
    thresholds = dict(THRESHOLDS)
    if not config_path:
        return thresholds
    try:
        data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return thresholds
    override = data.get("scoring", {}) if isinstance(data, dict) else {}
    for key, value in override.items():
        if key in thresholds and isinstance(value, (int, float)):
            thresholds[key] = value
    return thresholds


def build_parser():
    parser = argparse.ArgumentParser(
        description="稿件体检：信息量 / 利他性 / 可读性 / 抓人，四维打分并给出逐条修法",
    )
    parser.add_argument("--article", help="article.md 路径")
    parser.add_argument(
        "--titles", nargs="+", metavar="标题",
        help="只给标题候选打分排序（不看正文）。写正文之前先用它挑标题",
    )
    parser.add_argument("--config", help="writer-config.json，用于覆盖阈值")
    parser.add_argument(
        "--genre", choices=("insight", "reading"), default="insight",
        help="reading：按认知读书文判，拦书评腔、要求引用原句",
    )
    parser.add_argument("--markdown", action="store_true", help="输出给人看的报告")
    parser.add_argument("--out", help="把 JSON 结果另存到这个路径")
    return parser


def render_titles_markdown(result):
    lines = ["# 标题候选", ""]
    for index, item in enumerate(result["ranked"], start=1):
        mark = "✅" if index == 1 else "  "
        lines.append(f"{mark} **{item['score']}** · {item['chars']} 字 · {item['title']}")
        lines += [f"   - {note}" for note in item["notes"]]
    lines.append("")
    for note in result["advice"]:
        lines.append(f"⚠️ {note}")
    lines.append(f"\n下一步：{result['next']}")
    return "\n".join(lines)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    thresholds = load_thresholds(args.config)

    if args.titles:
        result = rank_titles(args.titles, thresholds, genre=args.genre)
        print(render_titles_markdown(result) if args.markdown
              else json.dumps(result, ensure_ascii=False))
        return 0
    if not args.article:
        parser.error("需要 --article（或用 --titles 只给标题打分）")

    try:
        article = Path(args.article).read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({
            "status": "fix", "score": 0, "grade": "E", "problems": [{
                "dim": "input", "severity": "high", "line": 0,
                "what": f"读不到稿件：{exc}",
                "fix": "确认 --article 指向 job_contract.paths 里的 article.md",
            }],
        }, ensure_ascii=False))
        return 0
    result = analyze(article, thresholds, genre=args.genre)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(render_markdown(result) if args.markdown
          else json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
