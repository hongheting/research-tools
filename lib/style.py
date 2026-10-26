"""期刊风绘图默认样式（色盲友好）。"""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt

# Okabe–Ito 色盲友好调色板
COLORBLIND_SAFE = [
    "#0072B2",  # 蓝
    "#E69F00",  # 橙
    "#009E73",  # 绿
    "#CC79A7",  # 紫红
    "#56B4E9",  # 天蓝
    "#D55E00",  # 朱红
    "#F0E442",  # 黄
    "#000000",  # 黑
]

FIGURE_DPI = 300


def apply_journal_style() -> None:
    """应用单栏/双栏友好的期刊默认样式。"""
    mpl.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": FIGURE_DPI,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.05,
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.titlesize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "axes.linewidth": 1.0,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "lines.linewidth": 1.5,
            "lines.markersize": 5,
            "pdf.fonttype": 42,  # TrueType，便于期刊编辑改字
            "ps.fonttype": 42,
            "font.family": "sans-serif",
            "font.sans-serif": [
                "DejaVu Sans",
                "Arial",
                "Helvetica",
                "Noto Sans CJK SC",
                "SimHei",
                "sans-serif",
            ],
        }
    )


def save_figure(fig: plt.Figure, path_stem: str, formats: tuple[str, ...] = ("png", "pdf")) -> list[str]:
    """保存多种格式，返回写出的绝对路径列表。"""
    from pathlib import Path

    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    for fmt in formats:
        p = stem.with_suffix(f".{fmt}")
        fig.savefig(p, format=fmt)
        out.append(str(p.resolve()))
    return out
