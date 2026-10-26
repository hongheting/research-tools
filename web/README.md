# 科研出图工具 · Web（v0.2）

FastAPI 单页：上传 SEM / EIS / 极化 / 拉拔数据 → 调用上级 CLI 同款模块出图 → 预览 PNG + 下载 ZIP（含 PDF、EIS 拟合参数）。

## 目录

```
web/
  app.py              # FastAPI 入口
  templates/index.html
  static/{style.css,app.js}
  Dockerfile          # 构建上下文 = 上级 research-tools/
  docker-compose.yml
  requirements.txt
  README.md
```

## 本地运行（开发）

在已有 venv 中：

```bash
cd /workspace/lab-data/scripts/research-tools
source .venv/bin/activate
pip install -r requirements.txt -r web/requirements.txt
cd web
uvicorn app:app --host 0.0.0.0 --port 8766
```

浏览器打开：http://127.0.0.1:8766/

自测 EIS DEMO：

```bash
curl -s -F plot_type=eis -F fit=cpe -F color='#0072B2' \
  -F file=@../demo/data/DEMO_eis_randles.csv \
  http://127.0.0.1:8766/api/plot/json | python -m json.tool
```

或直接拿 ZIP：

```bash
curl -s -F plot_type=eis -F as_zip=1 \
  -F file=@../demo/data/DEMO_eis_randles.csv \
  -o /tmp/eis_demo.zip http://127.0.0.1:8766/api/plot
```

## Docker

**构建上下文必须是 `research-tools` 根目录**（以便 `COPY` 出图模块）：

```bash
cd /path/to/research-tools
docker build -f web/Dockerfile -t research-tools-web:0.2 .
docker run --rm -p 8766:8766 --name research-tools-web research-tools-web:0.2
```

或 compose：

```bash
cd /path/to/research-tools
docker compose -f web/docker-compose.yml up -d --build
```

健康检查：`GET /health`

## QNAP Container Station 建议

| 项 | 建议值 |
|----|--------|
| 容器名 | `research-tools-web` |
| 镜像 | `research-tools-web:0.2`（本机 build 后导出/推送，或 NAS 上 build） |
| 主机端口 | **8766**（避开已有 8765 refcheck） |
| 容器端口 | 8766 |
| 重启策略 | unless-stopped |

部署后访问：`http://192.168.0.121:8766/`（局域网）。

## API 摘要

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 上传页 |
| GET | `/health` | 健康检查 |
| POST | `/api/plot` | multipart 出图；`as_zip=1` 返回 zip，否则多文件时也 zip |
| POST | `/api/plot/json` | 同上，返回 JSON（preview_url + files） |
| GET | `/jobs/{id}/{filename}` | 下载任务产物 |

表单字段：`plot_type`（sem/eis/polar/pull）、`file`、以及 `fit` / `cmap` / `color` / `palette` / `fit_color` / `mode` 等。

## 注意

- 不编造实验数据；DEMO 仅供试跑。
- 上传上限 20 MB；任务目录 `/tmp/research-tools-jobs`，约 1 小时清理。
- EIS 拟合失败会返回 400，不会给假参数。
