#!/usr/bin/env python3
"""生成标注为 DEMO 的合成数据与示例图（非真实实验）。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEMO_DATA = Path(__file__).resolve().parent / "data"
DEMO_OUT = Path(__file__).resolve().parent / "out"
# 同步一份到实验室 figures 主题目录，方便数据仓索引
FIG_EIS = Path("/workspace/lab-data/figures/eis")
FIG_PULL = Path("/workspace/lab-data/figures/pull-off")
FIG_OTHER = Path("/workspace/lab-data/figures/other")
FIG_POLAR = Path("/workspace/lab-data/figures/polarization")


def make_demo_sem(path: Path) -> Path:
    """合成一张「类 SEM」灰度纹理图（DEMO）。"""
    rng = np.random.default_rng(42)
    w, h = 512, 384
    # 基底噪声 + 若干圆形「颗粒」
    base = rng.normal(0.35, 0.08, (h, w))
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(40):
        cy, cx = rng.integers(0, h), rng.integers(0, w)
        r = rng.uniform(8, 35)
        amp = rng.uniform(0.15, 0.45)
        base += amp * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * r**2))
    # 轻微方向性划痕
    for _ in range(8):
        y0 = rng.integers(0, h)
        base[y0 : y0 + 2, :] += rng.uniform(0.05, 0.15)
    base = (base - base.min()) / (base.max() - base.min() + 1e-12)
    img = Image.fromarray((base * 255).astype(np.uint8), mode="L")
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    # 角落水印
    draw = ImageDraw.Draw(img)
    draw.text((8, 8), "DEMO", fill=220)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")  # ensure touch
    img.save(path)
    return path


def make_demo_eis(path: Path) -> Path:
    """合成 Randles 型 EIS 曲线（DEMO）。"""
    rng = np.random.default_rng(7)
    freq = np.logspace(5, -2, 60)  # 100 kHz → 0.01 Hz
    Rs, Rct, Q, n = 20.0, 800.0, 2e-5, 0.85
    w = 2 * np.pi * freq
    # CPE: Z = 1 / (Q * (jω)^n)
    jw_n = (1j * w) ** n
    z_cpe = 1.0 / (Q * jw_n)
    z = Rs + 1.0 / (1.0 / Rct + 1.0 / z_cpe)
    # 小噪声
    z = z + rng.normal(0, 2, size=z.shape) + 1j * rng.normal(0, 2, size=z.shape)
    df = pd.DataFrame(
        {
            "freq": freq,
            "Zreal": z.real,
            "Zimag": z.imag,
            "|Z|": np.abs(z),
            "phase": np.degrees(np.angle(z)),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path



def make_demo_polarization(path: Path) -> Path:
    """合成 Butler–Volmer 型动电位极化曲线（DEMO）。"""
    rng = np.random.default_rng(11)
    Ecorr = -0.45  # V
    icorr = 2e-6   # A/cm2
    ba, bc = 0.12, 0.12  # V/dec 示意
    E = np.linspace(Ecorr - 0.35, Ecorr + 0.35, 220)
    eta = E - Ecorr
    # i = icorr * (exp(2.303*eta/ba) - exp(-2.303*eta/bc))
    i = icorr * (np.exp(2.303 * eta / ba) - np.exp(-2.303 * eta / bc))
    i = i + rng.normal(0, icorr * 0.08, size=i.shape)
    df = pd.DataFrame(
        {
            "E_V": E,
            "i_A_cm2": i,
            "Ecorr": Ecorr,
            "icorr": icorr,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path



def make_demo_ocp(path: Path) -> Path:
    """合成开路电位衰减曲线（DEMO）。"""
    rng = np.random.default_rng(33)
    t = np.linspace(0, 1800, 361)
    E_inf, E0, tau = -0.182, -0.255, 280.0
    E = E_inf + (E0 - E_inf) * np.exp(-t / tau) + rng.normal(0, 0.0008, size=t.shape)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = pd.DataFrame({"Time (s)": t, "Potential (V)": E}).to_csv(index=False)
    path.write_text(
        "# DEMO 合成开路电位：指数衰减至稳态（非真实实验）\n" + body,
        encoding="utf-8",
    )
    return path


def make_demo_pull(path: Path) -> Path:
    """合成拉拔重复数据（DEMO）。"""
    rng = np.random.default_rng(21)
    rows = []
    for group, mu, sigma, n in [
        ("Blank", 1.2, 0.15, 5),
        ("CA@MSiO2-1%", 2.1, 0.22, 5),
        ("CA@MSiO2-5%", 2.8, 0.25, 5),
        ("Commercial", 2.4, 0.30, 4),
    ]:
        for v in rng.normal(mu, sigma, n):
            rows.append({"group": group, "strength_MPa": max(0.1, v)})
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def main() -> int:
    DEMO_DATA.mkdir(parents=True, exist_ok=True)
    DEMO_OUT.mkdir(parents=True, exist_ok=True)
    for d in (FIG_EIS, FIG_PULL, FIG_OTHER, FIG_POLAR):
        d.mkdir(parents=True, exist_ok=True)

    sem_in = make_demo_sem(DEMO_DATA / "DEMO_sem_gray.png")
    eis_in = make_demo_eis(DEMO_DATA / "DEMO_eis_randles.csv")
    pull_in = make_demo_pull(DEMO_DATA / "DEMO_pull_off.csv")
    polar_in = make_demo_polarization(DEMO_DATA / "DEMO_polarization.csv")
    # 别名 DEMO_polar.csv（任务约定文件名）
    import shutil as _shutil
    _shutil.copy2(polar_in, DEMO_DATA / "DEMO_polar.csv")
    # 加 DEMO 注释头
    _p = DEMO_DATA / "DEMO_polar.csv"
    _body = _p.read_text(encoding="utf-8")
    if not _body.lstrip().startswith("#"):
        _p.write_text("# DEMO 合成极化曲线（Butler–Volmer），非真实实验。\n" + _body, encoding="utf-8")
    ocp_in = make_demo_ocp(DEMO_DATA / "DEMO_ocp.csv")

    from sem_pseudocolor import render_with_colorbar, load_gray
    from eis_plot import load_eis, plot_eis
    from pull_off_bar import load_table, summarize, plot_pull_off
    from polarization_plot import load_polarization, plot_polarization
    from ocp_plot import load_ocp, plot_ocp

    gray = load_gray(sem_in)
    sem_paths = render_with_colorbar(
        gray,
        cmap="viridis",
        stretch=True,
        low_pct=1.0,
        high_pct=99.0,
        title="DEMO · SEM pseudocolor (synthetic, not real sample)",
        out_stem=DEMO_OUT / "DEMO_sem_pseudocolor_viridis",
        formats=("png",),
    )
    # 同步到 figures/other
    import shutil

    for p in sem_paths:
        if p.endswith(".png") and "_raw" not in p:
            shutil.copy2(p, FIG_OTHER / Path(p).name)

    eis_df = load_eis(eis_in)
    from eis_fit import fit_eis, save_fit_outputs

    eis_fit = fit_eis(eis_df, circuit="cpe", label="DEMO Randles")
    eis_stem = DEMO_OUT / "DEMO_eis_nyquist_bode"
    for fp in save_fit_outputs([eis_fit], eis_stem):
        shutil.copy2(fp, FIG_EIS / Path(fp).name)
    eis_paths = plot_eis(
        [("DEMO Randles", eis_df)],
        eis_stem,
        title="DEMO · EIS + CPE fit (synthetic Randles, not real experiment)",
        layout="triple",
        fits=[eis_fit],
    )
    for pth in eis_paths:
        shutil.copy2(pth, FIG_EIS / Path(pth).name)


    polar_df = load_polarization(polar_in, i_unit="A_cm2")
    # 拟合窗口相对合成 Ecorr≈-0.45 V，仅 DEMO 示意（非真实腐蚀参数）
    polar_paths, _polar_rows = plot_polarization(
        [("DEMO BV", polar_df)],
        DEMO_OUT / "DEMO_polarization_tafel",
        title="DEMO · Polarization (synthetic Butler–Volmer, not real experiment)",
        mode="tafel",
        auto_tafel=True,
    )
    for pth in polar_paths:
        shutil.copy2(pth, FIG_POLAR / Path(pth).name)

    ocp_df = load_ocp(ocp_in)
    ocp_paths, _ocp_rows = plot_ocp(
        [("DEMO OCP", ocp_df)],
        DEMO_OUT / "DEMO_ocp",
        title="DEMO · OCP (synthetic decay to steady state, not real experiment)",
    )
    FIG_OCP = Path("/workspace/lab-data/figures/ocp")
    FIG_OCP.mkdir(parents=True, exist_ok=True)
    for pth in ocp_paths:
        shutil.copy2(pth, FIG_OCP / Path(pth).name)

    pull_sum = summarize(load_table(pull_in))
    pull_paths = plot_pull_off(
        pull_sum,
        DEMO_OUT / "DEMO_pull_off_bar",
        title="DEMO · Pull-off (synthetic data, not real experiment)",
    )
    for p in pull_paths:
        shutil.copy2(p, FIG_PULL / Path(p).name)

    readme = DEMO_OUT / "README.md"
    readme.write_text(
        "# DEMO 输出（合成数据）\n\n"
        "本目录图片与 `demo/data/` 下 CSV/PNG **均为合成演示数据**，"
        "仅用于验证工具链，**不是**洪鹤庭课题真实实验数据。\n\n"
        "生成命令：`python cli.py demo`（在 research-tools 目录，建议用 `.venv`）。\n",
        encoding="utf-8",
    )
    (DEMO_DATA / "README.md").write_text(
        "# DEMO 输入数据\n\n全部为脚本合成，文件名含 `DEMO_` 前缀。\n",
        encoding="utf-8",
    )

    print("DEMO 完成。输出：")
    for p in sem_paths + eis_paths + polar_paths + ocp_paths + pull_paths:
        print(" ", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
