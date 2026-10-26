#!/usr/bin/env python3
"""SEM 灰度图 → 伪彩（期刊预览 / 示意用）。

注意：伪彩仅用于可视化增强，发表时请遵守期刊对彩色 SEM 的要求，
并在图注中说明 colormap 与是否做过对比度拉伸。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

# 允许的 colormap（含常见科研用）
COLORMAPS = (
    "viridis",
    "plasma",
    "inferno",
    "magma",
    "cividis",
    "turbo",
    "jet",
    "hot",
    "gray",
)


def load_gray(path: Path) -> np.ndarray:
    """读入图像并转为 float64 灰度 [0, 1]。"""
    img = Image.open(path)
    if img.mode not in ("L", "I", "F", "I;16", "I;16B"):
        img = img.convert("L")
    arr = np.asarray(img, dtype=np.float64)
    # 16-bit 等可能超 255
    vmax = arr.max()
    if vmax > 0:
        arr = arr / vmax
    return arr


def stretch_contrast(arr: np.ndarray, low_pct: float = 1.0, high_pct: float = 99.0) -> np.ndarray:
    """百分位对比度拉伸，抑制极端亮/暗点。"""
    lo, hi = np.percentile(arr, [low_pct, high_pct])
    if hi <= lo:
        return arr
    out = (arr - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0)


def apply_pseudocolor(
    gray: np.ndarray,
    cmap: str = "viridis",
    stretch: bool = True,
    low_pct: float = 1.0,
    high_pct: float = 99.0,
) -> np.ndarray:
    """返回 RGBA uint8 数组 (H, W, 4)。"""
    if cmap not in COLORMAPS and cmap not in plt.colormaps():
        raise ValueError(f"未知 colormap: {cmap}；可选: {', '.join(COLORMAPS)}")
    data = stretch_contrast(gray, low_pct, high_pct) if stretch else np.clip(gray, 0, 1)
    cm = plt.get_cmap(cmap)
    rgba = (cm(data) * 255).astype(np.uint8)
    return rgba


def render_with_colorbar(
    gray: np.ndarray,
    cmap: str,
    stretch: bool,
    low_pct: float,
    high_pct: float,
    title: str | None,
    out_stem: Path,
    formats: tuple[str, ...] = ("png",),
    dpi: int = 300,
) -> list[str]:
    """画伪彩 + 色标条并保存。"""
    data = stretch_contrast(gray, low_pct, high_pct) if stretch else np.clip(gray, 0, 1)
    fig, ax = plt.subplots(figsize=(5.2, 4.5))
    im = ax.imshow(data, cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=11, pad=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Normalized intensity", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    fig.tight_layout()

    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for fmt in formats:
        p = out_stem.with_suffix(f".{fmt}")
        fig.savefig(p, dpi=dpi, bbox_inches="tight", pad_inches=0.05)
        paths.append(str(p.resolve()))
    plt.close(fig)

    # 另存无色标的纯伪彩 TIFF/PNG（便于后处理）
    rgba = apply_pseudocolor(gray, cmap=cmap, stretch=stretch, low_pct=low_pct, high_pct=high_pct)
    raw_png = out_stem.with_name(out_stem.name + "_raw").with_suffix(".png")
    Image.fromarray(rgba, mode="RGBA").save(raw_png)
    paths.append(str(raw_png.resolve()))
    return paths


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SEM 灰度图伪彩着色")
    p.add_argument("input", type=Path, help="输入灰度图（PNG/TIFF/JPG）")
    p.add_argument("-o", "--output", type=Path, required=True, help="输出路径（无扩展名，或 .png）")
    p.add_argument("-c", "--cmap", default="viridis", help=f"colormap，默认 viridis；可选 {', '.join(COLORMAPS)}")
    p.add_argument("--no-stretch", action="store_true", help="关闭百分位对比度拉伸")
    p.add_argument("--low", type=float, default=1.0, help="拉伸低百分位，默认 1")
    p.add_argument("--high", type=float, default=99.0, help="拉伸高百分位，默认 99")
    p.add_argument("--title", default=None, help="图标题")
    p.add_argument("--tiff", action="store_true", help="额外输出 TIFF")
    args = p.parse_args(argv)

    gray = load_gray(args.input)
    stem = args.output
    if stem.suffix:
        stem = stem.with_suffix("")
    formats = ("png", "tiff") if args.tiff else ("png",)
    paths = render_with_colorbar(
        gray,
        cmap=args.cmap,
        stretch=not args.no_stretch,
        low_pct=args.low,
        high_pct=args.high,
        title=args.title,
        out_stem=stem,
        formats=formats,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
