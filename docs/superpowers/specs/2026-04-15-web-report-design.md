# Power BI Web 报告系统设计

> **日期**：2026-04-15
> **状态**：已批准
> **方案**：预部署 React Shell + Vercel Blob

---

## 1. 背景与目标

### 现状

powerbi-analysis skill 通过 MCP 调用 Power BI 获取语义模型数据，使用 matplotlib 生成静态 PNG 图表，输出到本地 `output/` 目录。报告只能本地查看，无法分享。

### 目标

1. **Web 报告**：将分析结果以交互式 Web 页面呈现，支持 Recharts 图表组件
2. **公网可访问**：用户获得一个可点击的公网 URL
3. **仪表板**：报告首页展示所有历史报告列表
4. **快速生成**：从分析完成到获得 URL，在 5 秒以内
5. **技术栈一致**：沿用 Data Dive 的前端技术路线（React + Tailwind + Recharts）

---

## 2. 架构概览

```
┌─────────────────────────────────────────────────┐
│          Vercel Project (一次性部署)              │
│                                                  │
│  ┌──────────────┐   ┌─────────────────────────┐  │
│  │ React 前端    │   │ API Routes              │  │
│  │ /            │◄──►│ GET  /api/reports       │  │
│  │ /report/:id  │   │ GET  /api/reports/[id]  │  │
│  │              │   │ POST /api/reports       │  │
│  │ Recharts     │   │ DELETE /api/reports/[id]│  │
│  │ Tailwind CSS │   └────────┬────────────────┘  │
│  └──────────────┘            │                   │
│                               ▼                   │
│                      ┌──────────────┐            │
│                      │ Vercel Blob  │            │
│                      │ reports/*.json           │
│                      │ reports-index.json       │
│                      └──────────────┘            │
└─────────────────────────────────────────────────┘
         ▲
         │ POST /api/reports (上传 JSON)
         │
    Python: scripts/web_report_builder.py

    输出 URL: https://pbi-reports.vercel.app/report/{id}
```

**核心原理**：React 应用和 API Routes 一次性部署到 Vercel。报告数据以 JSON 存储在 Vercel Blob 中。每次生成新报告只需通过 API 上传 ~5KB JSON，返回公网 URL。

---

## 3. Vercel 项目结构

```
web-report/
├── src/                          # React 前端
│   ├── App.jsx                   # 路由: / → Dashboard, /report/:id → Report
│   ├── pages/
│   │   ├── Dashboard.jsx         # 报告列表
│   │   └── Report.jsx            # 报告详情
│   ├── components/
│   │   ├── Header.jsx            # 顶部导航栏
│   │   ├── InsightCard.jsx       # 单条洞察卡片
│   │   ├── ChartContainer.jsx    # Recharts 图表容器
│   │   ├── ReportCard.jsx        # 报告列表卡片
│   │   ├── StatsOverview.jsx     # 统计概览
│   │   ├── ExportButton.jsx      # PDF 导出按钮
│   │   └── EmptyState.jsx        # 空状态提示
│   ├── utils/
│   │   ├── pdfExporter.js        # PDF 导出工具
│   │   └── chartConfig.js        # 图表配置
│   ├── index.css                 # Tailwind + CSS 变量 + 动画
│   └── main.jsx                  # React 入口
├── api/                          # Vercel Serverless Functions
│   └── reports/
│       ├── index.ts              # GET (列表) + POST (上传)
│       └── [id].ts               # GET (单个) + DELETE
├── lib/
│   └── blob.ts                   # Vercel Blob 操作封装
├── package.json
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── vercel.json
├── index.html
├── .env.local                    # BLOB_READ_WRITE_TOKEN, API_SECRET
└── .env.example                  # 环境变量模板
```

---

## 4. API Routes 规格

### 4.1 `POST /api/reports` — 上传或覆写报告

**用途**：Python 脚本调用，上传报告 JSON 到 Blob。**支持 Upsert 语义**：相同 ID 的报告会覆写已有数据，适用于用户多次追问同一主题的场景。

**鉴权**：`Authorization: Bearer {API_SECRET}`

**Request Body**：
```json
{
  "id": "report-20260415-流失分析",
  "meta": {
    "title": "超级VIP月度流失回流分析",
    "generated_at": "2026-04-15T14:30:00",
    "model": "超级VIP",
    "version": "1.0"
  },
  "summary": {
    "overall": "...",
    "total_conclusions": 5,
    "high_importance_count": 2
  },
  "conclusions": [...]
}
```

**处理逻辑**：
1. 校验 Bearer Token
2. `blob.put("reports/{id}.json", JSON.stringify(body))` — 存储报告（同 ID 覆写）
3. 读取 `reports-index.json`（不存在则创建空数组）
4. **索引去重**：检查数组中是否已存在相同 `id` 的条目
   - **已存在**（覆写场景）：更新该条目的 `title`、`summary_preview`、`stats`，并将条目移至数组头部（保持最新排序）
   - **不存在**（新建场景）：在数组头部插入新条目
   ```json
   {
     "id": "report-20260415-流失分析",
     "title": "超级VIP月度流失回流分析",
     "created_at": "2026-04-15T14:30:00",
     "summary_preview": "...(前100字)",
     "stats": { "total_conclusions": 5, "high_importance": 2 }
   }
   ```
