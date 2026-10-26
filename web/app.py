#!/usr/bin/env python3
"""科研出图工具 · Web 上传页（FastAPI）。

复用上级目录的 sem / eis / polar / ocp / pull 模块，不重写算法。
"""
from __future__ import annotations

import shutil
import sys
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 保证可 import 上级 research-tools 模块
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eis_fit import FitError, fit_eis, resolve_circuit, save_fit_outputs  # noqa: E402
from eis_plot import load_eis, plot_eis  # noqa: E402
from lib.colors import ColorError, parse_color, resolve_series_colors  # noqa: E402
from polarization_plot import load_polarization, plot_polarization, save_tafel_params  # noqa: E402
from ocp_plot import load_ocp, plot_ocp, save_ocp_params  # noqa: E402
from pull_off_bar import load_table, plot_pull_off, summarize  # noqa: E402
from sem_pseudocolor import COLORMAPS, load_gray, render_with_colorbar  # noqa: E402

# Docker 可设 RESEARCH_TOOLS_JOBS=/tmp/research-tools-jobs；本机默认 _jobs/
_jobs_env = __import__("os").environ.get("RESEARCH_TOOLS_JOBS", "").strip()
TMP_ROOT = Path(_jobs_env) if _jobs_env else (Path(__file__).resolve().parent.parent / "_jobs")
TMP_ROOT.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
JOB_TTL_SEC = 3600  # 1 h
ALLOWED_PLOT = frozenset({"sem", "eis", "polar", "ocp", "pull"})
ALLOWED_EXT = {
    "sem": {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"},
    "eis": {".csv", ".txt", ".tsv", ".xlsx", ".xls"},
    "polar": {".csv", ".txt", ".tsv", ".xlsx", ".xls"},
    "ocp": {".csv", ".txt", ".tsv", ".xlsx", ".xls"},
    "pull": {".csv", ".txt", ".tsv", ".xlsx", ".xls"},
}

app = FastAPI(title="科研出图工具", version="0.3.0")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


def _cleanup_old_jobs() -> None:
    now = time.time()
    if not TMP_ROOT.exists():
        return
    for p in TMP_ROOT.iterdir():
        try:
            if p.is_dir() and now - p.stat().st_mtime > JOB_TTL_SEC:
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file() and now - p.stat().st_mtime > JOB_TTL_SEC:
                p.unlink(missing_ok=True)
        except OSError:
            continue


def _safe_suffix(filename: str | None) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


async def _save_upload(upload: UploadFile, dest: Path, plot_type: str) -> Path:
    suffix = _safe_suffix(upload.filename)
    allowed = ALLOWED_EXT.get(plot_type, set())
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"文件类型不支持（{suffix or '无扩展名'}）。{plot_type} 允许: {', '.join(sorted(allowed))}",
        )
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB）")
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    dest.write_bytes(data)
    return dest


def _parse_colors(color: str | None, colors: str | None, palette: str, n: int) -> list[str]:
    try:
        return resolve_series_colors(
            n,
            color=color.strip() if color and color.strip() else None,
            colors=colors.strip() if colors and colors.strip() else None,
            palette=(palette or "okabe").strip() or "okabe",
        )
    except ColorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_sem(inp: Path, out_dir: Path, cmap: str, title: str | None, stretch: bool) -> list[Path]:
    gray = load_gray(inp)
    stem = out_dir / "result"
    paths = render_with_colorbar(
        gray,
        cmap=cmap or "viridis",
        stretch=stretch,
        low_pct=1.0,
        high_pct=99.0,
        title=title,
        out_stem=stem,
        formats=("png",),
    )
    return [Path(p) for p in paths]


