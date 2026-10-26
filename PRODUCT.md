# 科研出图工具 · 产品说明（v0.3）

## 定位

给环境 / 材料 / 电化学同行用的**轻量科研出图箱**：把仪器导出的 SEM 图、EIS 表、拉拔表丢进来，得到色盲友好、接近期刊版式的 PNG/PDF。  
当前交付含**本机 CLI**与 **`web/` FastAPI 上传页**（可 Docker 部署到 NAS，端口建议 8766）；目标形态是挂在 **jassyhong.top** 上的「科研工具」栏目，人人可上传、可下载，无需配本地 Python。

作者场景：华中科技大学环境工程 · 多水域生物污损防治（涂层 / EIS / 拉拔 / UV-C·超声等），但模块不绑定单一课题。

## 核心功能（已实现）

1. **SEM 伪彩** — 灰度扫描电镜图映射到 viridis / plasma / inferno / turbo / jet 等；可选百分位对比度拉伸；输出带色标条的预览 + 无色标 raw PNG。  
2. **电化学 EIS：先拟合再成图** — 等效电路（Randles / CPE / CPE+Warburg / coating(双时间常数) / lr_cpe(感抗)，scipy 最小二乘）→ 参数表 CSV/JSON → Nyquist+Bode 叠加数据点与拟合曲线；`--fit none` 可关。  
3. **拉拔（及同类）柱状图** — 由重复数据算均值±SD，柱顶标 n；配色 Okabe–Ito。  
4. **极化曲线（Tafel / 动电位，可选自动 Tafel）· 开路电位 OCP（E–t）** — E vs log|i| 半对数（及可选线性 E–i）；多曲线叠加；可选用户给定 Ecorr/icorr 或电位窗口线性拟合标注（不默认硬估）。

后续可平行扩展：接触角柱状/箱线、防污附着计数、UV-C 剂量–响应、激光熔覆截面标注等——共用同一「图类型注册表」。

## 未来上线 jassyhong.top · 模块划分建议

```
[浏览器]  上传 SEM/CSV/Excel → 选图类型与参数 → 预览 → 下载 PNG/PDF
    │
    ▼
[前端]    /tools 路由；拖拽上传；参数表单；结果画廊
    │
    ▼
[API]     POST /api/v1/jobs  { type, options, file }
          GET  /api/v1/jobs/:id  → status + 结果 URL
    │
    ▼
[Worker]  复用本仓库 Python 模块（sem / eis / polar / pull / …）
    │
    ▼
[注册表]  plot_types.yaml
          id: eis_nyquist_bode
          entry: eis_plot:plot_eis
          accept: [csv, xlsx]
          options_schema: ...
```

建议原则：

- **个人主页**（现有 `/workspace/academic-homepage`）继续只做简历/论文/联系；科研工具作为**同域子路径或独立子应用**（如 `jassyhong.top/tools`），避免和个人站静态页强耦合。  
- **不要**在未单独设计前把重计算塞进纯静态 Pages；API + 短时 Worker（Cloudflare Workers + 队列，或轻量 VPS）更合适。  
- 上传文件默认**短时保留、可匿名**；可选登录后进「我的图」。  
- 每张图水印/元数据写明 colormap、是否拉伸、软件版本，方便审稿追溯。

## 与 academic-homepage 的关系

| | academic-homepage | research-tools |
|--|-------------------|----------------|
| 现状 | 静态个人站 | 本目录 CLI |
| 建议 | 首页加「科研工具」入口链接即可 | 独立部署 `/tools` |
| 本阶段 | **不改**个人站源码（除非你明确要求加入口） | 先把图类型与 API 边界定清 |

## 已知限制（v0.1）

- 无 Web UI；无用户账户。  
- EIS 目前为单时间常数族（Randles/CPE/Warburg），**多时间常数 / 涂层多层电路尚未做**。  
- 极化曲线的 Tafel 拟合仅为指定窗口线性示意，非稳健腐蚀参数算法。  
- SEM 伪彩不做尺度条识别 / 放大倍率 OCR。  
- 中文字体依赖环境；无 CJK 字体时标题中文可能缺字（英文与符号正常）。  
- DEMO 数据为合成，不能当实验结果引用。

## 下一版建议

1. FastAPI 薄封装 + 前端单页，对齐上述 API。  
2. 图类型注册表 + 插件目录，便于加「接触角」「附着计数」。  
3. EIS：多时间常数（如 Rs-(CPE1\|R1)-(CPE2\|R2)）、KKT 检验、置信区间。  
4. 批量：文件夹拖入 → zip 打包下载。  
5. 在 jassyhong.top 导航增加 Tools 入口（改 homepage 一处链接）。
