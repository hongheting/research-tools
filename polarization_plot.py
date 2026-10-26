#!/usr/bin/env python3
"""动电位 / 极化曲线出图：半对数 E–log|i|（Tafel 风格）与可选线性 E–i。

列名灵活识别（大小写不敏感）：
- 电位 E：E, Potential, E_V, Ewe, Ewe/V, V, Voltage …
- 电流/电流密度 i：i, I, Current, j, CurrentDensity, i_A_cm2, mA/cm2 …
电流密度若疑似 mA/cm²（典型 |i| 中位数 > 0.1 且列名含 mA），绘图时换算为 A/cm²；
也可用 --i-unit mA_cm2 / A_cm2 强制指定。

Tafel 分析：
- 数据中已有 Ecorr / icorr 列 → 画参考线与标注
- --tafel-cathode / --tafel-anode 指定电位窗口
- --auto-tafel：自动估 Ecorr（|i| 最小附近），阴阳极各取一段做线性拟合并标 βa/βc、外推 icorr
  （失败则只画曲线 + Ecorr 线，不编造）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lib.colors import ColorError, add_color_arguments, colors_from_args, resolve_series_colors
from lib.style import apply_journal_style, save_figure

_E_ALIASES = (
    "e",
    "potential",
    "e_v",
    "ewe",
    "ewe/v",
    "voltage",
    "v",
    "e_sce",
    "e_agcl",
    "eoc",
    "电位",
    "电势",
)
_I_ALIASES = (
    "i",
    "j",
    "current",
    "currentdensity",
    "i_a_cm2",
    "j_a_cm2",
    "i_ma_cm2",
    "j_ma_cm2",
    "ma/cm2",
    "a/cm2",
    "abs_i",
    "电流",
    "电流密度",
)
_ECORR_ALIASES = ("ecorr", "e_corr", "corrosion_potential", "腐蚀电位")
_ICORR_ALIASES = ("icorr", "i_corr", "jcorr", "corrosion_current", "腐蚀电流")


def _norm_col(name: str) -> str:
    """归一化列名：去括号单位与空格。"""
    s = str(name).strip().lower().replace("（", "(").replace("）", ")")
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace(" ", "").replace("_", "")
    for ch in ("Ω", "ohm", "ohms", "°", "deg", "²", "^2", "/"):
        s = s.replace(ch, "")
    return s


def _find_col(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    norm_map = {_norm_col(c): c for c in df.columns}
    for a in aliases:
        an = _norm_col(a)
        if an in norm_map:
            return norm_map[an]
    for a in aliases:
        an = _norm_col(a)
        if not an:
            continue
        for key, orig in norm_map.items():
            if an in key or key in an:
                # 避免把 Ecorr 误当成 E：精确优先已处理；包含匹配时排除 corr
                if an in ("e", "v") and "corr" in key:
                    continue
                if an in ("i", "j") and "corr" in key:
                    continue
                return orig
    return None


def _detect_i_unit(col_name: str, i_values: pd.Series, forced: str | None) -> str:
    """返回 'A_cm2' 或 'mA_cm2'。"""
    if forced in ("A_cm2", "mA_cm2"):
        return forced
    n = _norm_col(col_name)
    if "ma" in n or "毫安" in str(col_name):
        return "mA_cm2"
    if "a/cm" in n or "acm" in n or n.endswith("acm2"):
        return "A_cm2"
    med = float(np.nanmedian(np.abs(i_values.to_numpy(dtype=float))))
    # 经验：涂层/金属极化 |i| 以 A/cm² 计常 < 1e-2；若中位数偏大更像 mA
    if med > 0.05:
        return "mA_cm2"
    return "A_cm2"


def _read_table(path: Path, sheet: str | int = 0) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet)
    return pd.read_csv(path, sep=None, engine="python", comment="#")


def load_polarization(
    path: Path,
    sheet: str | int = 0,
    i_unit: str | None = None,
) -> pd.DataFrame:
    """读 CSV/TXT/Excel → 标准列 E_V, i_A_cm2（及可选 Ecorr_V, icorr_A_cm2）。"""
    path = Path(path)
    df = _read_table(path, sheet=sheet)
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    e_col = _find_col(df, _E_ALIASES)
    i_col = _find_col(df, _I_ALIASES)
    if not e_col or not i_col:
        raise ValueError(
            "未能识别电位/电流列。请包含 E(Potential) 与 i/j(Current density)。"
            f" 当前列: {list(df.columns)}"
        )

    e = pd.to_numeric(df[e_col], errors="coerce")
    i_raw = pd.to_numeric(df[i_col], errors="coerce")
    unit = _detect_i_unit(i_col, i_raw, i_unit)
    i = i_raw / 1000.0 if unit == "mA_cm2" else i_raw

    out = pd.DataFrame({"E_V": e, "i_A_cm2": i}).dropna()
    out["log_abs_i"] = np.log10(np.maximum(np.abs(out["i_A_cm2"].to_numpy()), 1e-15))

    ecorr_c = _find_col(df, _ECORR_ALIASES)
    icorr_c = _find_col(df, _ICORR_ALIASES)
    if ecorr_c:
        out.attrs["Ecorr_V"] = float(pd.to_numeric(df[ecorr_c], errors="coerce").dropna().iloc[0])
    if icorr_c:
        ic = float(pd.to_numeric(df[icorr_c], errors="coerce").dropna().iloc[0])
        # 与主电流列同单位启发式
        if unit == "mA_cm2" and abs(ic) > 1e-3:
            ic = ic / 1000.0
        out.attrs["icorr_A_cm2"] = ic
    out.attrs["i_unit_detected"] = unit
    out.attrs["source_cols"] = {"E": e_col, "i": i_col}
    return out


def _fit_tafel(E: np.ndarray, log_i: np.ndarray, e_lo: float, e_hi: float) -> tuple[float, float] | None:
    """在 [e_lo, e_hi] 内对 log|i| = a + b*E 线性拟合，返回 (a, b)。"""
    lo, hi = min(e_lo, e_hi), max(e_lo, e_hi)
    m = (E >= lo) & (E <= hi) & np.isfinite(log_i) & np.isfinite(E)
    if m.sum() < 3:
        return None
    b, a = np.polyfit(E[m], log_i[m], 1)  # log_i = b*E + a
    return float(a), float(b)


def auto_tafel_analysis(
    df: pd.DataFrame,
    cath_offset: tuple[float, float] = (-0.15, -0.05),
    anod_offset: tuple[float, float] = (0.05, 0.15),
) -> dict:
    """自动估 Ecorr 并做阴阳极 Tafel 线性拟合。

    返回 dict 可能含：Ecorr_V, beta_a, beta_c, icorr_A_cm2, cath_window, anod_window,
    cath_fit (a,b), anod_fit (a,b)。失败的键省略，不编造。
    """
    E = df["E_V"].to_numpy(dtype=float)
    i = df["i_A_cm2"].to_numpy(dtype=float)
    log_i = df["log_abs_i"].to_numpy(dtype=float)
    result: dict = {}

    # Ecorr：优先已有 attrs；否则 |i| 最小点；再尝试 i 过零线性插值
    if df.attrs.get("Ecorr_V") is not None:
        ecorr = float(df.attrs["Ecorr_V"])
    else:
        idx = int(np.nanargmin(np.abs(i)))
        ecorr = float(E[idx])
        # 过零插值（若存在正负电流）
        sign = np.sign(i)
        cross = np.where(sign[:-1] * sign[1:] < 0)[0]
        if len(cross) > 0:
            k = int(cross[np.argmin(np.abs(E[cross] - ecorr))])
            e0, e1 = E[k], E[k + 1]
            i0, i1 = i[k], i[k + 1]
            if abs(i1 - i0) > 1e-30:
                ecorr = float(e0 - i0 * (e1 - e0) / (i1 - i0))
    result["Ecorr_V"] = ecorr

    cath_lo = ecorr + cath_offset[0]
    cath_hi = ecorr + cath_offset[1]
    anod_lo = ecorr + anod_offset[0]
    anod_hi = ecorr + anod_offset[1]
    result["cath_window"] = (cath_lo, cath_hi)
    result["anod_window"] = (anod_lo, anod_hi)

    cath = _fit_tafel(E, log_i, cath_lo, cath_hi)
    anod = _fit_tafel(E, log_i, anod_lo, anod_hi)
    if cath is not None:
        a_c, b_c = cath
        result["cath_fit"] = (a_c, b_c)
        if abs(b_c) > 1e-12:
            result["beta_c"] = float(abs(1.0 / b_c))  # V/decade
    if anod is not None:
        a_a, b_a = anod
        result["anod_fit"] = (a_a, b_a)
        if abs(b_a) > 1e-12:
            result["beta_a"] = float(abs(1.0 / b_a))  # V/decade

    # 外推交点 → icorr（两支都成功时）
    if "cath_fit" in result and "anod_fit" in result:
        a1, b1 = result["cath_fit"]
        a2, b2 = result["anod_fit"]
        if abs(b1 - b2) > 1e-12:
            e_int = (a2 - a1) / (b1 - b2)
            log_i_int = a1 + b1 * e_int
            icorr = float(10 ** log_i_int)
            if np.isfinite(icorr) and icorr > 0:
                result["icorr_A_cm2"] = icorr
                result["Ecorr_extrap_V"] = float(e_int)
    elif df.attrs.get("icorr_A_cm2") is not None:
        result["icorr_A_cm2"] = float(df.attrs["icorr_A_cm2"])

    return result


def save_tafel_params(rows: list[dict], out_stem: Path) -> str:
    """写极化/Tafel 参数 CSV。"""
    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    path = out_stem.with_name(out_stem.name + "_tafel_params.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path.resolve())


def plot_polarization(
    series: list[tuple[str, pd.DataFrame]],
    out_stem: Path,
    title: str | None = None,
    mode: str = "tafel",
    tafel_cathode: tuple[float, float] | None = None,
    tafel_anode: tuple[float, float] | None = None,
    auto_tafel: bool = False,
    show_markers: bool = False,
    colors: list[str] | None = None,
) -> tuple[list[str], list[dict]]:
    """
    mode: tafel = 半对数 E vs log|i|；linear = E vs i；both = 两栏。
    返回 (写出路径列表, Tafel 参数行列表)。
    """
    apply_journal_style()
    series_colors = colors if colors is not None else resolve_series_colors(len(series))
    if mode == "both":
        fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.0))
        ax_t, ax_l = axes
    elif mode == "linear":
        fig, ax_l = plt.subplots(figsize=(5.0, 4.0))
        ax_t = None
    else:
        fig, ax_t = plt.subplots(figsize=(5.2, 4.2))
        ax_l = None

    param_rows: list[dict] = []

    for i, (label, df) in enumerate(series):
        color = series_colors[i % len(series_colors)]
        E = df["E_V"].to_numpy()
        log_i = df["log_abs_i"].to_numpy()
        mk = dict(marker="o", markersize=2.5, markevery=max(1, len(E) // 40)) if show_markers else {}

        if ax_t is not None:
            ax_t.plot(log_i, E, color=color, label=label or None, linewidth=1.6, **mk)
        if ax_l is not None:
            ax_l.plot(df["i_A_cm2"], E, color=color, label=label or None, linewidth=1.6, **mk)

        analysis: dict = {}
        if auto_tafel:
            analysis = auto_tafel_analysis(df)
        else:
            if df.attrs.get("Ecorr_V") is not None:
                analysis["Ecorr_V"] = df.attrs["Ecorr_V"]
            if df.attrs.get("icorr_A_cm2") is not None:
                analysis["icorr_A_cm2"] = df.attrs["icorr_A_cm2"]

        # 手动窗口优先覆盖 auto 窗口拟合
        use_cath = tafel_cathode
        use_anod = tafel_anode
        if auto_tafel and not use_cath and "cath_window" in analysis:
            use_cath = analysis["cath_window"]
        if auto_tafel and not use_anod and "anod_window" in analysis:
            use_anod = analysis["anod_window"]

        ecorr = analysis.get("Ecorr_V")
        icorr = analysis.get("icorr_A_cm2")
        if ax_t is not None and ecorr is not None:
            ax_t.axhline(ecorr, color=color, linestyle=":", linewidth=1.0, alpha=0.8)
            ax_t.annotate(
                f"Ecorr≈{ecorr:.3f} V",
                xy=(float(np.nanmin(log_i)), ecorr),
                fontsize=7,
                color=color,
                xytext=(4, 4),
                textcoords="offset points",
            )
        if ax_t is not None and icorr is not None and icorr > 0:
            ax_t.axvline(np.log10(icorr), color=color, linestyle=":", linewidth=1.0, alpha=0.8)

        # 窗口拟合线
        if ax_t is not None and (use_cath or use_anod):
            lines_ab = []
            if use_cath:
                fit = _fit_tafel(E, log_i, *use_cath)
                if fit is not None:
                    a, b = fit
                    lines_ab.append(("c", a, b))
                    analysis["cath_fit"] = (a, b)
                    if abs(b) > 1e-12:
                        analysis["beta_c"] = float(abs(1.0 / b))
                    e_grid = np.linspace(min(use_cath), max(use_cath), 40)
                    ax_t.plot(a + b * e_grid, e_grid, color=color, linestyle="--", linewidth=1.1, alpha=0.85)
            if use_anod:
                fit = _fit_tafel(E, log_i, *use_anod)
                if fit is not None:
                    a, b = fit
                    lines_ab.append(("a", a, b))
                    analysis["anod_fit"] = (a, b)
                    if abs(b) > 1e-12:
                        analysis["beta_a"] = float(abs(1.0 / b))
                    e_grid = np.linspace(min(use_anod), max(use_anod), 40)
                    ax_t.plot(a + b * e_grid, e_grid, color=color, linestyle="--", linewidth=1.1, alpha=0.85)
            if len(lines_ab) == 2:
                (_, a1, b1), (_, a2, b2) = lines_ab
                if abs(b1 - b2) > 1e-12:
                    e_int = (a2 - a1) / (b1 - b2)
                    log_i_int = a1 + b1 * e_int
                    ic_ex = float(10 ** log_i_int)
                    if np.isfinite(ic_ex) and ic_ex > 0:
                        analysis["icorr_A_cm2"] = ic_ex
                        analysis["Ecorr_extrap_V"] = float(e_int)
                        ax_t.plot(log_i_int, e_int, "x", color=color, markersize=8)
                        beta_txt = ""
                        if "beta_a" in analysis:
                            beta_txt += f"βa={analysis['beta_a']*1000:.1f} mV/dec\n"
                        if "beta_c" in analysis:
                            beta_txt += f"βc={analysis['beta_c']*1000:.1f} mV/dec\n"
                        ax_t.annotate(
                            f"{beta_txt}icorr≈{ic_ex:.2e}\nE≈{e_int:.3f} V",
                            xy=(log_i_int, e_int),
                            fontsize=7,
                            color=color,
                            xytext=(8, -8),
                            textcoords="offset points",
                        )

        row = {"label": label or ""}
        for key in ("Ecorr_V", "icorr_A_cm2", "beta_a", "beta_c", "Ecorr_extrap_V"):
            if key in analysis and analysis[key] is not None:
                row[key] = analysis[key]
        if "cath_window" in analysis:
            row["cath_E1"], row["cath_E2"] = analysis["cath_window"]
        if "anod_window" in analysis:
            row["anod_E1"], row["anod_E2"] = analysis["anod_window"]
        if len(row) > 1:
            param_rows.append(row)

    if ax_t is not None:
        ax_t.set_xlabel(r"log |i| (A cm$^{-2}$)")
        ax_t.set_ylabel(r"$E$ (V)")
        ax_t.set_title("Polarization (semilog)")
        if any(lbl for lbl, _ in series):
            ax_t.legend(frameon=False, loc="best")
    if ax_l is not None:
        ax_l.set_xlabel(r"$i$ (A cm$^{-2}$)")
        ax_l.set_ylabel(r"$E$ (V)")
        ax_l.set_title("Polarization (linear)")
        if any(lbl for lbl, _ in series):
            ax_l.legend(frameon=False, loc="best")

    if title:
        fig.suptitle(title, fontsize=12, y=1.02)
    fig.tight_layout()
    paths = save_figure(fig, str(out_stem), formats=("png", "pdf"))
    return paths, param_rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="极化曲线 / Tafel 半对数出图")
    p.add_argument("input", type=Path, nargs="+", help="CSV/TXT/Excel（可多个对比）")
    p.add_argument("-o", "--output", type=Path, required=True, help="输出路径（无扩展名）")
    p.add_argument("-l", "--label", action="append", default=[], help="曲线标签")
    p.add_argument("--title", default=None)
    p.add_argument("--mode", choices=("tafel", "linear", "both"), default="tafel")
    p.add_argument("--i-unit", choices=("A_cm2", "mA_cm2"), default=None, help="强制电流密度单位")
    p.add_argument("--sheet", default=0)
    p.add_argument(
        "--tafel-cathode",
        nargs=2,
        type=float,
        metavar=("E1", "E2"),
        default=None,
        help="阴极 Tafel 拟合电位窗口 (V)",
    )
    p.add_argument(
        "--tafel-anode",
        nargs=2,
        type=float,
        metavar=("E1", "E2"),
        default=None,
        help="阳极 Tafel 拟合电位窗口 (V)",
    )
    p.add_argument(
        "--auto-tafel",
        action="store_true",
        help="自动估 Ecorr 并在阴阳极窗口做 Tafel 分析（失败则仅标 Ecorr）",
    )
    p.add_argument("--markers", action="store_true", help="显示采样点标记")
    add_color_arguments(p)
    args = p.parse_args(argv)

    sheet: str | int = args.sheet
    try:
        sheet = int(args.sheet)
    except (TypeError, ValueError):
        pass

    series: list[tuple[str, pd.DataFrame]] = []
    for i, path in enumerate(args.input):
        label = args.label[i] if i < len(args.label) else Path(path).stem
        series.append((label, load_polarization(path, sheet=sheet, i_unit=args.i_unit)))

    stem = args.output
    if stem.suffix:
        stem = stem.with_suffix("")
    try:
        series_colors = colors_from_args(args, len(series))
    except ColorError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    paths, param_rows = plot_polarization(
        series,
        stem,
        title=args.title,
        mode=args.mode,
        tafel_cathode=tuple(args.tafel_cathode) if args.tafel_cathode else None,
        tafel_anode=tuple(args.tafel_anode) if args.tafel_anode else None,
        auto_tafel=args.auto_tafel,
        show_markers=args.markers,
        colors=series_colors,
    )
    if param_rows:
        print(save_tafel_params(param_rows, stem))
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
