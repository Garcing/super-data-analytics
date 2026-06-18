---
name: report-to-html
description: 把分析结果发布为可分享的 HTML 报告（Vercel + Blob），返回公网链接
---

# HTML 报告（report → html）

把分析结论发布成在线 HTML 报告，托管在 Vercel，数据存于 Vercel Blob，返回可分享的公网链接。

## 架构一瞥

```
发布方(JS) ──POST + Bearer secret──▶ Vercel API ──put──▶ Blob (reports/{id}.json + 索引)
                                       ▲
浏览者(浏览器) ──GET(无鉴权)──────────┘ ──head──▶ Blob → 渲染页面
```

- **写**：发布方通过 `POST /api/reports`（需鉴权）写入。
- **读**：浏览器打开链接时 `GET`（公开，无需密钥）。
- 鉴权分界：POST/DELETE 需要 `Bearer {API_SECRET}`；GET 完全公开。

---

## 可调用的接口

### A. HTTP API（语言无关，底层接口）

Base URL：`https://project-6hzz6.vercel.app`（即 `VERCEL_REPORTS_URL`）

| 方法 | 路径 | 鉴权 | 说明 | 返回 |
|------|------|------|------|------|
| `GET` | `/api/reports` | 无 | 列出全部报告（读索引） | `{ reports: IndexEntry[] }` |
| `GET` | `/api/reports/:id` | 无 | 读取单份报告 | 完整报告 JSON |
| `POST` | `/api/reports` | `Authorization: Bearer {API_SECRET}` | 发布/更新一份报告（按 id 去重，新的置顶） | `{ url: "/report/:id", updated: boolean }` |
| `DELETE` | `/api/reports/:id` | `Authorization: Bearer {API_SECRET}` | 删除报告（同步更新索引） | `{ success: true }` |

**发布（POST）请求体** = 下面的「报告 JSON 格式」，并在体内带 `id` 字段。

**响应里的 `url` 是相对路径**（`/report/:id`），发布方需自行拼上 base URL 得到完整公网链接：
`https://project-6hzz6.vercel.app/report/:id`。

### B. JS 便捷接口（`report.js`）

封装了上面的 HTTP API，自动处理 `.env` 加载、代理、鉴权。导出四个函数：`publishReport` / `listReports` / `getReport` / `deleteReport`。

**编程式（从 generating-insights-report/ 目录）：**

```js
import { publishReport, listReports, getReport, deleteReport } from './scripts/html/report.js'

await publishReport(reportData, 'report-20260415-分析主题')  // => 公网 URL 字符串
await listReports()                                         // => 索引条目数组
await getReport('report-20260415-分析主题')                  // => 完整报告对象
await deleteReport('report-20260415-分析主题')               // => { success: true }
```

**报告 JSON 放哪（CLI 工作流）**：把生成的报告 JSON 写到 `scripts/html/cache/<reportId>.json`，文件名即报告 id，格式 `report-YYYYMMDD-主题.json`（参考 `cache/_template.json`）。`publish` 只传 id，自动读对应文件。

**CLI（从 generating-insights-report/ 目录）：**

```bash
node scripts/html/report.js publish report-20260415-分析主题   # 读 cache/<id>.json 并发布，打印链接
node scripts/html/report.js list                              # 列出全部报告
node scripts/html/report.js get report-20260415-分析主题       # 打印某份报告 JSON
node scripts/html/report.js delete report-20260415-分析主题    # 删除
```

### C. 其它语言

接口是纯 HTTP。任意语言只需：`POST {VERCEL_REPORTS_URL}/api/reports`，Header 带 `Authorization: Bearer {VERCEL_API_SECRET}` 与 `Content-Type: application/json`，body 为报告 JSON（含 `id`）。

---

## 报告 JSON 格式（输入）

```jsonc
{
  "meta": {
    "title": "报告标题",                 // 必填，POST 校验
    "generated_at": "2026-04-15T10:00:00Z", // ISO 8601，作为创建时间
    "model": "语义模型名称"               // 可选，显示为数据来源徽标
  },
  "summary": {
    "overall": "整体结论概述（2-3 句）",   // 截取前 100 字作为列表预览
    "total_conclusions": 5,
    "high_importance_count": 2,
    "kpis": [
      {
        "label": "指标名称",
        "value": "核心数值",
        "trend": "up | down | neutral",
        "trend_value": "趋势说明"
      }
    ]
  },
  "conclusions": [
    {
      "id": 1,
      "title": "结论标题",
      "description": "详细描述",
      "data_support": "数据支撑",
      "importance": "high | medium | low",
      "chart_type": "bar | line | pie | scatter",
      "chart_data": { /* 见下，随 chart_type 而定 */ }
    }
  ]
}
```

### chart_data 格式（按 chart_type）

- **bar**：`{ "xKey": "name", "yKey": "value", "data": [{ "name": "A", "value": 100 }] }`
- **line**：`{ "x_labels": ["1月", "2月"], "series": { "指标A": [100, 200] } }`
- **pie**：`{ "labels": ["A", "B"], "values": [60, 40] }`
- **scatter**：`{ "x": [1, 2], "y": [3, 4], "x_title": "X", "y_title": "Y" }`

---

## 环境变量

从最近的 `.env` 自动加载（位于项目根 `generating-insights-report/.env`）：

| 变量 | 用途 |
|------|------|
| `VERCEL_REPORTS_URL` | Vercel 项目 URL（发布方用） |
| `VERCEL_API_SECRET` | POST/DELETE 鉴权密钥（发布方用） |
| `BLOB_READ_WRITE_TOKEN` | 服务端 Blob 读写令牌（**仅在 Vercel 项目设置中配置**，仓库 .env 里仅供本地参考） |
| `API_SECRET` | 同 `VERCEL_API_SECRET`，服务端 `api/index.ts` 实际校验的密钥 |

> 注意：`BLOB_READ_WRITE_TOKEN` 与 `API_SECRET` 是 Vercel serverless 函数运行时读的，必须在 **Vercel 项目设置 → Environment Variables** 里配置；仓库里的 `.env` 对线上不生效。

### 依赖与代理网络

- **依赖**：JS 接口（`report.js`）需在 `scripts/html` 下先 `npm install`（含 `undici`）。
- **代理**：发布方会自动检测 `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY` 环境变量（与 Python `requests` 行为一致），经 `undici` 的 `ProxyAgent` 走代理。代理环境下若未装 `undici`，调用会明确报错提示安装。
- Node 自带 `fetch`（Node 18+），除 `undici`（仅代理网络需要）外无其它外部依赖。

---

## 一次性部署（首次或前端/API 代码变更后）

```bash
cd generating-insights-report/scripts/html && rm -rf dist && vercel deploy --prod --force
```

- 必须先 `rm -rf dist` 清除构建缓存。
- 部署后在 Vercel 项目设置中配置 `BLOB_READ_WRITE_TOKEN`、`API_SECRET`，并关联一个 Public 模式的 Blob Store。
- 部署后域名固定，后续每次发报告只调接口，无需重新部署。

---

## 读取 / 删除示例

```bash
# 列出全部报告（公开）
curl https://project-6hzz6.vercel.app/api/reports

# 删除某份报告（需鉴权）
curl -X DELETE \
  -H "Authorization: Bearer $VERCEL_API_SECRET" \
  https://project-6hzz6.vercel.app/api/reports/report-20260415-分析主题
```
