#!/usr/bin/env python3
"""拉拔强度（Pull-off adhesion）柱状图：均值 ± SD，柱上标注 n。

输入 CSV/Excel，至少两列：
- group / sample / 样品（分组名）
- strength / adhesion / MPa / 强度（数值）
可选：若已是汇总表，可含 mean / sd / n 列，则直接绘图。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lib.colors import ColorError, add_color_arguments, colors_from_args, resolve_series_colors
from lib.style import apply_journal_style, save_figure

_GROUP_ALIASES = ("group", "sample", "样品", "涂层", "coating", "label", "name")
_VALUE_ALIASES = ("strength", "adhesion", "mpa", "拉力", "强度", "pull_off", "value", "y")
_MEAN_ALIASES = ("mean", "avg", "平均值", "均值")
_SD_ALIASES = ("sd", "std", "stdev", "标准差")
_N_ALIASES = ("n", "count", "重复", "repeats")


def _find_col(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for a in aliases:
        if a.lower() in lower:
            return lower[a.lower()]
    # 宽松：列名包含别名（如 strength_MPa）
    for a in aliases:
        al = a.lower()
        for key, orig in lower.items():
            if al and al in key.replace(" ", "").replace("-", "_"):
                return orig
    return None


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """原始长表 → group, mean, sd, n；或识别已汇总表。"""
    mean_c = _find_col(df, _MEAN_ALIASES)
    sd_c = _find_col(df, _SD_ALIASES)
    n_c = _find_col(df, _N_ALIASES)
    group_c = _find_col(df, _GROUP_ALIASES)

    if mean_c and group_c:
        out = pd.DataFrame(
            {
                "group": df[group_c].astype(str),
                "mean": pd.to_numeric(df[mean_c], errors="coerce"),
                "sd": pd.to_numeric(df[sd_c], errors="coerce") if sd_c else 0.0,
                "n": pd.to_numeric(df[n_c], errors="coerce").fillna(0).astype(int) if n_c else 0,
            }
        )
        return out.dropna(subset=["mean"])

    value_c = _find_col(df, _VALUE_ALIASES)
    if not group_c or not value_c:
        raise ValueError(
            "需要 group+strength 原始列，或 group+mean(+sd+n) 汇总列。"
            f" 当前列: {list(df.columns)}"
        )
    g = df[group_c].astype(str)
    v = pd.to_numeric(df[value_c], errors="coerce")
    tmp = pd.DataFrame({"group": g, "value": v}).dropna()
    grouped = tmp.groupby("group", sort=False)["value"]
    out = grouped.agg(mean="mean", sd="std", n="count").reset_index()
    out["sd"] = out["sd"].fillna(0.0)
    return out


def load_table(path: Path, sheet: str | int = 0) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet)
    return pd.read_csv(path)


def plot_pull_off(
    summary: pd.DataFrame,
    out_stem: Path,
    title: str | None = None,
    ylabel: str = "Pull-off strength (MPa)",
    colors: list[str] | None = None,
) -> list[str]:
    apply_journal_style()
    fig, ax = plt.subplots(figsize=(max(4.5, 0.9 * len(summary) + 1.5), 4.0))
    x = np.arange(len(summary))
    means = summary["mean"].to_numpy()
    sds = summary["sd"].to_numpy()
    ns = summary["n"].to_numpy()
    if colors is None:
        colors = resolve_series_colors(len(summary))
    elif len(colors) == 1:
        colors = colors * len(summary)
    else:
        colors = [colors[i % len(colors)] for i in range(len(summary))]

    bars = ax.bar(
        x,
        means,
        yerr=sds,
        width=0.65,
        color=colors,
        edgecolor="black",
        linewidth=0.6,
        capsize=4,
        error_kw={"elinewidth": 1.0, "capthick": 1.0},
    )
    ax.set_xticks(x)
    ax.set_xticklabels(summary["group"].tolist(), rotation=20, ha="right")
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)

    # 柱顶标注 n
    ymax = float(np.nanmax(means + sds)) if len(means) else 1.0
    for i, (m, s, n) in enumerate(zip(means, sds, ns)):
        if n and n > 0:
            ax.text(i, m + s + 0.03 * ymax, f"n={int(n)}", ha="center", va="bottom", fontsize=8)

    ax.set_ylim(0, ymax * 1.18 if ymax > 0 else 1)
    fig.tight_layout()
    return save_figure(fig, str(out_stem), formats=("png", "pdf"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="拉拔强度柱状图（均值±SD，标 n）")
    p.add_argument("input", type=Path, help="CSV/Excel")
    p.add_argument("-o", "--output", type=Path, required=True, help="输出路径（无扩展名）")
    p.add_argument("--title", default=None)
    p.add_argument("--ylabel", default="Pull-off strength (MPa)")
    p.add_argument("--sheet", default=0)
    add_color_arguments(p)
    args = p.parse_args(argv)

    sheet: str | int = args.sheet
    try:
        sheet = int(args.sheet)
    except (TypeError, ValueError):
        pass

    df = load_table(args.input, sheet=sheet)
    summary = summarize(df)
    stem = args.output
    if stem.suffix:
        stem = stem.with_suffix("")
    try:
        bar_colors = colors_from_args(args, len(summary))
    except ColorError as exc:
        import sys
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    paths = plot_pull_off(summary, stem, title=args.title, ylabel=args.ylabel, colors=bar_colors)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