def _run_eis(
    inp: Path,
    out_dir: Path,
    *,
    fit: str,
    label: str,
    title: str | None,
    color: str | None,
    colors: str | None,
    palette: str,
    fit_color: str | None,
    layout: str,
    weighting: str = "modulus",
) -> list[Path]:
    from eis_plot import plot_eis_residuals

    df = load_eis(inp)
    lbl = label.strip() if label and label.strip() else inp.stem
    series = [(lbl, df)]
    series_colors = _parse_colors(color, colors, palette, 1)
    fit_c = None
    if fit_color and fit_color.strip():
        try:
            fit_c = parse_color(fit_color.strip())
        except ColorError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        circuit = resolve_circuit(fit or "cpe")
    except FitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stem = out_dir / "result"
    fits = []
    if circuit != "none":
        try:
            fits.append(fit_eis(df, circuit=circuit, label=lbl, weighting=weighting or "modulus"))
        except FitError as exc:
            raise HTTPException(status_code=400, detail=f"拟合失败: {exc}") from exc
        save_fit_outputs(fits, stem)
        plot_eis_residuals(fits, stem, title=f"Fit residual ({circuit})", colors=series_colors)

    plot_title = title
    if plot_title is None or plot_title.strip() == "":
        plot_title = f"EIS fit ({circuit})" if circuit != "none" else None

    paths = plot_eis(
        series,
        stem,
        title=plot_title,
        layout=layout if layout in ("triple", "dual") else "triple",
        fits=fits or None,
        colors=series_colors,
        fit_color=fit_c,
    )
    return [Path(p) for p in paths] + list(out_dir.glob("result_fit_*"))


def _run_polar(
    inp: Path,
    out_dir: Path,
    *,
    label: str,
    title: str | None,
    mode: str,
    color: str | None,
    colors: str | None,
    palette: str,
    auto_tafel: bool = True,
) -> list[Path]:
    df = load_polarization(inp)
    lbl = label.strip() if label and label.strip() else inp.stem
    series = [(lbl, df)]
    series_colors = _parse_colors(color, colors, palette, 1)
    stem = out_dir / "result"
    m = mode if mode in ("tafel", "linear", "both") else "tafel"
    paths, param_rows = plot_polarization(
        series,
        stem,
        title=title.strip() if title and title.strip() else None,
        mode=m,
        auto_tafel=auto_tafel,
        colors=series_colors,
    )
    out = [Path(p) for p in paths]
    if param_rows:
        out.append(Path(save_tafel_params(param_rows, stem)))
    return out


def _run_ocp(
    inp: Path,
    out_dir: Path,
    *,
    label: str,
    title: str | None,
    color: str | None,
    colors: str | None,
    palette: str,
) -> list[Path]:
    df = load_ocp(inp)
    lbl = label.strip() if label and label.strip() else inp.stem
    series = [(lbl, df)]
    series_colors = _parse_colors(color, colors, palette, 1)
    stem = out_dir / "result"
    paths, rows = plot_ocp(
        series,
        stem,
        title=title.strip() if title and title.strip() else None,
        colors=series_colors,
    )
    out = [Path(p) for p in paths]
    if rows:
        out.append(Path(save_ocp_params(rows, stem)))
    return out


def _run_pull(
    inp: Path,
    out_dir: Path,
    *,
    title: str | None,
    color: str | None,
    colors: str | None,
    palette: str,
) -> list[Path]:
    df = load_table(inp)
    summary = summarize(df)
    series_colors = _parse_colors(color, colors, palette, len(summary))
    stem = out_dir / "result"
    paths = plot_pull_off(
        summary,
        stem,
        title=title.strip() if title and title.strip() else None,
        colors=series_colors,
    )
    return [Path(p) for p in paths]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "colormaps": COLORMAPS,
            "max_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        },
    )


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": "research-tools-web", "version": "0.3.0"}


