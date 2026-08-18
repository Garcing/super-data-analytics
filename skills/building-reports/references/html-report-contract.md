# HTML 报告 JSON 契约（report_html_publish）

真相源：`sda_mcp/skills/building_reports/html_reports.py`。服务端校验只强制两件事：`id` 非空、`report.meta.title` 非空；其余字段不校验但**前端渲染依赖它们**——按本契约写全。

## 顶层结构

```jsonc
{
  "meta": { ... },        // 元信息，title 必填
  "summary": { ... },     // 总览 + KPI 卡
  "conclusions": [ ... ]  // 结论列表，每条可带一张内嵌小图
}
```

发布时服务端自动注入顶层 `id`（覆盖传入的 `report.id`），存到 Vercel Blob `html-reports/<id>.json`。

## meta

| 字段 | 类型 | 必填 | 说明 / 示例 |
|---|---|---|---|
| `title` | str | 是（唯一校验强制项） | 报告标题，写入索引 `title`。如 `"第 31 周 GMV 周报"` |
| `generated_at` | str | 建议 | ISO 8601 UTC（`"2026-08-03T10:00:00Z"`），首次发布写入索引 `created_at`，重发保留原值 |
| `model` | str | 否 | 语义模型名称，前端显示为数据来源徽标 |
| `tags` | list[str] | 否 | 如 `["销售", "周报"]`，写入索引 `tags`，非 list 时索引里置 `[]` |

## summary

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `overall` | str | 建议 | 整体结论 2-3 句，写入索引 `summary`。如 `"本周 GMV 1280 万，环比 +11.3%，渠道 A 主拉。"` |
| `kpis` | list[dict] | 建议 | KPI 卡数组 |

kpis 条目：

| 字段 | 类型 | 说明 / 示例 |
|---|---|---|
| `label` | str | 指标名，如 `"GMV"` |
| `value` | str | 核心数值，如 `"1280 万"` |
| `trend` | str | `"up" \| "down" \| "neutral"` |
| `trend_value` | str | 趋势说明，如 `"环比 +11.3%"` |

## conclusions

列表，每条：

| 字段 | 类型 | 说明 / 示例 |
|---|---|---|
| `id` | int | 结论序号，如 `1` |
| `title` | str | 结论标题 |
| `description` | str | 详细描述 |
| `data_support` | str | 数据支撑/来源说明，如 `"dws_gmv_channel，2026-W31"` |
| `importance` | str | `"high" \| "medium" \| "low"`（前端按此排序/标色） |
| `chart_type` | str | `"bar" \| "line" \| "pie" \| "scatter"`，可省略（纯文字结论） |
| `chart_data` | dict | 随 chart_type，见下 |

**chart_data 按 chart_type**（前端 Recharts 渲染，与 `chart` 工具的 spec 不是一套）：

- **bar**：`{"xKey": "name", "yKey": "value", "data": [{"name": "渠道A", "value": 520}, ...]}`
- **line**：`{"x_labels": ["7月", "8月"], "series": {"GMV": [860, 910]}}`
- **pie**：`{"labels": ["A", "B"], "values": [60, 40]}`
- **scatter**：`{"x": [1, 2], "y": [3, 4], "x_title": "X", "y_title": "Y"}`

## id 命名建议

id 是 URL 的一部分（`<前端域名>/report/<id>`），建议**日期 + 主题 slug**，小写连字符：

- `2026-08-w31-gmv-weekly`（周报）
- `2026-q3-gmv-review`（季度复盘）

同 id 重发覆盖（首版 `created_at` 保留）；要留历史版本（上周 vs 本周）就每期换 id，日期前缀天然不冲突。

## 索引与乐观锁

- 发布/删除都会改 `html-reports-index.json`：读索引 → 改 → `ifMatch` etag 写回；并发冲突（412）时内核自动退避重试最多 5 次，仍失败才报错——**收到乐观锁错误直接原样重发一次即可**，无需换 id。
- 索引条目：`{id, title, created_at, updated_at, summary, tags}`；不存结论数等派生指标，前端实时从 conclusions 派生。
- Blob CDN 缓存 60s：刚发布/覆盖后 url 打开可能是旧内容，约 1 分钟内新鲜。

## 最小可发布示例

```json
{
  "id": "2026-08-smoke",
  "report": {
    "meta": {"title": "冒烟测试报告"},
    "summary": {"overall": "一句话结论。", "kpis": []},
    "conclusions": [
      {"id": 1, "title": "结论一", "description": "描述", "data_support": "来源",
       "importance": "high"}
    ]
  }
}
```
