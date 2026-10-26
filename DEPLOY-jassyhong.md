# 挂到 jassyhong.top · 部署交接（给 Jassy King）

## 现状（2026-10-25）
- 代码：`/workspace/lab-data/scripts/research-tools/`（v0.3.0 FastAPI Web）
- 本机已跑通：`http://127.0.0.1:8766/`（Windows LZD）
- Cloudflare 区 `jassyhong.top` 已 active
  - apex / www → GitHub Pages（`hongheting.github.io`）
  - 先例：`ref.jassyhong.top` → Azure Container Apps（文献核对）
- 本服务依赖 **Python + scipy/matplotlib**，不能塞进 Cloudflare Workers / 纯静态 Pages

## 推荐方案（与 ref 一致）
1. 容器跑 `web/Dockerfile`（端口 **8766**）
2. DNS：`tools.jassyhong.top` CNAME → 容器公网主机（或 Azure Container Apps FQDN）
3. 主站导航加链接：Tools → `https://tools.jassyhong.top/`
4. 可选：Cloudflare 橙云代理 + 缓存绕过 `/api/*`

## 本地 / 服务器构建
```bash
cd research-tools
docker compose -f web/docker-compose.yml up -d --build
# 健康检查
curl -s http://127.0.0.1:8766/health
# 期望: {"ok":true,"service":"research-tools-web","version":"0.3.0"}
```

环境变量：
- `RESEARCH_TOOLS_JOBS`：任务临时目录（默认容器内 `/tmp/research-tools-jobs`）
- `MPLCONFIGDIR`：matplotlib 缓存

## 能力清单
SEM 伪彩 · EIS 拟合（cpe/randles/warburg/coating/lr_cpe）· 极化（自动 Tafel）· OCP · 拉拔柱状图

## 不推荐
- 把 FastAPI 嵌进 GitHub Pages 静态站
- 长期 Cloudflare Tunnel 指到宿舍 Windows（不稳定）

## 需要 Jassy King 回执
- 托管选哪家（Azure Container Apps / 其他 VPS）
- 子域是否用 `tools.jassyhong.top`
- 需要我推的镜像仓库地址或 tarball 路径