@app.post("/api/plot")
async def api_plot(
    plot_type: str = Form(...),
    file: UploadFile = File(...),
    # common
    title: str = Form(""),
    label: str = Form(""),
    color: str = Form(""),
    colors: str = Form(""),
    palette: str = Form("okabe"),
    # eis
    fit: str = Form("cpe"),
    fit_color: str = Form(""),
    layout: str = Form("triple"),
    # sem
    cmap: str = Form("viridis"),
    stretch: str = Form("1"),
    # polar
    mode: str = Form("tafel"),
    auto_tafel: str = Form("1"),
    # eis weighting
    weighting: str = Form("modulus"),
    # response preference
    as_zip: str = Form("0"),
):
    """上传文件出图。默认返回主 PNG；as_zip=1 时打包全部产物。"""
    _cleanup_old_jobs()
    plot_type = (plot_type or "").strip().lower()
    if plot_type not in ALLOWED_PLOT:
        raise HTTPException(status_code=400, detail=f"未知图类型: {plot_type}")

    job_id = uuid.uuid4().hex[:12]
    job_dir = TMP_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    inp = job_dir / f"input{_safe_suffix(file.filename) or '.bin'}"

    try:
        await _save_upload(file, inp, plot_type)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    try:
        if plot_type == "sem":
            out_paths = _run_sem(
                inp,
                job_dir,
                cmap=cmap or "viridis",
                title=title.strip() or None,
                stretch=stretch not in ("0", "false", "False", "no"),
            )
        elif plot_type == "eis":
            out_paths = _run_eis(
                inp,
                job_dir,
                fit=fit or "cpe",
                label=label,
                title=title.strip() or None,
                color=color or None,
                colors=colors or None,
                palette=palette or "okabe",
                fit_color=fit_color or None,
                layout=layout or "triple",
                weighting=weighting or "modulus",
            )
        elif plot_type == "polar":
            out_paths = _run_polar(
                inp,
                job_dir,
                label=label,
                title=title.strip() or None,
                mode=mode or "tafel",
                color=color or None,
                colors=colors or None,
                palette=palette or "okabe",
                auto_tafel=auto_tafel not in ("0", "false", "False", "no"),
            )
        elif plot_type == "ocp":
            out_paths = _run_ocp(
                inp,
                job_dir,
                label=label,
                title=title.strip() or None,
                color=color or None,
                colors=colors or None,
                palette=palette or "okabe",
            )
        else:  # pull
            out_paths = _run_pull(
                inp,
                job_dir,
                title=title.strip() or None,
                color=color or None,
                colors=colors or None,
                palette=palette or "okabe",
            )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"出图失败: {exc}") from exc

    # 去重并只保留 job_dir 内文件
    unique: list[Path] = []
    seen: set[str] = set()
    for p in out_paths:
        rp = Path(p).resolve()
        if not rp.exists() or not str(rp).startswith(str(job_dir.resolve())):
            continue
        key = str(rp)
        if key in seen:
            continue
        seen.add(key)
        unique.append(rp)

    if not unique:
        raise HTTPException(status_code=500, detail="出图完成但未找到输出文件")

    want_zip = as_zip in ("1", "true", "True", "yes") or len(unique) > 1
    # 若只要预览且有 png，可直接返回 png；多文件或 as_zip 则 zip
    pngs = [p for p in unique if p.suffix.lower() == ".png" and not p.name.endswith("_raw.png")]
    if not want_zip and len(unique) == 1 and unique[0].suffix.lower() == ".png":
        return FileResponse(unique[0], media_type="image/png", filename=unique[0].name)
    if not want_zip and pngs:
        # 仍提供 zip 下载链接信息：浏览器表单默认 as_zip；API 可单图
        pass

    if want_zip or len(unique) > 1:
        zip_path = job_dir / "result.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in unique:
                zf.write(p, arcname=p.name)
        # 也写一个 manifest 方便前端
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"{plot_type}_{job_id}.zip",
            headers={"X-Job-Id": job_id},
        )

    return FileResponse(unique[0], media_type="application/octet-stream", filename=unique[0].name)


