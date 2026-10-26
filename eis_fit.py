#!/usr/bin/env python3
"""EIS 等效电路拟合（scipy.optimize，无 impedance.py 依赖）。

支持电路（字符串别名不区分大小写）：
  - randles / Rs-Cdl-Rct      : Rs + (Rct || Cdl)
  - cpe / Rs-CPE-Rct          : Rs + (Rct || CPE)     【默认】
  - warburg / Rs-CPE-Rct-W    : Rs + ( CPE || (Rct + Zw) )，Zw = σ·ω^{-1/2}(1−j)
  - coating / 2rc / rs-q1r1-q2r2 : Rs + (R1||Q1) + (R2||Q2)  涂层双时间常数
  - lr_cpe / Rs-L-CPE-Rct     : Rs + jωL + (Rct||CPE)  高频感抗

拟合质量（贴近 ZSimpWin 习惯）：
  - 默认 modulus weighting：残差 / |Z|
  - 可选 unit weighting
  - 加权 χ²、RMSE；参数 stderr（Jacobian 近似）与相对误差 %

失败时抛 FitError，不返回假参数。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

# ---------------------------------------------------------------------------
# 电路阻抗
# ---------------------------------------------------------------------------


def z_randles(omega: np.ndarray, Rs: float, Rct: float, Cdl: float) -> np.ndarray:
    """Rs-(Cdl||Rct)。"""
    return Rs + 1.0 / (1.0 / Rct + 1j * omega * Cdl)


def z_cpe_randles(omega: np.ndarray, Rs: float, Rct: float, Q: float, n: float) -> np.ndarray:
    """Rs-(CPE||Rct)，Y_CPE = Q (jω)^n。"""
    y_cpe = Q * (1j * omega) ** n
    return Rs + 1.0 / (1.0 / Rct + y_cpe)


def z_cpe_warburg(
    omega: np.ndarray, Rs: float, Rct: float, Q: float, n: float, sigma: float
) -> np.ndarray:
    """Rs-(CPE||(Rct-W))，Zw = σ/√ω · (1−j)。"""
    y_cpe = Q * (1j * omega) ** n
    zw = sigma / np.sqrt(np.maximum(omega, 1e-30)) * (1.0 - 1j)
    return Rs + 1.0 / (y_cpe + 1.0 / (Rct + zw))


def z_coating(
    omega: np.ndarray,
    Rs: float,
    R1: float,
    Q1: float,
    n1: float,
    R2: float,
    Q2: float,
    n2: float,
) -> np.ndarray:
    """Rs + (R1||Q1) + (R2||Q2) 涂层常用双时间常数。"""
    y1 = Q1 * (1j * omega) ** n1
    y2 = Q2 * (1j * omega) ** n2
    z1 = 1.0 / (1.0 / R1 + y1)
    z2 = 1.0 / (1.0 / R2 + y2)
    return Rs + z1 + z2


def z_lr_cpe(
    omega: np.ndarray, Rs: float, L: float, Rct: float, Q: float, n: float
) -> np.ndarray:
    """Rs + jωL + (Rct||CPE)，高频感抗。"""
    y_cpe = Q * (1j * omega) ** n
    return Rs + 1j * omega * L + 1.0 / (1.0 / Rct + y_cpe)


CIRCUITS: dict[str, dict] = {
    "randles": {
        "aliases": ("randles", "rs-cdl-rct", "rs_cdl_rct", "cdl"),
        "params": ("Rs", "Rct", "Cdl"),
        "units": {"Rs": "ohm", "Rct": "ohm", "Cdl": "F"},
        "z": z_randles,
        "bounds": ([1e-6, 1e-3, 1e-12], [1e6, 1e8, 1e-2]),
        "desc": "Rs + (Rct || Cdl) 经典 Randles（理想电容）",
    },
    "cpe": {
        "aliases": ("cpe", "rs-cpe-rct", "rs_cpe_rct", "randles_cpe", "r0-cpe-rct"),
        "params": ("Rs", "Rct", "Q", "n"),
        "units": {"Rs": "ohm", "Rct": "ohm", "Q": "S·s^n", "n": "-"},
        "z": z_cpe_randles,
        "bounds": ([1e-6, 1e-3, 1e-12, 0.35], [1e6, 1e8, 1e-1, 1.0]),
        "desc": "Rs + (Rct || CPE)  【默认】",
    },
    "warburg": {
        "aliases": ("warburg", "rs-cpe-rct-w", "rs_cpe_rct_w", "randles_w", "cpe_w"),
        "params": ("Rs", "Rct", "Q", "n", "sigma"),
        "units": {"Rs": "ohm", "Rct": "ohm", "Q": "S·s^n", "n": "-", "sigma": "ohm·s^{-0.5}"},
        "z": z_cpe_warburg,
        "bounds": ([1e-6, 1e-3, 1e-12, 0.35, 1e-6], [1e6, 1e8, 1e-1, 1.0, 1e6]),
        "desc": "Rs + (CPE || (Rct + Zw))，含 Warburg",
    },
    "coating": {
        "aliases": (
            "coating",
            "2rc",
            "rs-q1r1-q2r2",
            "rs_q1r1_q2r2",
            "double_cpe",
            "2cpe",
            "coat",
        ),
        "params": ("Rs", "R1", "Q1", "n1", "R2", "Q2", "n2"),
        "units": {
            "Rs": "ohm",
            "R1": "ohm",
            "Q1": "S·s^n",
            "n1": "-",
            "R2": "ohm",
            "Q2": "S·s^n",
            "n2": "-",
        },
        "z": z_coating,
        "bounds": (
            [1e-6, 1e-2, 1e-12, 0.35, 1e-2, 1e-12, 0.35],
            [1e6, 1e9, 1e-1, 1.0, 1e9, 1e-1, 1.0],
        ),
        "desc": "Rs + (R1||Q1) + (R2||Q2) 涂层双时间常数",
    },
    "lr_cpe": {
        "aliases": ("lr_cpe", "lrcpe", "rs-l-cpe-rct", "rs_l_cpe_rct", "inductive", "l_cpe"),
        "params": ("Rs", "L", "Rct", "Q", "n"),
        "units": {"Rs": "ohm", "L": "H", "Rct": "ohm", "Q": "S·s^n", "n": "-"},
        "z": z_lr_cpe,
        "bounds": ([1e-6, 1e-12, 1e-3, 1e-12, 0.35], [1e6, 1e-2, 1e8, 1e-1, 1.0]),
        "desc": "Rs + jωL + (Rct||CPE) 高频感抗",
    },
}

DEFAULT_CIRCUIT = "cpe"
DEFAULT_WEIGHTING = "modulus"


def resolve_circuit(name: str) -> str:
    key = name.strip().lower().replace(" ", "")
    if key in ("none", "off", "false", "0"):
        return "none"
    for cid, meta in CIRCUITS.items():
        if key == cid or key in meta["aliases"]:
            return cid
    known = ", ".join(sorted(CIRCUITS)) + ", none"
    raise FitError(f"未知电路模型 '{name}'。可选: {known}")


class FitError(RuntimeError):
    """拟合或输入不满足条件时抛出（不静默失败）。"""


@dataclass
class FitResult:
    circuit: str
    label: str
    params: dict[str, float]
    units: dict[str, str]
    chi2: float
    chi2_weighted: float
    rmse: float
    n_points: int
    success: bool
    message: str
    weighting: str = DEFAULT_WEIGHTING
    param_stderr: dict[str, float] = field(default_factory=dict)
    param_rel_err_pct: dict[str, float] = field(default_factory=dict)
    freq_hz: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    z_fit: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    freq_meas: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    residual_real: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    residual_imag: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    residual_real_rel: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    residual_imag_rel: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))

    def to_row(self) -> dict:
        row = {
            "label": self.label,
            "circuit": self.circuit,
            "weighting": self.weighting,
            "chi2": self.chi2,
            "chi2_weighted": self.chi2_weighted,
            "rmse": self.rmse,
            "n_points": self.n_points,
            "success": self.success,
            "message": self.message,
        }
        for k, v in self.params.items():
            row[k] = v
            row[f"{k}_unit"] = self.units.get(k, "")
            se = self.param_stderr.get(k)
            if se is not None and np.isfinite(se):
                row[f"{k}_stderr"] = se
            rel = self.param_rel_err_pct.get(k)
            if rel is not None and np.isfinite(rel):
                row[f"{k}_rel_err_pct"] = rel
        return row

    def params_annotation(self) -> str:
        """Nyquist 角标用参数表文本（科学计数）。"""
        lines = [f"{self.circuit}  χ²_w={self.chi2_weighted:.3e}"]
        for k, v in self.params.items():
            unit = self.units.get(k, "")
            se = self.param_stderr.get(k)
            rel = self.param_rel_err_pct.get(k)
            if se is not None and np.isfinite(se) and abs(v) > 0:
                lines.append(f"{k}={v:.3e}±{se:.2e} {unit}".rstrip())
            elif rel is not None and np.isfinite(rel):
                lines.append(f"{k}={v:.3e} ({rel:.1f}%) {unit}".rstrip())
            else:
                lines.append(f"{k}={v:.3e} {unit}".rstrip())
        return "\n".join(lines)


def _prepare_z(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """返回 (freq_Hz, Z_complex)。缺频或缺阻抗则报错。"""
    if "freq" not in df.columns:
        raise FitError(
            "等效电路拟合需要频率列（freq / Frequency / f）。"
            "当前数据无 freq，无法拟合——请检查 CSV 列名。"
        )
    if not {"zreal", "zimag"}.issubset(df.columns):
        raise FitError(
            "拟合需要 Zreal 与 Zimag（或可由 |Z|+phase 推导）。"
            f"当前列: {list(df.columns)}"
        )
    sub = df[["freq", "zreal", "zimag"]].dropna()
    sub = sub[sub["freq"] > 0]
    if len(sub) < 5:
        raise FitError(f"有效频率点数过少（n={len(sub)}），至少需要约 5 点才能拟合。")
    # 高频在前，便于初值
    sub = sub.sort_values("freq", ascending=False)
    freq = sub["freq"].to_numpy(dtype=float)
    z = sub["zreal"].to_numpy(dtype=float) + 1j * sub["zimag"].to_numpy(dtype=float)
    return freq, z


def _initial_guess(circuit: str, freq: np.ndarray, z: np.ndarray) -> np.ndarray:
    zr, zi = z.real, z.imag
    # 高频 → Rs；弧直径 → Rct
    Rs = max(float(zr[0]), 1e-3)  # 已按 freq 降序
    R_tot = max(float(np.percentile(zr, 95)), Rs + 1.0)
    Rct = max(R_tot - Rs, 1.0)
    # 峰值虚部频率
    neg_zi = -zi
    idx = int(np.argmax(neg_zi)) if np.any(neg_zi > 0) else int(len(freq) // 2)
    w_peak = 2 * np.pi * max(float(freq[idx]), 1e-6)
    Cdl = 1.0 / max(w_peak * Rct, 1e-30)
    Cdl = float(np.clip(Cdl, 1e-12, 1e-2))
    Q = Cdl
    n = 0.85
    # 低频 Warburg 粗估
    sigma = max(
        float(np.abs(zr[-1] - zr[max(0, len(zr) // 2)]) * np.sqrt(2 * np.pi * freq[-1])),
        1e-3,
    )
    # 感抗粗估：高频虚部为正时 L ≈ Zimag/(ω)
    L = 1e-6
    if zi[0] > 0:
        L = float(np.clip(zi[0] / max(w_peak if idx == 0 else 2 * np.pi * freq[0], 1e-6), 1e-12, 1e-3))

    if circuit == "randles":
        return np.array([Rs, Rct, Cdl], dtype=float)
    if circuit == "cpe":
        return np.array([Rs, Rct, Q, n], dtype=float)
    if circuit == "warburg":
        return np.array([Rs, Rct, Q, n, sigma], dtype=float)
    if circuit == "coating":
        # 高频弧 R1、低频弧 R2；Q1 略小（膜）、Q2 略大（双电层）
        R1 = max(Rct * 0.35, 1.0)
        R2 = max(Rct * 0.65, 1.0)
        Q1 = float(np.clip(Q * 0.3, 1e-12, 1e-2))
        Q2 = float(np.clip(Q * 1.2, 1e-12, 1e-2))
        return np.array([Rs, R1, Q1, 0.9, R2, Q2, 0.8], dtype=float)
    if circuit == "lr_cpe":
        return np.array([Rs, L, Rct, Q, n], dtype=float)
    raise FitError(f"无初值策略: {circuit}")


def _param_stderr(res, param_names: tuple[str, ...]) -> tuple[dict[str, float], dict[str, float]]:
    """由 least_squares Jacobian 近似协方差 → stderr 与相对误差 %。"""
    stderr: dict[str, float] = {}
    rel: dict[str, float] = {}
    try:
        J = res.jac
        n, p = J.shape
        dof = max(n - p, 1)
        s_sq = float(np.sum(res.fun**2)) / dof
        jtj = J.T @ J
        cov = np.linalg.pinv(jtj) * s_sq
        se = np.sqrt(np.maximum(np.diag(cov), 0.0))
        for name, val, s in zip(param_names, res.x, se, strict=True):
            stderr[name] = float(s)
            if abs(float(val)) > 1e-30:
                rel[name] = float(100.0 * abs(s / val))
            else:
                rel[name] = float("nan")
    except Exception:  # noqa: BLE001
        for name in param_names:
            stderr[name] = float("nan")
            rel[name] = float("nan")
    return stderr, rel


def fit_eis(
    df: pd.DataFrame,
    circuit: str = DEFAULT_CIRCUIT,
    label: str = "",
    dense_points: int = 200,
    weighting: str = DEFAULT_WEIGHTING,
) -> FitResult:
    """对单条 EIS 曲线做非线性最小二乘拟合。

    weighting:
      - modulus（默认）: 残差 / |Z|，贴近 ZSimpWin modulus weighting
      - unit: 绝对残差
    """
    cid = resolve_circuit(circuit)
    if cid == "none":
        raise FitError("circuit=none 时不应调用 fit_eis")

    wkey = (weighting or DEFAULT_WEIGHTING).strip().lower()
    if wkey in ("mod", "modulus", "zsimpwin", "relative", "rel"):
        wkey = "modulus"
    elif wkey in ("unit", "absolute", "abs", "none"):
        wkey = "unit"
    else:
        raise FitError(f"未知加权方式 '{weighting}'。可选: modulus, unit")

    meta = CIRCUITS[cid]
    freq, z_meas = _prepare_z(df)
    omega = 2 * np.pi * freq
    x0 = _initial_guess(cid, freq, z_meas)
    lo, hi = meta["bounds"]
    x0 = np.clip(x0, lo, hi)
    z_fun: Callable = meta["z"]
    z_mod = np.maximum(np.abs(z_meas), 1e-30)

    def residual(x: np.ndarray) -> np.ndarray:
        z_m = z_fun(omega, *x)
        err_r = z_m.real - z_meas.real
        err_i = z_m.imag - z_meas.imag
        if wkey == "modulus":
            err_r = err_r / z_mod
            err_i = err_i / z_mod
        return np.concatenate([err_r, err_i])

    try:
        res = least_squares(
            residual,
            x0,
            bounds=(lo, hi),
            method="trf",
            ftol=1e-12,
            xtol=1e-12,
            gtol=1e-12,
            max_nfev=12000,
        )
    except Exception as exc:  # noqa: BLE001
        raise FitError(
            f"拟合数值失败（电路={cid}，标签={label or '-'}）：{exc}\n"
            f"初值={dict(zip(meta['params'], x0, strict=True))}。请检查数据单位与列名。"
        ) from exc

    if not res.success and res.cost > 1e3:
        raise FitError(
            f"拟合未收敛（电路={cid}，标签={label or '-'}）：{res.message}\n"
            f"初值={dict(zip(meta['params'], x0, strict=True))}，"
            f"终值={dict(zip(meta['params'], res.x, strict=True))}。\n"
            "可尝试 --fit randles / cpe / warburg / coating / lr_cpe，或检查量级与频段。"
        )

    params = {name: float(val) for name, val in zip(meta["params"], res.x, strict=True)}
    stderr, rel_err = _param_stderr(res, meta["params"])
    z_hat = z_fun(omega, *res.x)
    resid_r = z_hat.real - z_meas.real
    resid_i = z_hat.imag - z_meas.imag
    resid_r_rel = resid_r / z_mod
    resid_i_rel = resid_i / z_mod
    chi2 = float(np.sum(resid_r**2 + resid_i**2))
    chi2_w = float(np.sum(res.fun**2))
    rmse = float(np.sqrt(chi2 / max(len(z_meas), 1)))

    # 密集频率上的拟合曲线（便于光滑出图）
    f_dense = np.logspace(np.log10(freq.min()), np.log10(freq.max()), dense_points)
    z_dense = z_fun(2 * np.pi * f_dense, *res.x)

    ok = bool(res.success) or rmse < 0.25 * max(float(np.median(np.abs(z_meas))), 1.0)
    if not ok:
        raise FitError(
            f"拟合残差过大（RMSE={rmse:.4g} Ω，电路={cid}）。"
            f"参数={params}。请换模型（如 coating / warburg）或检查数据。"
        )

    return FitResult(
        circuit=cid,
        label=label,
        params=params,
        units=dict(meta["units"]),
        chi2=chi2,
        chi2_weighted=chi2_w,
        rmse=rmse,
        n_points=len(z_meas),
        success=bool(res.success),
        message=str(res.message),
        weighting=wkey,
        param_stderr=stderr,
        param_rel_err_pct=rel_err,
        freq_hz=f_dense,
        z_fit=z_dense,
        freq_meas=freq.copy(),
        residual_real=resid_r,
        residual_imag=resid_i,
        residual_real_rel=resid_r_rel,
        residual_imag_rel=resid_i_rel,
    )


def fit_result_to_frames(results: list[FitResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """参数总表 + 逐点拟合曲线表。"""
    rows = [r.to_row() for r in results]
    params_df = pd.DataFrame(rows)
    curve_parts = []
    for r in results:
        curve_parts.append(
            pd.DataFrame(
                {
                    "label": r.label,
                    "circuit": r.circuit,
                    "freq": r.freq_hz,
                    "zreal_fit": r.z_fit.real,
                    "zimag_fit": r.z_fit.imag,
                    "neg_zimag_fit": -r.z_fit.imag,
                    "zmod_fit": np.abs(r.z_fit),
                    "phase_fit": np.degrees(np.angle(r.z_fit)),
                }
            )
        )
    curves_df = pd.concat(curve_parts, ignore_index=True) if curve_parts else pd.DataFrame()
    return params_df, curves_df


def save_fit_outputs(results: list[FitResult], out_stem: Path) -> list[str]:
    """写 CSV + JSON，返回路径列表。"""
    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    params_df, curves_df = fit_result_to_frames(results)
    paths: list[str] = []

    p_csv = out_stem.with_name(out_stem.name + "_fit_params.csv")
    params_df.to_csv(p_csv, index=False)
    paths.append(str(p_csv.resolve()))

    p_json = out_stem.with_name(out_stem.name + "_fit_params.json")
    payload = []
    for r in results:
        payload.append(
            {
                "label": r.label,
                "circuit": r.circuit,
                "description": CIRCUITS[r.circuit]["desc"],
                "weighting": r.weighting,
                "params": r.params,
                "units": r.units,
                "param_stderr": r.param_stderr,
                "param_rel_err_pct": r.param_rel_err_pct,
                "chi2": r.chi2,
                "chi2_weighted": r.chi2_weighted,
                "rmse": r.rmse,
                "n_points": r.n_points,
                "success": r.success,
                "message": r.message,
            }
        )
    p_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    paths.append(str(p_json.resolve()))

    c_csv = out_stem.with_name(out_stem.name + "_fit_curve.csv")
    curves_df.to_csv(c_csv, index=False)
    paths.append(str(c_csv.resolve()))

    # 残差表（测量频率点）
    resid_parts = []
    for r in results:
        if len(r.freq_meas) == 0:
            continue
        resid_parts.append(
            pd.DataFrame(
                {
                    "label": r.label,
                    "circuit": r.circuit,
                    "freq": r.freq_meas,
                    "residual_real": r.residual_real,
                    "residual_imag": r.residual_imag,
                    "residual_real_rel": r.residual_real_rel,
                    "residual_imag_rel": r.residual_imag_rel,
                }
            )
        )
    if resid_parts:
        r_csv = out_stem.with_name(out_stem.name + "_fit_residual.csv")
        pd.concat(resid_parts, ignore_index=True).to_csv(r_csv, index=False)
        paths.append(str(r_csv.resolve()))
    return paths


def list_circuits_help() -> str:
    lines = ["支持的电路模型:"]
    for cid, meta in CIRCUITS.items():
        lines.append(f"  {cid:10s}  {meta['desc']}  参数: {', '.join(meta['params'])}")
    lines.append("  none        关闭拟合，仅画原始数据")
    lines.append("加权: modulus（默认，残差/|Z|）或 unit")
    return "\n".join(lines)
