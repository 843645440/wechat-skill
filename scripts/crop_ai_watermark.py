#!/usr/bin/env python3
"""
crop_ai_watermark.py — ImageGen 等平台 AI 出图自动去右下角水印。

默认策略：仅裁掉图像高度的底部 5%（保宽去高），适配 1536×1024、1024×1024 等
横/方构图（2026-09-04 用户实测水印极小，从 10% 调低到 5%）。之前的"裁右边 +
裁底"会把主体裁坏，本工具专门修复这个问题。

使用示例：
    # 默认：裁底部 5%
    python scripts/crop_ai_watermark.py path/to/raw.png

    # 自定义比例 + 指定输出
    python scripts/crop_ai_watermark.py raw.png -r 0.1 -o cropped.png

    # 批量
    python scripts/crop_ai_watermark.py raw1.png raw2.png -o out_dir/

依赖：Pillow (PIL)。失败会给出明确报错；图片不存在/读不动也会提示。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.stderr.write(
        "[crop_ai_watermark] 缺少 Pillow，请先在 venv 安装：\n"
        "  /Users/cong/.workbuddy/binaries/python/envs/default/bin/pip install Pillow\n"
    )
    sys.exit(1)


def crop_bottom(
    src: Path,
    dst: Path,
    bottom_ratio: float = 0.1,
) -> tuple[int, int]:
    """从顶部保留 (1 - bottom_ratio) 的高度，宽度保持不变。

    返回 (原图尺寸, 输出尺寸) 便于日志。
    """
    img = Image.open(src)
    img.load()  # 触发完整解码，提前暴露坏图
    w, h = img.size
    new_h = int(h * (1 - bottom_ratio))
    if new_h <= 0 or new_h >= h:
        raise ValueError(
            f"bottom_ratio={bottom_ratio} 无效，需满足 0 < ratio < 1；"
            f"当前 h={h} → new_h={new_h}"
        )
    cropped = img.crop((0, 0, w, new_h))
    if cropped.mode not in ("RGB", "RGBA"):
        cropped = cropped.convert("RGB")
    os.makedirs(dst.parent, exist_ok=True)
    cropped.save(dst)
    return (w, h), (w, new_h)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="AI 出图去右下角水印（默认裁掉底部 10%）",
    )
    ap.add_argument("inputs", nargs="+", type=Path, help="输入图片路径")
    ap.add_argument(
        "-o", "--output",
        type=Path,
        help="输出路径（单文件时=目标文件；批量时=输出目录）",
    )
    ap.add_argument(
        "-r", "--bottom-ratio",
        type=float,
        default=0.05,
        help="裁掉底部比例，默认 0.05（即 5%%；2026-09-04 用户实测水印极小，从 10%% 调低）",
    )
    args = ap.parse_args()

    outputs: list[Path] = []
    if args.output and len(args.inputs) == 1:
        # 单文件模式：-o 是目标文件
        outputs = [args.output]
    elif args.output and len(args.inputs) > 1:
        # 批量模式：-o 是目录，按输入文件名 + .cropped.png 后缀输出
        out_dir = args.output
        os.makedirs(out_dir, exist_ok=True)
        outputs = [out_dir / f"{p.stem}.cropped.png" for p in args.inputs]
    else:
        # 默认：原地覆盖（原文件覆盖为裁后版本）
        outputs = list(args.inputs)

    rc = 0
    for src, dst in zip(args.inputs, outputs):
        if not src.exists():
            sys.stderr.write(f"[skip] 不存在：{src}\n")
            rc = 1
            continue
        try:
            orig, after = crop_bottom(src, dst, args.bottom_ratio)
            print(
                f"[ok] {src.name}: {orig[0]}x{orig[1]} → "
                f"{after[0]}x{after[1]} (裁底 {args.bottom_ratio:.0%}) → {dst}"
            )
        except Exception as exc:
            sys.stderr.write(f"[fail] {src}: {exc}\n")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())