---
name: report-to-html
description: 把分析结果发布为可分享的 HTML 报告（Vercel + Blob），返回公网链接
---

# HTML 报告

把分析结论发布成在线 HTML 报告，托管在 Vercel（数据存 Blob），返回公网链接。

**读写模型**：浏览器打开链接是公开 GET（无需密钥）；发布 / 删除是 POST / DELETE，需鉴权。链路：发布方 → Vercel serverless 函数 → Blob，Blob 令牌只在服务端，客户端只持一个密钥。

## CLI（从 building-reports/ 目录）

```bash
# 发布（--report 三种来源，同 querying-data 的 --query；id 由 --id 传入）
node scripts/html/report.js publish --id <reportId> --report "<json>"   # inline
node scripts/html/report.js publish --id <reportId> --report @<file>    # 文件（建议 <工作区>/.super-data-analytics/scratch/）
node scripts/html/report.js publish --id <reportId> --report -          # stdin（管道）
node scripts/html/report.js publish --id <reportId>                     # 不传 --report 等同 stdin

# 其它
node scripts/html/report.js list                              # 列出全部报告
node scripts/html/report.js get <reportId>                     # 打印某份报告 JSON
node scripts/html/report.js delete <reportId>                  # 删除
```

- 报告 id 单独由 `--id` 传入（发布时注入请求体）。
- 原则上优先管道 stdin（不落盘）；需要审阅 / 复跑的报告 JSON 才走 `@文件` 落 <工作区>/.super-data-analytics/scratch。

## 报告 JSON 格式（输入）

```jsonc
{
  "meta": {
    "title": "报告标题",                  // 必填
    "generated_at": "2026-04-15T10:00:00Z", // ISO 8601，作为创建时间
    "model": "语义模型名称"                // 可选，显示为数据来源徽标
  },
  "summary": {
    "overall": "整体结论概述（2-3 句）",    // 截取前 100 字作为列表预览
    "total_conclusions": 5,
    "high_importance_count": 2,
    "kpis": [
      { "label": "指标名称", "value": "核心数值", "trend": "up|down|neutral", "trend_value": "趋势说明" }
    ]
  },
  "conclusions": [
    {
      "id": 1,
      "title": "结论标题",
      "description": "详细描述",
      "data_support": "数据支撑",
      "importance": "high|medium|low",
      "chart_type": "bar|line|pie|scatter",
      "chart_data": { /* 见下 */ }
    }
  ]
}
```

**chart_data 按 chart_type：**

- **bar**：`{ "xKey": "name", "yKey": "value", "data": [{ "name": "A", "value": 100 }] }`
- **line**：`{ "x_labels": ["1月","2月"], "series": { "指标A": [100, 200] } }`
- **pie**：`{ "labels": ["A","B"], "values": [60, 40] }`
- **scatter**：`{ "x": [1,2], "y": [3,4], "x_title": "X", "y_title": "Y" }`

## 配置（config.json）

凭证来自 `~/.super-data-analytics/config.json` 的 `env` 块（脚本不读 `.env`）：

| 变量 | 用途 |
|------|------|
| `VERCEL_REPORTS_URL` | Vercel 项目 URL |
| `VERCEL_API_SECRET` | POST / DELETE 鉴权密钥 |

> 服务端（Vercel serverless 运行时）另读 `BLOB_READ_WRITE_TOKEN`、`API_SECRET`，**只在 Vercel 项目设置里配**，不进 config.json；`API_SECRET` 与 `VERCEL_API_SECRET` 同值。

配置缺失时报错指引补全，由 agent 引导用户写回 config.json 后重试。代理（`HTTPS_PROXY` 等）由 `undici` 自动接管。

## 部署（前端 / API 代码变更后）

```bash
cd building-reports/scripts/html && rm -rf dist && vercel deploy --prod --force
```

必须先 `rm -rf dist` 清构建缓存；部署后在 Vercel 项目设置配 `BLOB_READ_WRITE_TOKEN`、`API_SECRET` 并关联 Public 模式 Blob Store。域名固定，之后发报告只调接口，无需重新部署。
