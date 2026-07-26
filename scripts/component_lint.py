#!/usr/bin/env python3
"""组件库源头检查器 —— 可验证循环的第一道关。

扫描 references/ 下所有组件库 .md 里的 ```html 代码块，检测会导致
排版问题的反模式。只看真实组件 HTML，不被说明文字干扰（grep 做不到）。

与 validate_gzh_html.py 配合构成闭环：
  改组件库 → component_lint.py 扫源头 → 生成产物 → validate_gzh_html.py 扫产物 → 修 → 重复

用法：
    component_lint.py [skill-dir]   # 默认当前目录
退出码：1 = 有 ERROR，0 = 通过。
"""

import glob
import os
import re
import sys

CJK = re.compile(r"[一-鿿㐀-䶿]")

# (正则, 级别, 说明) —— 在每个 ```html 组件块内检查
CHECKS = [
    (re.compile(r"white-space\s*:\s*pre", re.I), "ERROR",
     "用了 white-space:pre —— 会把 HTML 源码缩进/换行渲染成大左缩进+空行；"
     "代码块改成每行一个 <p style=\"margin:0\">，缩进用全角空格"),
    (re.compile(r"</?div[\s>]", re.I), "ERROR", "出现 <div>，应用 <section>"),
    (re.compile(r"\sclass\s*=", re.I), "ERROR", "出现 class 属性（会被公众号剥离）"),
    (re.compile(r"\sid\s*=", re.I), "ERROR", "出现 id 属性"),
    (re.compile(r"<style[\s>]", re.I), "ERROR", "出现 <style> 标签"),
    (re.compile(r"position\s*:\s*(fixed|absolute|sticky)", re.I), "ERROR",
     "position fixed/absolute/sticky 不被支持"),
    (re.compile(r"display\s*:\s*grid", re.I), "ERROR", "display:grid 不被支持"),
    (re.compile(r"var\s*\(\s*--", re.I), "ERROR", "用了 CSS 变量 var(--x)"),
    (re.compile(r"@(media|keyframes|import)", re.I), "ERROR", "@media/@keyframes/@import 不被支持"),
]

# 四周虚线框：border: ... dashed（不含方向，如 border-left dashed 不算）
FOURSIDE_DASHED = re.compile(r"border\s*:\s*[^;{}]*dashed", re.I)
# 居中：text-align:center 或 flex 主/交叉轴居中（占位/素材类组件的常见写法）
CENTERED = re.compile(
    r"text-align\s*:\s*center|justify-content\s*:\s*center|align-items\s*:\s*center", re.I)
# 主题库可在组件块前的说明文字里写 `lint-allow: dashed`，
# 声明该组件的虚线框是主题风格特征（如摸鱼绿 quote-box），豁免 WARN
ALLOW_DASHED = re.compile(r"lint-allow\s*[:：]\s*dashed", re.I)


def lint_file(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    name = os.path.basename(path).replace("公众号排版组件库 —— ", "").replace(".md", "")
    found = []  # (level, msg)
    seen = set()

    def add(level, msg):
        if msg not in seen:
            seen.add(msg)
            found.append((level, msg))

    for m in re.finditer(r"```html\s*\n(.*?)```", text, re.S):
        html = m.group(1)
        for rx, level, msg in CHECKS:
            if rx.search(html):
                add(level, msg)
        # 四周虚线框：正文强调勿用；居中块视为"占位/素材"组件，豁免；
        # 组件块前 300 字符内声明 lint-allow: dashed（主题风格特征）也豁免
        context_before = text[max(0, m.start() - 300):m.start()]
        if (FOURSIDE_DASHED.search(html) and not CENTERED.search(html)
                and not ALLOW_DASHED.search(context_before)):
            add("WARN", "四周虚线框 border:…dashed（正文强调请用左竖条；"
                        "仅居中的素材占位块或主题库声明 lint-allow: dashed 的风格组件可用）")
    return name, found


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    refs = sorted(glob.glob(os.path.join(root, "references", "*.md")))
    if not refs:
        print(f"未找到 {root}/references/*.md")
        sys.exit(1)

    total_err = total_warn = clean = 0
    print(f"📐 组件库源头检查：{len(refs)} 个库\n")
    for path in refs:
        name, found = lint_file(path)
        if not found:
            clean += 1
            continue
        errs = [m for lv, m in found if lv == "ERROR"]
        warns = [m for lv, m in found if lv == "WARN"]
        total_err += len(errs)
        total_warn += len(warns)
        print(f"── {name} ──")
        for m in errs:
            print(f"   ❌ {m}")
        for m in warns:
            print(f"   ⚠️  {m}")

    print(f"\n汇总：{clean}/{len(refs)} 个库干净，ERROR×{total_err}，WARN×{total_warn}")
    if total_err == 0 and total_warn == 0:
        print("✅ 全部组件库源头无反模式")
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
