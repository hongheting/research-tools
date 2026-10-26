"""曲线/柱状图颜色解析（CLI 共用）。"""
from __future__ import annotations

import argparse
from typing import Sequence

import matplotlib.colors as mcolors
from matplotlib import colormaps

from .style import COLORBLIND_SAFE

# 命名色板
PALETTES: dict[str, list[str]] = {
    "okabe": list(COLORBLIND_SAFE),
    "tableau": [
        "#4E79A7",
        "#F28E2B",
        "#E15759",
        "#76B7B2",
        "#59A14F",
        "#EDC948",
        "#B07AA1",
        "#FF9DA7",
        "#9C755F",
        "#BAB0AC",
    ],
    "viridis": [mcolors.to_hex(colormaps["viridis"](x)) for x in (0.15, 0.35, 0.55, 0.75, 0.9)],
}

DEFAULT_PALETTE = "okabe"


class ColorError(ValueError):
    """非法颜色或色板。"""


def parse_color(spec: str) -> str:
    """把用户输入规范成 matplotlib 可识别颜色；失败抛 ColorError。"""
    s = (spec or "").strip()
    if not s:
        raise ColorError("颜色为空。请使用如 #0072B2、orange、C0。")
    # 允许用户写 #RGB / #RRGGBB（可带或不带引号残留）
    s = s.strip("\"'")
    try:
        return mcolors.to_hex(mcolors.to_rgba(s))
    except ValueError as exc:
        raise ColorError(
            f"无法识别颜色 '{spec}'。可用：十六进制 (#E69F00)、CSS 名 (blue/orange)、"
            f"matplotlib 循环色 (C0–C9)。原因: {exc}"
        ) from exc


def parse_colors_csv(spec: str) -> list[str]:
    """逗号分隔色列表。"""
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        raise ColorError("--colors 为空。示例: --colors '#0072B2,#E69F00,#009E73'")
    return [parse_color(p) for p in parts]


def get_palette(name: str) -> list[str]:
    key = (name or DEFAULT_PALETTE).strip().lower()
    if key not in PALETTES:
        raise ColorError(
            f"未知色板 '{name}'。可选: {', '.join(sorted(PALETTES))}。"
        )
    return list(PALETTES[key])


def resolve_series_colors(
    n: int,
    *,
    color: str | None = None,
    colors: str | list[str] | None = None,
    palette: str = DEFAULT_PALETTE,
) -> list[str]:
    """为 n 条系列解析颜色列表。

    优先级：--colors > --color（全系列同色）> --palette 轮换。
    """
    if n <= 0:
        return []
    if colors:
        if isinstance(colors, str):
            clist = parse_colors_csv(colors)
        else:
            clist = [parse_color(c) for c in colors]
        if len(clist) < n:
            # 不够则循环补齐
            clist = [clist[i % len(clist)] for i in range(n)]
        return clist[:n]
    if color:
        c = parse_color(color)
        return [c] * n
    pal = get_palette(palette)
    return [pal[i % len(pal)] for i in range(n)]


def darken_color(color: str, factor: float = 0.65) -> str:
    """同色加深，用于拟合线默认样式。"""
    r, g, b, a = mcolors.to_rgba(color)
    return mcolors.to_hex((r * factor, g * factor, b * factor, a))


def add_color_arguments(parser: argparse.ArgumentParser, *, with_fit_color: bool = False) -> None:
    """给子命令挂上统一颜色参数。"""
    parser.add_argument(
        "-c",
        "--color",
        default=None,
        help="单条/全系列颜色，如 #E69F00、blue、C0",
    )
    parser.add_argument(
        "--colors",
        default=None,
        help="多系列逗号分隔色，如 '#0072B2,#E69F00,#009E73'",
    )
    parser.add_argument(
        "--palette",
        default=DEFAULT_PALETTE,
        choices=sorted(PALETTES),
        help=f"默认色板轮换（默认 {DEFAULT_PALETTE}）",
    )
    if with_fit_color:
        parser.add_argument(
            "--fit-color",
            default=None,
            help="拟合曲线颜色；省略则与数据同色（线型区分），可用加深色",
        )


def colors_from_args(args: argparse.Namespace, n: int) -> list[str]:
    """从 argparse Namespace 解析 n 色；非法则抛 ColorError。"""
    return resolve_series_colors(
        n,
        color=getattr(args, "color", None),
        colors=getattr(args, "colors", None),
        palette=getattr(args, "palette", DEFAULT_PALETTE) or DEFAULT_PALETTE,
    )
