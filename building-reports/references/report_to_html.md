---
name: report-to-html
description: 把分析结果发布为可分享的 HTML 报告（Vercel + Blob），返回公网链接
---

# HTML 报告

把分析结论发布成在线 HTML 报告，托管在 Vercel（数据存 Blob），返回公网链接。

**读写模型**：数据存在 Vercel Blob（公开读）。前端直读 Blob 公开 URL（无需密钥）；发布/删除由 skill 侧 `report.js` 直连 Blob 写（持 token）。**没有 serverless 函数**，前端和 CLI 都直接对接 Blob——与 streamlit 完全对称。

## CLI（从 building-reports/ 目录）

```bash
# 发布（--report 三种来源，同 querying-data 的 --sql / --payload；id 由 --id 传入）
node scripts/report.js html publish --id <reportId> --report "<json>"   # inline
node scripts/report.js html publish --id <reportId> --report @<file>    # 文件（建议 <工作区>/.super-data-analytics/scratch/）
node scripts/report.js html publish --id <reportId> --report -          # stdin（管道）
node scripts/report.js html publish --id <reportId>                     # 不传 --report 等同 stdin

# 其它
node scripts/report.js html list                              # 列出全部报告
node scripts/report.js html get <reportId>                     # 打印某份报告 JSON
node scripts/report.js html delete <reportId>                  # 删除
```

- 报告 id 单独由 `--id` 传入（发布时注入请求体）。
- 原则上优先管道 stdin（不落盘）；需要审阅 / 复跑的报告 JSON 才走 `@文件` 落 <工作区>/.super-data-analytics/scratch。

## 报告 JSON 格式（输入）

```jsonc
{
  "meta": {
    "title": "报告标题",                  // 必填
    "generated_at": "2026-04-15T10:00:00Z", // ISO 8601 UTC，作为 created_at（重发保留原值）
    "model": "语义模型名称",               // 可选，显示为数据来源徽标
    "tags": ["销售", "区域"]               // 可选，标签数组，写入索引供主页展示
  },
  "summary": {
    "overall": "整体结论概述（2-3 句）",    // 写入索引 summary
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

> 报告 JSON 只需关心内容本身。索引条目由 `report.js` 从 JSON 提取组装，schema 为
> `{ id, title, created_at, updated_at, summary, tags }`（与 streamlit 共用）。
> 不再存 `total_conclusions` / `high_importance_count`——主页/详情页要"结论数"等指标时实时从 `conclusions` 派生。

**chart_data 按 chart_type：**

- **bar**：`{ "xKey": "name", "yKey": "value", "data": [{ "name": "A", "value": 100 }] }`
- **line**：`{ "x_labels": ["1月","2月"], "series": { "指标A": [100, 200] } }`
- **pie**：`{ "labels": ["A","B"], "values": [60, 40] }`
- **scatter**：`{ "x": [1,2], "y": [3,4], "x_title": "X", "y_title": "Y" }`

## 配置（config.json）

凭证来自 `~/.super-data-analytics/config.json` 的 `env` 块（脚本不读 `.env`）：

| 变量 | 用途 |
|------|------|
| `BLOB_READ_WRITE_TOKEN` | 直连 Blob 读写（整个 store 写权限，注意保管） |
| `VERCEL_REPORTS_URL` | 仅用于拼可分享的前端链接（如 `https://project-6hzz6.vercel.app`） |

**不需要在 Vercel 项目设置里配任何环境变量**（旧版的 `BLOB_READ_WRITE_TOKEN` / `API_SECRET` 可删）。Blob 命名：报告 `html-reports/<id>.json`，索引 `html-reports-index.json`；索引用 **ifMatch 乐观锁**写、blob 设 `cacheControlMaxAge=60`（新报告对前端约 1 分钟可见）。配置缺失时报错指引补全，代理（`HTTPS_PROXY` 等）由 `undici` 自动接管。

## 部署（前端代码变更后）

```bash
cd building-reports/scripts/html && rm -rf dist && vercel deploy --prod --force
```

必须先 `rm -rf dist` 清构建缓存。无需配 Vercel 环境变量（前端直读 Blob 公开 URL），只需项目关联一个 Public 模式 Blob Store。域名固定，之后发报告只推 Blob，无需重新部署。
