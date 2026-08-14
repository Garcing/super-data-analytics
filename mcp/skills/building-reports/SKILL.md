---
name: building-reports
description: 构建数据报告。当用户要求出报告、生成周报/月报、复盘报告、数据播报、分析简报，或要一张数据海报/报告封面图/单图播报时使用；report_html_* 把结构化报告发布为在线可分享页面，report_image_generate 用火山方舟 Seedream 生成单张图片报告。
metadata:
  skill-series: super-data-analytics
  chinese-name: 构建报告
  mcp-server: sda
  mcp-tools:
    owns:
      - report_html_publish
      - report_html_list
      - report_html_get
      - report_html_delete
      - report_image_generate
    uses:
      - retrieve_search
      - retrieve_doc_read
      - chart
---

# building-reports（构建报告）

把分析结果交付成两种形态：**在线 HTML 报告**（`report_html_publish`，报告 JSON 存 Vercel Blob，返回可分享前端 URL）和**单张图片报告**（`report_image_generate`，火山方舟 Seedream，一张信息图/海报固化标题 + KPI + 趋势 + 结论）。核心纪律：**报告里的每个数字必须来自真实取数/分析结果，不在报告里编数**；发布后必须打开 URL 验证渲染再交付。

## 何时使用 / 何时不用

**用**：
- 用户要"出一份报告"、"周报"、"复盘"、"数据播报"、"分析简报"。
- 结构化多结论、带数字/表格/内嵌图表的在线报告 → HTML。
- 一张图讲清结论、贴进 PPT/飞书/微信、视觉海报/周报头图/封面图 → image。

**不用**：
- 只要一张**数值精确**的数据图表 → visualizing-data 的 `chart`（image 生成不保证坐标精确）。
- 只要数字不要交付物 → querying-data 直接取数。
- 要落飞书文档/多维表 → 走 retrieving-context 技能（其 `retrieve_doc_update` 可改 docx 正文）。

## 决策流程

1. **格式路由**：

   | 需求 | 选择 |
   |---|---|
   | 多结论、可在线分享、可回看历史 | HTML（`report_html_publish`） |
   | 视觉海报 / 单图数据播报 / 周报头图 / 封面图 | image（`report_image_generate`） |
   | 报告里还要嵌数值精确图表 | chart 出图后引用其 URL，报告本体仍走 HTML |

2. **HTML 发布三步**：构造报告 JSON（meta/summary/conclusions，结构见 [references/html-report-contract.md](references/html-report-contract.md)）→ `report_html_publish` → **打开返回的 url 验证渲染**（标题/KPI/结论图表是否齐全）→ 交付链接并附一句口径说明（时间范围/数据来源/单位）。
3. **报告模板**：用户提到"按模板出报告"时，先 `retrieve_search` 搜模板（注意：graph-config 当前实体标签里**尚无「报告模板」**——模板功能依赖语义层多维表配置，未配置时搜不到，按本 SKILL 内置的 meta/summary/conclusions 结构自拟即可）；搜到模板后用 `retrieve_doc_read` 读模板 docx 正文结构，照其章节骨架填数，再走第 2 步发布。
4. **图片报告**：按 [references/image-report-prompting.md](references/image-report-prompting.md) 写提示词（类型/比例/标题/关键数字/趋势结论全写进去）→ `report_image_generate`（耗时约 60-90s 正常，勿超时重发）→ 交付 URL 并提醒 24h 过期、需要留存立即下载。
5. **修改已发布报告**：`report_html_get` 取完整 JSON → 改 → 同 id 重新 `report_html_publish`（覆盖语义，`created_at` 保留原值）。

## 工具契约

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `report_html_publish` | `id: str` 必填非空（报告唯一标识，建议日期+主题 slug 如 `2026-08-weekly-gmv`）；`report: dict` 必填，校验仅强制 `report.meta.title` 非空，但完整结构 meta/summary/conclusions 见 reference——按完整结构写，前端才能渲染 KPI 卡和结论图表。同 id 重发是**覆盖** | `{url, report_id, blob_url}`：url 是可分享前端链接（依赖 config 的 `VERCEL_REPORTS_URL`），blob_url 是报告 JSON 原始地址。**必须打开 url 验证渲染再交付**。索引乐观锁并发冲突时报错，按提示重试即可 |
| `report_html_list` | 无参数 | `{reports: [...]}` 索引条目 `{id, title, created_at, updated_at, summary, tags}`，最新在前 |
| `report_html_get` | `id: str` 必填非空 | 报告完整 JSON（读改重发用）；找不到该 id 报错 |
| `report_html_delete` | `id: str` 必填非空 | `{success, report_id}`。**destructive**：删除报告 JSON 并移出索引，不可恢复——删除前确认用户意图 |
| `report_image_generate` | `prompt: str` 必填非空；`model?: str`（Model ID 或 Endpoint ID，缺省 config.json `VOLCENGINE_ARK_IMAGE_MODEL`）；`size?: str`（如 `"2K"` 或模型支持的 WxH，**比例要写进 prompt**如「3:4 竖版」，冒烟基线 2K+3:4 → 1776x2368）；`response_format: "url"（默认）\|"b64_json"`；`seed?: int`（-1..2^31-1）；`watermark: bool=false` | structuredContent `{provider, model, response_format, status, created, request_id, usage, images[{url, size, format, error}]}`。同步单图、**无轮询**；URL 含 `X-Tos-Expires=86400`（**24h 过期**，要留存立即下载）；失败/超时**不自动重试**（防重复计费）；耗时约 60-90s 正常。b64_json 时额外返回 MCP ImageContent 图片块（适合直接给用户看图）；url 适合转述/下载留存 |