5. `blob.put("reports-index.json", updatedIndex)` — 更新索引

**Response** (200)：
```json
{ "url": "/report/report-20260415-流失分析", "updated": true }
```

> **`updated` 字段**：`false` 表示新建报告，`true` 表示覆写已有报告。前端可据此提示用户"报告已更新"。

**Response** (401)：Token 无效。

---

### 4.2 `GET /api/reports` — 获取报告列表

**用途**：Dashboard 页面调用，展示所有报告。

**无鉴权**（公开只读）。

**处理逻辑**：
1. `blob.get("reports-index.json")` → 返回 JSON 数组
2. 数组已按创建时间倒序排列（新报告插入头部）

**Response** (200)：
```json
{
  "reports": [
    {
      "id": "report-20260415-流失分析",
      "title": "超级VIP月度流失回流分析",
      "created_at": "2026-04-15T14:30:00",
      "summary_preview": "...",
      "stats": { "total_conclusions": 5, "high_importance": 2 }
    }
  ]
}
```

---

### 4.3 `GET /api/reports/[id]` — 获取单个报告

**用途**：Report 页面调用，获取完整报告数据。

**无鉴权**（公开只读）。

**处理逻辑**：
1. `blob.get("reports/{id}.json")` → 返回完整报告 JSON

**Response** (200)：完整的 report JSON（meta + summary + conclusions）。

**Response** (404)：报告不存在。

---

### 4.4 `DELETE /api/reports/[id]` — 删除报告（可选）

**鉴权**：Bearer Token。

**处理逻辑**：
1. `blob.del("reports/{id}.json")`
2. 更新 `reports-index.json` 移除对应条目

---

## 5. 报告 JSON Schema

```json
{
  "meta": {
    "title": "报告标题（必填）",
    "generated_at": "ISO 8601 时间戳（必填）",
    "model": "语义模型名称（可选）",
    "version": "1.0"
  },
  "summary": {
    "overall": "整体结论概述（必填）",
    "total_conclusions": 5,
    "high_importance_count": 2
  },
  "conclusions": [
    {
      "id": 1,
      "title": "结论标题（必填）",
      "description": "详细描述（必填）",
      "data_support": "数据支撑文本（可选）",
      "importance": "high | medium | low",
      "chart_type": "bar | line | pie | scatter | combo",
      "chart_data": {
        // 格式参考 ChartContainer 支持的类型
        // bar: { "xKey": "name", "yKey": "value", "data": [...] }
        // line: { "x_labels": [...], "series": { "指标名": [...] } }
        // pie: { "labels": [...], "values": [...] }
        // scatter: { "x": [...], "y": [...], "x_title": "...", "y_title": "..." }
      }
    }
  ]
}
```

**chart_data 格式**与 Data Dive 的 `ChartContainer.jsx` 完全兼容，支持 bar / line / pie / scatter 四种图表类型。

---

## 6. Python 上传脚本

### 6.1 位置

`scripts/web_report_builder.py`

### 6.2 接口

```python
class WebReportBuilder:
    def __init__(self, vercel_url: str, api_secret: str):
        """初始化
        Args:
            vercel_url: Vercel 项目 URL，如 https://pbi-reports.vercel.app
            api_secret: API 密钥，用于 POST 鉴权
        """

    def publish_report(self, report_data: dict, report_id: str) -> str:
        """上传报告到 Vercel，返回公网 URL

        Args:
            report_data: 完整的报告 JSON（含 meta, summary, conclusions）
            report_id: 报告唯一标识，如 report-20260415-流失分析

        Returns:
            公网 URL，如 https://pbi-reports.vercel.app/report/report-20260415-流失分析

        Raises:
            requests.exceptions.RequestException: 上传失败
            ValueError: API 返回错误
        """
```

### 6.3 环境变量

脚本从 `.env` 文件或环境变量读取配置：

```
VERCEL_REPORTS_URL=https://pbi-reports.vercel.app
VERCEL_API_SECRET=your-secret-key
```

`.env` 文件存放在 skill 根目录，加入 `.gitignore`。

### 6.4 依赖

- `requests`（新增到 requirements.txt）

---

## 7. React 前端设计

### 7.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | ^18.3.1 | UI 框架 |
| Vite | ^6.0.7 | 构建工具 |
| Tailwind CSS | ^3.4.17 | 样式系统 |
| Recharts | ^2.15.0 | 图表渲染 |
| React Router | ^7.11.0 | 路由管理 |
| html2pdf.js | ^0.10.2 | PDF 导出 |

### 7.2 路由

| 路径 | 页面 | 数据来源 |
|------|------|----------|
| `/` | Dashboard | `GET /api/reports` |
| `/report/:id` | Report | `GET /api/reports/:id` |

