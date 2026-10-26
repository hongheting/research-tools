#!/usr/bin/env python3
"""电化学阻抗谱（EIS）：等效电路拟合 + Nyquist/Bode 成图。

默认先拟合再画图（数据点 + 拟合曲线）。关闭：`--fit none`。

列名（大小写不敏感，常见别名自动识别）：
- Zreal / Zimag / Zre / Zim（含单位括号如 Zre (ohms)）
- Frequency (Hz) / freq；拟合**必须**有频率
- 或 freq + |Z| + phase；支持 .csv / .txt（制表符）/ Excel

拟合时额外输出残差图 `*_fit_residual.png`，Nyquist 角标参数表。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from eis_fit import (
    DEFAULT_CIRCUIT,
    FitError,
    FitResult,
    fit_eis,
    list_circuits_help,
    resolve_circuit,
    save_fit_outputs,
)
from lib.colors import ColorError, colors_from_args, darken_color, add_color_arguments, parse_color
from lib.style import apply_journal_style, save_figure

_ALIASES: dict[str, tuple[str, ...]] = {
    "zreal": ("zreal", "z'", "zre", "z_re", "re", "real", "zr", "zrealohms", "zreohms"),
    "zimag": ("zimag", 'z"', "zim", "z_im", "im", "imag", "zi", "-zim", "-zimag", "zimohms", "zimagohms"),
    "freq": ("freq", "frequency", "f", "hz", "freqhz", "frequencyhz"),
    "zmod": ("zmod", "|z|", "mod", "modulus", "absz", "zmod", "abs(z)"),
    "phase": ("phase", "phaseofz", "zphz", "phz", "phi", "angle", "phasedeg", "phaseofzdeg"),
}


def _norm_col(name: str) -> str:
    """归一化列名：去空格/单位括号，便于别名匹配。

    例：'Zre (ohms)' → 'zre'；'Frequency (Hz)' → 'frequency'；'|Z| (ohms)' → '|z|'
    """
    s = str(name).strip().lower().replace("（", "(").replace("）", ")")
    # 去掉括号内单位说明
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace(" ", "").replace("_", "")
    for ch in ("Ω", "ohms", "ohm", "°", "deg", "/"):
        s = s.replace(ch, "")
    return s


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    norm_to_actual = {_norm_col(c): c for c in df.columns}
    mapping: dict[str, str] = {}
    for std, aliases in _ALIASES.items():
        for a in aliases:
            if a in norm_to_actual:
                mapping[std] = norm_to_actual[a]
                break
    return mapping


def _read_table(path: Path, sheet: str | int | None = 0) -> pd.DataFrame:
    """读 CSV/TSV/TXT/Excel；TXT 常为制表符分隔（Gamry/CHI 等导出）。"""
    path = Path(path)
    suf = path.suffix.lower()
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)
    # 自动嗅探分隔符（逗号/制表符/分号）
    return pd.read_csv(path, sep=None, engine="python", comment="#")


def load_eis(path: Path, sheet: str | int | None = 0) -> pd.DataFrame:
    """读 CSV/Excel/TXT → freq / zreal / zimag / zmod / phase / neg_zimag。"""
    path = Path(path)
    df = _read_table(path, sheet=sheet)
    # 去掉全空列（部分仪器导出末尾多一列空）
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    mapping = _map_columns(df)
    out = pd.DataFrame()
    for std, actual in mapping.items():
        out[std] = pd.to_numeric(df[actual], errors="coerce")

    # 由 |Z|+phase 还原复数阻抗
    if {"zmod", "phase"}.issubset(out.columns) and (
        "zreal" not in out.columns or "zimag" not in out.columns
    ):
        ph = np.radians(out["phase"].to_numpy(dtype=float))
        out["zreal"] = out["zmod"] * np.cos(ph)
        out["zimag"] = out["zmod"] * np.sin(ph)

    if "zimag" in out.columns:
        med = out["zimag"].dropna().median()
        out["neg_zimag"] = -out["zimag"] if med >= 0 else out["zimag"].abs()
        if med < 0:
            out["zimag"] = -out["zimag"].abs()

    if "zmod" not in out.columns and {"zreal", "zimag"}.issubset(out.columns):
        out["zmod"] = np.sqrt(out["zreal"] ** 2 + out["zimag"] ** 2)
    if "phase" not in out.columns and {"zreal", "zimag"}.issubset(out.columns):
        out["phase"] = np.degrees(np.arctan2(out["zimag"], out["zreal"]))

    if out.empty or not {"zreal", "zimag"}.issubset(out.columns):
        raise ValueError(
            "未能识别 EIS 列。请包含 Zreal/Zimag（建议再加 freq），或 freq+|Z|+phase。"
            f" 当前列: {list(df.columns)}"
        )
    return out.dropna(how="all")


def plot_eis_residuals(
    fits: list[FitResult],
    out_stem: Path,
    title: str | None = None,
    colors: list[str] | None = None,
) -> list[str]:
    """实部/虚部残差（相对 |Z|）vs 频率半对数图。"""
    apply_journal_style()
    from lib.colors import resolve_series_colors

    series_colors = colors if colors is not None else resolve_series_colors(len(fits))
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.6), sharex=True)
    ax_r, ax_i = axes
    for i, fr in enumerate(fits):
        if len(fr.freq_meas) == 0:
            continue
        color = series_colors[i % len(series_colors)]
        lbl = fr.label or fr.circuit
        ax_r.semilogx(
            fr.freq_meas,
            fr.residual_real_rel * 100,
            color=color,
            marker="o",
            markersize=3,
            linestyle="none",
            label=lbl,
            alpha=0.9,
        )
        ax_i.semilogx(
            fr.freq_meas,
            fr.residual_imag_rel * 100,
            color=color,
            marker="s",
            markersize=3,
            linestyle="none",
            label=lbl,
            alpha=0.9,
        )
    for ax, ylab, ttl in (
        (ax_r, r"ΔZ′ / |Z| (%)", "Real residual"),
        (ax_i, r"ΔZ″ / |Z| (%)", "Imag residual"),
    ):
        ax.axhline(0, color="#888888", linewidth=0.8, linestyle=":")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel(ylab)
        ax.set_title(ttl)
        ax.legend(frameon=False, fontsize=8)
    if title:
        fig.suptitle(title, fontsize=12, y=1.02)
    fig.tight_layout()
    stem = Path(out_stem)
    residual_stem = stem.with_name(stem.name + "_fit_residual")
    return save_figure(fig, str(residual_stem), formats=("png", "pdf"))


def plot_eis(
    data: pd.DataFrame | list[tuple[str, pd.DataFrame]],
    out_stem: Path,
    title: str | None = None,
    layout: str = "triple",
    fits: list[FitResult] | None = None,
    colors: list[str] | None = None,
    fit_color: str | None = None,
    darken_fit: bool = True,
    annotate_params: bool = True,
) -> list[str]:
    """画数据点；若提供 fits，叠加拟合曲线。colors 为每条系列色。"""
    apply_journal_style()
    if isinstance(data, pd.DataFrame):
        series_list: list[tuple[str, pd.DataFrame]] = [("", data)]
    else:
        series_list = list(data)

    fit_by_label = {f.label: f for f in (fits or [])}
    from lib.colors import resolve_series_colors
    series_colors = colors if colors is not None else resolve_series_colors(len(series_list))

    if layout == "dual":
        fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.6))
        ax_ny, ax_bode = axes
        ax_phase = ax_bode.twinx()
        ax_mod = None
    else:
        fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.5))
        ax_ny, ax_mod, ax_phase = axes
        ax_bode = None

    for i, (label, df) in enumerate(series_list):
        color = series_colors[i % len(series_colors)]
        data_lbl = f"{label} data" if label else "data"
        fit_lbl = f"{label} fit" if label else "fit"

        if {"zreal", "neg_zimag"}.issubset(df.columns) or {"zreal", "zimag"}.issubset(df.columns):
            x = df["zreal"]
            y = df["neg_zimag"] if "neg_zimag" in df.columns else -df["zimag"]
            ax_ny.plot(
                x,
                y,
                color=color,
                marker="o",
                markersize=3.5,
                linestyle="none",
                label=data_lbl,
                alpha=0.9,
            )

        if "freq" in df.columns and "zmod" in df.columns:
            if layout == "dual":
                ax_bode.loglog(
                    df["freq"],
                    df["zmod"],
                    color=color,
                    marker="o",
                    markersize=3,
                    linestyle="none",
                    label=data_lbl if i == 0 else None,
                )
            else:
                ax_mod.loglog(
                    df["freq"],
                    df["zmod"],
                    color=color,
                    marker="o",
                    markersize=3,
                    linestyle="none",
                    label=data_lbl,
                )
        if "freq" in df.columns and "phase" in df.columns:
            ax_phase.semilogx(
                df["freq"],
                df["phase"],
                color=color if layout != "dual" else darken_color(color, 0.75),
                marker="s",
                markersize=3,
                linestyle="none",
                label=("phase data" if layout == "dual" and i == 0 else None),
            )

        fr = fit_by_label.get(label)
        if fr is not None:
            zf = fr.z_fit
            ff = fr.freq_hz
            fc = fit_color if fit_color else (darken_color(color) if darken_fit else color)
            ax_ny.plot(
                zf.real,
                -zf.imag,
                color=fc,
                linestyle="-",
                linewidth=1.8,
                label=fit_lbl,
            )
            if layout == "dual":
                ax_bode.loglog(ff, np.abs(zf), color=fc, linestyle="-", linewidth=1.6, label=fit_lbl if i == 0 else None)
                ax_phase.semilogx(
                    ff,
                    np.degrees(np.angle(zf)),
                    color=darken_color(fc, 0.75),
                    linestyle="--",
                    linewidth=1.4,
                    label="phase fit" if i == 0 else None,
                )
            else:
                ax_mod.loglog(ff, np.abs(zf), color=fc, linestyle="-", linewidth=1.6, label=fit_lbl)
                ax_phase.semilogx(
                    ff,
                    np.degrees(np.angle(zf)),
                    color=fc,
                    linestyle="-",
                    linewidth=1.6,
                )

    ax_ny.set_xlabel(r"$Z_{\mathrm{real}}$ (Ω)")
    ax_ny.set_ylabel(r"$-Z_{\mathrm{imag}}$ (Ω)")
    ax_ny.set_title("Nyquist")
    ax_ny.set_aspect("equal", adjustable="datalim")
    ax_ny.legend(frameon=False, fontsize=8)

    # 参数表角标（多系列时取第一条，避免遮挡）
    if annotate_params and fits:
        txt = fits[0].params_annotation()
        if len(fits) > 1:
            txt = fits[0].params_annotation() + f"\n(+{len(fits)-1} more)"
        ax_ny.text(
            0.02,
            0.98,
            txt,
            transform=ax_ny.transAxes,
            fontsize=6.5,
            verticalalignment="top",
            fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#cccccc", alpha=0.9),
        )

    if layout == "dual":
        ax_bode.set_xlabel("Frequency (Hz)")
        ax_bode.set_ylabel(r"|Z| (Ω)")
        ax_phase.set_ylabel("Phase (°)")
        ax_bode.set_title("Bode")
        lines1, labels1 = ax_bode.get_legend_handles_labels()
        lines2, labels2 = ax_phase.get_legend_handles_labels()
        if labels1 or labels2:
            ax_bode.legend(lines1 + lines2, labels1 + labels2, loc="best", frameon=False, fontsize=8)
    else:
        ax_mod.set_xlabel("Frequency (Hz)")
        ax_mod.set_ylabel(r"|Z| (Ω)")
        ax_mod.set_title("Bode |Z|")
        ax_phase.set_xlabel("Frequency (Hz)")
        ax_phase.set_ylabel("Phase (°)")
        ax_phase.set_title("Bode phase")
        ax_mod.legend(frameon=False, fontsize=8)

    if title:
        fig.suptitle(title, fontsize=12, y=1.02)
    fig.tight_layout()
    return save_figure(fig, str(out_stem), formats=("png", "pdf"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="EIS 拟合 + Nyquist/Bode 成图",
        epilog=list_circuits_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", type=Path, nargs="+", help="CSV/Excel（可多个对比）")
    p.add_argument("-o", "--output", type=Path, required=True, help="输出路径（无扩展名）")
    p.add_argument("-l", "--label", action="append", default=[], help="曲线标签")
    p.add_argument("--layout", choices=("triple", "dual"), default="triple")
    p.add_argument("--title", default=None)
    p.add_argument("--sheet", default=0)
    p.add_argument(
        "--fit",
        default=DEFAULT_CIRCUIT,
        help=f"电路模型（默认 {DEFAULT_CIRCUIT}）；none 关闭拟合。见 --help 末尾列表",
    )
    p.add_argument(
        "--weighting",
        default="modulus",
        choices=("modulus", "unit"),
        help="拟合加权（默认 modulus = 残差/|Z|）",
    )
    p.add_argument("--no-residual", action="store_true", help="不输出残差图")
    p.add_argument("--no-annotate", action="store_true", help="Nyquist 不标注参数表")
    add_color_arguments(p, with_fit_color=True)
    args = p.parse_args(argv)

    sheet: str | int = args.sheet
    try:
        sheet = int(args.sheet)
    except (TypeError, ValueError):
        pass

    try:
        circuit = resolve_circuit(args.fit)
    except FitError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    series: list[tuple[str, pd.DataFrame]] = []
    for i, path in enumerate(args.input):
        label = args.label[i] if i < len(args.label) else Path(path).stem
        series.append((label, load_eis(path, sheet=sheet)))

    try:
        series_colors = colors_from_args(args, len(series))
        fit_c = parse_color(args.fit_color) if args.fit_color else None
    except ColorError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    stem = args.output
    if stem.suffix:
        stem = stem.with_suffix("")

    fits: list[FitResult] = []
    if circuit != "none":
        for label, df in series:
            try:
                fits.append(fit_eis(df, circuit=circuit, label=label, weighting=args.weighting))
            except FitError as exc:
                print(f"错误: 拟合失败 — {exc}", file=sys.stderr)
                return 1
        for path in save_fit_outputs(fits, stem):
            print(path)
        if not args.no_residual:
            for path in plot_eis_residuals(fits, stem, title=f"Fit residual ({circuit})", colors=series_colors):
                print(path)

    title = args.title
    if title is None and circuit != "none":
        title = f"EIS fit ({circuit})"

    paths = plot_eis(
        series,
        stem,
        title=title,
        layout=args.layout,
        fits=fits or None,
        colors=series_colors,
        fit_color=fit_c,
        annotate_params=not args.no_annotate,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
