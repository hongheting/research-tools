# research-tools / 实验室科研出图

**作者 Author：** 洪鹤庭 Hong Heting（Jassyhong）  
**在线 Demo：** [https://tools.jassyhong.top](https://tools.jassyhong.top)  
**许可证 License：** MIT（见 `LICENSE`）  
**版本：** 0.3.x（CLI + FastAPI Web）

面向生物污损 / 涂层 / 电化学等实验的**一键出图**工具箱：SEM 伪彩、EIS 等效电路拟合、极化（Tafel）、OCP、拉拔柱状图——色盲友好、接近期刊版式。

> **English:** Lightweight lab plotting helpers (SEM pseudocolor, EIS fit + Nyquist/Bode, polarization, OCP, pull-off bars). Figures are **assistive**, not instrument-certified results.

---

## 一句话定位

把仪器导出的 SEM 图 / EIS 表 / 极化与拉拔数据丢进来，得到可下载的 PNG/PDF；图仅为科研辅助可视化。

## 功能要点

| 类型 | 模块 | 作用 |
|------|------|------|
| SEM 伪彩 | `sem_pseudocolor.py` | 灰度 SEM → viridis / plasma / inferno / turbo / jet… |
| EIS | `eis_plot.py` + `eis_fit.py` | 先等效电路拟合再出 Nyquist+Bode（可 `--fit none`） |
| 极化 | `polarization_plot.py` | 动电位 / Tafel 半对数（E vs log\|i\|） |
| OCP | `ocp_plot.py` | 开路电位 E–t |
| 拉拔 | `pull_off_bar.py` | 强度柱状图（均值±SD，标 n） |
| Demo | `demo/` | 合成 `DEMO_` 数据与示例图 |

配色默认 Okabe–Ito；EIS 电路含 `randles` / `cpe`（默认）/ `warburg` / `coating` / `lr_cpe` 等。

## 在线 Demo

打开 [tools.jassyhong.top](https://tools.jassyhong.top) 上传文件即可。主站入口亦见 [jassyhong.top/tools.html](https://jassyhong.top/tools.html)。

## 本地运行（CLI）

```bash
git clone https://github.com/hongheting/research-tools.git
cd research-tools

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 一键演示（合成数据）
python cli.py demo

# SEM / EIS / 极化 / 拉拔示例
python cli.py sem demo/data/DEMO_sem_gray.png -o demo/out/my_sem --cmap viridis
python cli.py eis demo/data/DEMO_eis_randles.csv -o demo/out/my_eis --fit cpe
python cli.py polar demo/data/DEMO_polarization.csv -o demo/out/my_polar --mode tafel
python cli.py pull demo/data/DEMO_pull_off.csv -o demo/out/my_pull
```

## Web / Docker

```bash
pip install -r web/requirements.txt
# 或直接：
docker compose -f web/docker-compose.yml up -d --build
curl -s http://127.0.0.1:8766/health
# 期望含 "research-tools-web"
```

浏览器打开 `http://127.0.0.1:8766/`。部署说明见 `DEPLOY-jassyhong.md`；产品边界见 `PRODUCT.md`。

## 环境变量（仅变量名）

| 变量 | 说明 |
|------|------|
| `RESEARCH_TOOLS_JOBS` | 任务临时目录（默认 `/tmp/research-tools-jobs`） |
| `MPLCONFIGDIR` | matplotlib 配置/缓存目录 |
| `PORT` | 若镜像支持覆盖监听端口（compose 默认映射 8766） |

本工具**通常不需要**云端 LLM / API Key。

## 输入约定（摘要）

- **SEM**：常见灰度/彩色图；彩色会先转灰度。
- **EIS**：`freq` + `Zreal/Zimag`（或 `freq+|Z|+phase`）；拟合失败会报错，不静默假拟合。
- **极化**：`E/Potential` + `i/I/j`；可选 Tafel 窗口。
- **拉拔**：长表 `group + strength`，或汇总 `group + mean + sd + n`。

## 免责声明

- **图仅为辅助**：伪彩、拟合曲线与柱状图用于整理与展示，**不是**计量认证或仪器官方结果。
- EIS / Tafel 拟合为常用等效电路与线性窗口示意；复杂多层体系、稳健腐蚀参数请用专业软件交叉验证。
- DEMO 数据为**合成**示例，不得当作实验结果引用。
- 上传到在线 Demo 的文件请避免未公开敏感数据；服务端任务为短时保留。

## License

MIT © 2026 Hong Heting（洪鹤庭, Jassyhong）