### 7.3 组件复用

直接复用 Data Dive（SPEC-FULL.md）中的以下组件，仅调整数据获取方式（从本地文件改为 API 调用）：

- `Header.jsx` — 顶部导航栏（滚动变化样式）
- `InsightCard.jsx` — 洞察卡片（importance 标签 + 数据支撑 + 图表）
- `ChartContainer.jsx` — Recharts 图表容器（bar/line/pie/scatter）
- `ReportCard.jsx` — 报告列表卡片
- `StatsOverview.jsx` — 统计概览（数字动画）
- `ExportButton.jsx` — PDF 导出
- `EmptyState.jsx` — 空状态

### 7.4 样式

沿用 Data Dive 的 CSS 变量主题（Warm Parchment）：
- 字体：Source Sans 3（正文）+ Cormorant Garamond（标题）+ IBM Plex Mono（数据）
- 色彩：terracotta / forest / gold / sage 莫兰迪色系
- 动画：fadeInUp、fadeIn
- 阴影：editorial shadow

---

## 8. Vercel 配置

### 8.1 环境变量

| 变量名 | 用途 | 获取方式 |
|--------|------|----------|
| `BLOB_READ_WRITE_TOKEN` | Vercel Blob 读写权限 | Vercel 控制台 → Storage → Blob |
| `API_SECRET` | POST/DELETE 接口鉴权 | 用户自定义，部署时设置 |

### 8.2 部署方式

```bash
cd web-report
npm install
vercel deploy --prod
```

### 8.3 域名

使用 Vercel 默认域名 `*.vercel.app`，或绑定自定义域名。

---

## 9. 与现有 SKILL.md 的集成

### 9.1 Phase 5 变更

**原 Phase 5**：调用 `chart_generator.py` 生成 matplotlib PNG 图表。

**新 Phase 5**：
```
Phase 5：生成 Web 分析报告 (可选)

触发条件：
- 用户明确要求生成报告/可视化分析
- 出现"分析走势"、"对比数据"、"复盘"等需要强可视化的场景

执行方式：
1. 构造 report JSON：
   - meta: { title, generated_at, model }
   - summary: { overall, total_conclusions, high_importance_count }
   - conclusions: [{ id, title, description, data_support, importance, chart_type, chart_data }]

2. 调用上传脚本：
   from scripts.web_report_builder import WebReportBuilder
   builder = WebReportBuilder()
   url = builder.publish_report(report_data, report_id)

3. 返回公网 URL
```

### 9.2 Phase 6 变更

交付内容中包含报告链接：
```
📊 Web分析报告: https://pbi-reports.vercel.app/report/report-xxx
```

### 9.3 画图引擎保留

`chart_generator.py`（matplotlib PNG）保留作为轻量备选，用于不需要 Web 报告的简单出图场景。

---

## 10. 一次性设置清单

用户首次使用前需要完成：

1. **创建 Vercel 项目**
   - Fork/Clone web-report 代码到 GitHub
   - 在 Vercel 导入该项目

2. **配置 Blob 存储**
   - Vercel 控制台 → Storage → Create Blob Store
   - 复制 `BLOB_READ_WRITE_TOKEN`

3. **设置环境变量**
   - 在 Vercel 项目设置中添加 `BLOB_READ_WRITE_TOKEN` 和 `API_SECRET`
   - 在本地 `.env` 中添加 `VERCEL_REPORTS_URL` 和 `VERCEL_API_SECRET`

4. **部署**
   - `vercel deploy --prod`

5. **验证**
   - 访问 `https://pbi-reports.vercel.app` 确认仪表板可访问
   - 使用 Python 脚本上传一个测试报告确认端到端流程

---

## 11. 项目结构变更总览

```
powerbi-analysis/
├── scripts/
│   ├── mcp_proxy_stdio.py        # (现有) MCP 代理
│   ├── mcp_proxy_sse.py          # (现有) MCP 代理
│   ├── powerbi_auth.py           # (现有) Power BI 认证
│   ├── chart_generator.py        # (现有) matplotlib 画图（保留）
│   └── web_report_builder.py     # (新增) Web 报告上传脚本
├── web-report/                   # (新增) Vercel 前端项目
│   ├── src/                      # React 组件
│   ├── api/                      # Serverless Functions
│   ├── lib/                      # Blob 封装
│   └── ...                       # 前端配置文件
├── references/                   # (现有) DAX 函数文档
├── output/                       # (现有) PNG 输出目录
├── assets/                       # (现有) 字体文件
├── semantic-model-ids.json       # (现有) 语义模型配置
├── requirements.txt              # (更新) 新增 requests
├── .env                          # (新增) Vercel 配置
├── .gitignore                    # (更新) 添加 .env, web-report/node_modules
├── SKILL.md                      # (更新) Phase 5/6 变更
└── docs/
    └── superpowers/specs/
        └── 2026-04-15-web-report-design.md  # (新增) 本文档
```