@app.post("/api/plot/json")
async def api_plot_json(
    plot_type: str = Form(...),
    file: UploadFile = File(...),
    title: str = Form(""),
    label: str = Form(""),
    color: str = Form(""),
    colors: str = Form(""),
    palette: str = Form("okabe"),
    fit: str = Form("cpe"),
    fit_color: str = Form(""),
    layout: str = Form("triple"),
    cmap: str = Form("viridis"),
    stretch: str = Form("1"),
    mode: str = Form("tafel"),
    auto_tafel: str = Form("1"),
    weighting: str = Form("modulus"),
):
    """出图并返回 JSON：job_id + 可下载文件列表（相对 /jobs/{id}/...）。"""
    # 复用 api_plot 逻辑：直接内部跑
    _cleanup_old_jobs()
    plot_type = (plot_type or "").strip().lower()
    if plot_type not in ALLOWED_PLOT:
        raise HTTPException(status_code=400, detail=f"未知图类型: {plot_type}")

    job_id = uuid.uuid4().hex[:12]
    job_dir = TMP_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    inp = job_dir / f"input{_safe_suffix(file.filename) or '.bin'}"
    await _save_upload(file, inp, plot_type)

    try:
        if plot_type == "sem":
            out_paths = _run_sem(inp, job_dir, cmap=cmap or "viridis", title=title.strip() or None, stretch=stretch not in ("0", "false", "no"))
        elif plot_type == "eis":
            out_paths = _run_eis(
                inp, job_dir, fit=fit or "cpe", label=label, title=title.strip() or None,
                color=color or None, colors=colors or None, palette=palette or "okabe",
                fit_color=fit_color or None, layout=layout or "triple",
                weighting=weighting or "modulus",
            )
        elif plot_type == "polar":
            out_paths = _run_polar(
                inp, job_dir, label=label, title=title.strip() or None, mode=mode or "tafel",
                color=color or None, colors=colors or None, palette=palette or "okabe",
                auto_tafel=auto_tafel not in ("0", "false", "False", "no"),
            )
        elif plot_type == "ocp":
            out_paths = _run_ocp(
                inp, job_dir, label=label, title=title.strip() or None,
                color=color or None, colors=colors or None, palette=palette or "okabe",
            )
        else:
            out_paths = _run_pull(
                inp, job_dir, title=title.strip() or None,
                color=color or None, colors=colors or None, palette=palette or "okabe",
            )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"出图失败: {exc}") from exc

    files = []
    for p in out_paths:
        rp = Path(p).resolve()
        if rp.exists() and str(rp).startswith(str(job_dir.resolve())):
            files.append({"name": rp.name, "url": f"/jobs/{job_id}/{rp.name}"})

    # 去重
    seen = set()
    uniq_files = []
    for f in files:
        if f["name"] in seen:
            continue
        seen.add(f["name"])
        uniq_files.append(f)

    # zip
    zip_path = job_dir / "result.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in uniq_files:
            zf.write(job_dir / f["name"], arcname=f["name"])
    uniq_files.append({"name": "result.zip", "url": f"/jobs/{job_id}/result.zip"})

    preview = next((f["url"] for f in uniq_files if f["name"].endswith(".png") and "_raw" not in f["name"]), None)
    return JSONResponse(
        {
            "ok": True,
            "job_id": job_id,
            "plot_type": plot_type,
            "preview_url": preview,
            "files": uniq_files,
            "note": "结果约 1 小时后自动清理。DEMO 合成数据请勿当正式实验结果引用。",
        }
    )


@app.get("/jobs/{job_id}/{filename}")
async def get_job_file(job_id: str, filename: str):
    if not job_id.isalnum() or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法路径")
    path = (TMP_ROOT / job_id / filename).resolve()
    if not str(path).startswith(str(TMP_ROOT.resolve())) or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    media = "image/png" if path.suffix.lower() == ".png" else (
        "application/pdf" if path.suffix.lower() == ".pdf" else (
            "application/zip" if path.suffix.lower() == ".zip" else "application/octet-stream"
        )
    )
    return FileResponse(path, media_type=media, filename=path.name)


# 便于 `python -m uvicorn` / `python app.py`
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8766, reload=False)