## 调用示例

发布一份周度 GMV 报告。调 `report_html_publish`：

```json
{
  "id": "2026-08-w31-gmv-weekly",
  "report": {
    "meta": {
      "title": "第 31 周 GMV 周报",
      "generated_at": "2026-08-03T10:00:00Z",
      "tags": ["销售", "周报"]
    },
    "summary": {
      "overall": "本周 GMV 1280 万，环比 +11.3%，渠道 A 主拉。",
      "kpis": [
        {"label": "GMV", "value": "1280 万", "trend": "up", "trend_value": "环比 +11.3%"},
        {"label": "拉动渠道", "value": "渠道 A", "trend": "up", "trend_value": "+18%"}
      ]
    },
    "conclusions": [
      {
        "id": 1,
        "title": "渠道 A 拉动增长",
        "description": "渠道 A 本周 520 万，环比 +18%，贡献主要增量。",
        "data_support": "分渠道 GMV 对比，dws_gmv_channel",
        "importance": "high",
        "chart_type": "bar",
        "chart_data": {"xKey": "name", "yKey": "value", "data": [
          {"name": "渠道A", "value": 520}, {"name": "渠道B", "value": 430}, {"name": "渠道C", "value": 330}
        ]}
      }
    ]
  }
}
```

返回 `{url: "https://…/report/2026-08-w31-gmv-weekly", report_id, blob_url}`。下一步：打开 url 确认渲染（标题/KPI/结论图表齐全）再交付。

生成一张 3:4 竖版周报数据播报图。调 `report_image_generate`：

```json
{
  "prompt": "生成一张 3:4 竖版数据播报信息图。【主题】给运营周会看的 GMV 周报简报。【关键数字】GMV 本周 1280 万、上周 1150 万、周环比 +11.3%；渠道A 520万(+18%)、渠道B 430万(+5%)、渠道C 330万(+12%)。【趋势结论】近 8 周趋势：820,910,980,1020,1100,1080,1150,1280，连续 3 周上行；高亮：渠道 A 主拉增长。商务扁平风，主色蓝，中文，数字粗体，所有图表带数据标签，数值须与提供数据完全一致。",
  "size": "2K",
  "response_format": "url"
}
```

返回 structuredContent，`images[0].url` 为 24h 有效下载链接。下一步：提醒用户链接 24h 过期，要留存立即下载（约 60-90s 出图正常）。

## 陷阱与注意

- **同 id 覆盖语义**：`report_html_publish` 同 id 重发会整体覆盖旧报告（`created_at` 保留首版）；想留历史版本就换 id。索引乐观锁并发冲突报错时直接重试。
- **校验只强制 `meta.title`**：缺 summary/conclusions 不会报错但前端渲染空——按 reference 的完整结构写全。
- **image URL 24h 过期**（`X-Tos-Expires=86400`），且不上传 Vercel Blob；需要长期保留立即下载。
- **生成慢勿超时重发**：约 60-90s 正常；失败不自动重试是防重复计费，确认失败原因后再手动重试。
- **b64 vs url**：要直接给用户看图（IM 场景）用 `b64_json`（返回图片块）；只转述链接或要下载留存用 `url`。
- **不要用 image 替代 chart**：Seedream 不保证坐标轴/比例精确，精确数据图走 visualizing-data 的 `chart`；image 里的图表必须带数据标签兜底。
- **删除是破坏性操作**：`report_html_delete` 不可恢复，动手前向用户确认。
- 新报告对前端约 1 分钟可见（Blob CDN 缓存 60s），刚发布 url 打开若是旧内容等一下再验。

## 深入参考

- [references/html-report-contract.md](references/html-report-contract.md) —— 报告 JSON 完整契约：meta/summary/conclusions 逐字段、chart_data 四种图型、id 命名建议、乐观锁冲突处理。
- [references/image-report-prompting.md](references/image-report-prompting.md) —— Seedream 提示词写法：类型/比例声明、中文 KPI 数值写法、信息结构模板、负面边界、URL 时效与 seed 复现。
