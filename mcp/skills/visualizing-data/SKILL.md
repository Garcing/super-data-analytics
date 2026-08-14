---
name: visualizing-data
description: 数据可视化。当用户要求画图、画图表、做可视化、趋势图、分布图、对比图、漏斗图、瀑布图，或需要一张数值准确、可直接分享的单图时使用；chart 工具按 JSON spec 确定性渲染 14 种图型并返回图片 + 公网 URL。
metadata:
  skill-series: super-data-analytics
  chinese-name: 数据可视化
  mcp-server: sda
  mcp-tools:
    owns:
      - chart
    uses: []
---

# visualizing-data（数据可视化）

把数据变成一张**数值精确、可复现**的图表。通过 `sda` MCP 服务的 `chart` 工具，传一份声明式 JSON spec（type/title/subtitle/data/encoding/options），服务端确定性渲染并返回图片字节 + 可分享 URL。核心纪律：**图上每个数值标签必须与数据一致——本技能只做确定性图表，不做视觉海报**（要 AI 配图/海报风走 building-reports 的 `report_image_generate`）。

## 何时使用 / 何时不用

**用**：
- 用户要"画个图"、"趋势图"、"分布"、"对比"、"漏斗"、"瀑布"、"帕累托"等单图。
- 报告里需要嵌入一张数值准确的图表（配合 building-reports）。
- 需要一条可直接发到飞书/企微的图片 URL。

**不用**：
- 要 AI 生成的视觉化配图/封面 → building-reports 的 `report_image_generate`。
- 只要数字、不要图 → querying-data 直接取数。
- 交互式 dashboard → 不支持，本工具只出静态单图。

## 决策流程

1. **选图型**（数据形态 → 图型映射）：

   | 分析意图 | 图型 |
   |---|---|
   | 时间/顺序趋势 | `line`（多系列用 encoding.series）、`area`（单系列强调量） |
   | 构成占比 | `pie`（类别少）；类别多/需精确对比 → `bar` + `series_mode: stacked` |
   | 类别对比 | `bar`；类别名长/类别多 → `horizontal_bar` |
   | 分布形态 | `histogram`（单变量）、`boxplot`（分组分布对比） |
   | 两变量相关 | `scatter` |
   | 转化漏斗 | `funnel` |
   | 变化贡献拆解 | `waterfall` |
   | 二八/头部集中度 | `pareto` |
   | 两维交叉的数值矩阵 | `heatmap` |
   | 量与率双轴（如销量+转化率） | `combo` |
   | 精确数值展示 | `table` |

2. **选 format**：默认 `png`（飞书/企微兼容，自动上传 Vercel Blob 得公网 URL）；要无损缩放或后续矢量编辑 → `svg`（不上传 Blob）。
3. **构造 spec**：`type` + 必填 `title`/`subtitle`（两者都必须是非空字符串；subtitle 写一句口径/单位说明）+ `data`（行数组）+ `encoding`（字段名映射）+ `options`（可选）。每种图型的必填通道和 options **逐字段见 [references/chart-spec.md](references/chart-spec.md)**。
4. **调 `chart`**，返回图片块 + 文本块「图表已生成（WxH）。URL: …」。给用户交付时**优先转述 URL**；上传失败时文本块提示"未上传 Blob，仅返回图片字节"，此时不是错误，图片块仍然有效。
5. 大表（几十行以上）先聚合/取 TopN 再画；`data_labels` 默认 `auto`（≤20 个标数值），点太密会自动省略，需要强开就显式传 `true`。

## 工具契约

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `chart` | `spec: dict` 必填：`type`（14 种之一：area/bar/boxplot/combo/funnel/heatmap/histogram/horizontal_bar/line/pareto/pie/scatter/table/waterfall）；`title: str` 必填非空；`subtitle: str` 必填非空（写口径/单位说明）；`data: list[dict]` 必填非空，每行一个对象；`encoding: dict` 必填，把角色（x/y/series/label/value/stage/delta/bar/line 等）映射到 data 里的字段名，必填角色随图型（见 reference）；`options: dict` 可选（width/height/data_labels/axis_labels/bins/sort/series_mode/markers/smooth/strip/start_value 等，默认值见 reference）。数值通道字段必须是数字（bool/None/字符串都会校验报错）。`format: "png"（默认）|"svg"`；`dpi: int=144`（72–300） | 多 content 块：ImageContent（图片字节）+ 文本块「图表已生成（WxH）。URL: …」。png 自动上传 Vercel Blob（cache 1h）；**上传失败仅返回图片块并附提示，不算错误**；svg 不上传。spec 不合法时返回可操作的 ContractError（指出哪个字段、哪一行错），按提示补正后重试 |

## 调用示例

各渠道月度 GMV 对比，柱上带数值标签。调 `chart`：

```json
{
  "spec": {
    "type": "bar",
    "title": "各渠道月度 GMV",
    "subtitle": "单位：万元；2026-07；来源：dws_gmv_channel",
    "data": [
      {"channel": "自然流量", "gmv": 320.5},
      {"channel": "广告投放", "gmv": 274.0},
      {"channel": "私域", "gmv": 156.8}
    ],
    "encoding": {"x": "channel", "y": "gmv"},
    "options": {"data_labels": true}
  },
  "format": "png",
  "dpi": 144
}
```

返回：图片块（PNG，默认 1200x720 逻辑尺寸 @144dpi）+ 文本块「图表已生成（1200x720）。URL: https://…」。下一步：把 URL 发给用户或嵌入报告；若某通道字段名写错（如 `gmv` 拼错），会收到指明 `data[i]` 缺字段的错误，按提示修正。

## 陷阱与注意

- **spec 校验失败是可操作的**：错误信息会指出具体字段与行号（如 `encoding.y field 'gmv' must contain numeric values; row 2 has "N/A"`），按提示改 spec 重试，不要瞎换图型。
- **subtitle 必填且非空**：没有副标题就写口径（单位/时间范围/来源），既满足校验又让图自带说明。
- **数值通道必须是数字**：从 SQL 取出的字符串数字要先转成 number；缺失值先清洗。
- 中文渲染无需关心：服务端已内置 CJK 字体。
- png 上传 Blob 失败**不算错误**：图片块仍有效，只是没有 URL；需要 URL 时重试一次。
- 大表先聚合：heatmap/bar 类图型几十个类别以上可读性差，先 TopN + "其他"。
- `pie` 类别多时不精确，改 `bar`；`percent_stacked` 要求数值非负；`smooth` 需每条线 ≥3 个不同 x 值。
- 本技能产物数值精确但风格固定（统一主题/配色），不要试图用它做营销海报。

## 深入参考

- [references/chart-spec.md](references/chart-spec.md) —— chart spec 完整契约：顶层五字段、14 种图型逐一的 encoding 必填/可选通道、options（含默认值）与最小示例 JSON。
