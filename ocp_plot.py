#!/usr/bin/env python3
"""开路电位（OCP / OCV）出图：E vs t（或点序号）。

列名灵活识别（大小写不敏感，去括号单位）：
- 电位（必须）：Potential (V) / E / OCP / Eoc / Voc / Ewe …
- 时间（可选）：time / t / Elapsed / 时间 …
- 若无时间列（仪器常只导出 Potential + Current）：用点序号 0..N-1 作横轴；
  可用 --dt 秒/点 换算为时间。Current 列忽略（不用于 OCP 主图）。

支持 csv / txt / tsv / xlsx。图上标注终值 OCP；可选末段均值与相对初段漂移。
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

_T_ALIASES = (
    "time",
    "t",
    "times",
    "elapsed",
    "elapsedtime",
    "time_s",
    "ts",
    "时间",
    "计时",
)
_E_ALIASES = (
    "e",
    "potential",
    "ocp",
    "eoc",
    "e_oc",
    "voc",
    "ewe",
    "ewe/v",
    "voltage",
    "v",
    "开路电位",
    "电位",
    "电势",
)


def _norm_col(name: str) -> str:
    s = str(name).strip().lower().replace("（", "(").replace("）", ")")
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace(" ", "").replace("_", "")
    for ch in ("Ω", "ohm", "ohms", "°", "deg", "/"):
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
            if an == key or (len(an) > 1 and (an in key or key in an)):
                return orig
    return None


def _read_table(path: Path, sheet: str | int = 0) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet)
    return pd.read_csv(path, sep=None, engine="python", comment="#")


def load_ocp(path: Path, sheet: str | int = 0, dt: float | None = None) -> pd.DataFrame:
    """读表 → t_s, E_V。

    无时间列时：t = 点序号 * dt（dt 默认 1.0，横轴语义为点序号或秒）。
    """
    path = Path(path)
    df = _read_table(path, sheet=sheet)
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    e_col = _find_col(df, _E_ALIASES)
    if not e_col:
        raise ValueError(
            "未能识别电位列。请包含 Potential (V) / E / OCP / Eoc 等。"
            f" 当前列: {list(df.columns)}"
        )

    e = pd.to_numeric(df[e_col], errors="coerce")
    t_col = _find_col(df, _T_ALIASES)
    time_synthetic = False
    if t_col:
        t = pd.to_numeric(df[t_col], errors="coerce")
        out = pd.DataFrame({"t_s": t, "E_V": e}).dropna()
        out = out.sort_values("t_s").reset_index(drop=True)
        x_label = "t_s"
    else:
        # Gamry 等常导出 Potential + Current，无时间戳
        mask = e.notna()
        e_ok = e[mask].reset_index(drop=True)
        step = float(dt) if dt is not None and dt > 0 else 1.0
        t_ok = pd.Series(np.arange(len(e_ok), dtype=float) * step)
        out = pd.DataFrame({"t_s": t_ok, "E_V": e_ok})
        time_synthetic = True
        x_label = "index_dt" if (dt is not None and dt > 0) else "index"

    out.attrs["source_cols"] = {"t": t_col or "(synthetic index)", "E": e_col}
    out.attrs["time_synthetic"] = time_synthetic
    out.attrs["x_kind"] = x_label
    out.attrs["dt"] = float(dt) if dt is not None and dt > 0 else (1.0 if time_synthetic else None)
    return out


def summarize_ocp(df: pd.DataFrame, tail_frac: float = 0.1, head_frac: float = 0.1) -> dict:
    """终值、末段均值、初段均值、漂移（末−初）。"""
    e = df["E_V"].to_numpy(dtype=float)
    t = df["t_s"].to_numpy(dtype=float)
    n = len(e)
    if n == 0:
        return {}
    n_tail = max(1, int(round(n * tail_frac)))
    n_head = max(1, int(round(n * head_frac)))
    e_final = float(e[-1])
    e_tail = float(np.mean(e[-n_tail:]))
    e_head = float(np.mean(e[:n_head]))
    out = {
        "E_final_V": e_final,
        "E_tail_mean_V": e_tail,
        "E_head_mean_V": e_head,
        "drift_V": e_tail - e_head,
        "t_start_s": float(t[0]),
        "t_end_s": float(t[-1]),
        "n_points": n,
        "time_synthetic": bool(df.attrs.get("time_synthetic", False)),
    }
    if df.attrs.get("dt") is not None:
        out["dt"] = float(df.attrs["dt"])
    return out


def plot_ocp(
    series: list[tuple[str, pd.DataFrame]],
    out_stem: Path,
    title: str | None = None,
    show_drift: bool = True,
    colors: list[str] | None = None,
) -> tuple[list[str], list[dict]]:
    """画 E vs t，标注终值 OCP；可选漂移。返回 (路径, 参数行)。"""
    apply_journal_style()
    series_colors = colors if colors is not None else resolve_series_colors(len(series))
    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    rows: list[dict] = []

    for i, (label, df) in enumerate(series):
        color = series_colors[i % len(series_colors)]
        t = df["t_s"].to_numpy()
        e = df["E_V"].to_numpy()
        ax.plot(t, e, color=color, linewidth=1.6, label=label or None)
        stats = summarize_ocp(df)
        if not stats:
            continue
        row = {"label": label or "", **stats}
        rows.append(row)
        e_f = stats["E_final_V"]
        ax.axhline(e_f, color=color, linestyle=":", linewidth=1.0, alpha=0.75)
        note = f"OCP≈{e_f:.4f} V"
        if show_drift and "drift_V" in stats:
            note += f"\ndrift(tail−head)≈{stats['drift_V']*1000:.2f} mV"
        ax.annotate(
            note,
            xy=(float(t[-1]), e_f),
            fontsize=8,
            color=color,
            xytext=(-5, 8),
            textcoords="offset points",
            ha="right",
        )

    # 横轴：有真实时间用 t(s)；否则点序号（或 dt 换算后的秒）
    any_synth = any(df.attrs.get("time_synthetic") for _, df in series)
    all_real = all(not df.attrs.get("time_synthetic") for _, df in series)
    if all_real:
        ax.set_xlabel(r"$t$ (s)")
    elif any(df.attrs.get("x_kind") == "index_dt" for _, df in series):
        ax.set_xlabel(r"$t$ (s, index$\times\Delta t$)")
    else:
        ax.set_xlabel("Sample index")
    ax.set_ylabel(r"$E$ (V)")
    ax.set_title(title or ("Open circuit potential" + (" (no time column)" if any_synth else "")))
    if any(lbl for lbl, _ in series):
        ax.legend(frameon=False, loc="best")
    fig.tight_layout()
    paths = save_figure(fig, str(out_stem), formats=("png", "pdf"))
    return paths, rows


def save_ocp_params(rows: list[dict], out_stem: Path) -> str:
    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    path = out_stem.with_name(out_stem.name + "_ocp_params.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path.resolve())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="开路电位 OCP：E vs t 出图")
    p.add_argument("input", type=Path, nargs="+", help="CSV/TXT/Excel（可多个对比）")
    p.add_argument("-o", "--output", type=Path, required=True, help="输出路径（无扩展名）")
    p.add_argument("-l", "--label", action="append", default=[], help="曲线标签")
    p.add_argument("--title", default=None)
    p.add_argument("--sheet", default=0)
    p.add_argument(
        "--dt",
        type=float,
        default=None,
        help="无时间列时每点间隔（秒）；默认按点序号 0,1,2…",
    )
    p.add_argument("--no-drift", action="store_true", help="不标注漂移")
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
        series.append((label, load_ocp(path, sheet=sheet, dt=args.dt)))

    stem = args.output
    if stem.suffix:
        stem = stem.with_suffix("")
    try:
        series_colors = colors_from_args(args, len(series))
    except ColorError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    paths, rows = plot_ocp(
        series,
        stem,
        title=args.title,
        show_drift=not args.no_drift,
        colors=series_colors,
    )
    if rows:
        print(save_ocp_params(rows, stem))
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
