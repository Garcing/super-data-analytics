# visualizing-data 输入契约

创建 `visualizing-data/scripts/chart.py` 的输入 JSON 时，使用本参考。

## CLI

CLI 形态：

```bash
python visualizing-data/scripts/chart.py --data <inline | @file | -> --save <file-path> [--dpi N]
```

参数：

- `--data`（与 stdin 二选一）：图表 JSON 输入，三态：
  - `--data '<JSON>'` inline JSON 字符串
  - `--data @<file-path>` 从文件读取
  - `--data -` 或不传 → 从 stdin（管道）读取
- `--save`（**必填**）：输出文件路径。**扩展名决定输出格式**——`.png` 出 PNG，`.svg` 出 SVG，其他扩展名或缺扩展名直接报错。建议落到 `<工作区>/.super-data-analytics/results/`。
- `--dpi`（可选，默认 `144`）：正整数。

skills 文件夹不放动态资源：临时输入 JSON 写到 `<工作区>/.super-data-analytics/scratch/`，生成图片落到 `<工作区>/.super-data-analytics/results/`（该目录已在仓库根 `.gitignore`）。

### 按环境选 `--data` 写法

| 环境条件 | 写法 | 执行方式 |
|---|---|---|
| Agent 进程 API | 管道 stdin | `spawn` 子进程，向 stdin 写 UTF-8 JSON，传 `--data -`；不要为了用 spawn 把 JSON 落盘 |
| bash/zsh | 管道 stdin | quoted heredoc `<<'EOF'`（引号抑制 `$` 或反引号展开） |
| PowerShell | 管道 stdin | 显式设 `$OutputEncoding` 为 UTF-8 without BOM；单引号 here-string，管道到 `--data -` |
| JSON 需要审阅、复跑或留痕 | @文件 | agent 把 JSON 写入 `<工作区>/.super-data-analytics/scratch/`，经 `--data @` 传入 |
| 简短 JSON | inline | JSON 直接写入命令行 |

### 参考示例

**inline：**

```bash
python visualizing-data/scripts/chart.py \
  --data '{"type":"bar","title":"区域销售额","subtitle":"2026年6月","data":[{"区域":"华东","销售额":120}],"encoding":{"x":"区域","y":"销售额"}}' \
  --save .super-data-analytics/results/bar-20260702-1030-area.png
```

**@文件：**

```bash
python visualizing-data/scripts/chart.py \
  --data @.super-data-analytics/scratch/bar-20260702-1030-area.json \
  --save .super-data-analytics/results/bar-20260702-1030-area.svg
```

**bash quoted heredoc（stdin，不落盘、不展开）：**

```bash
python visualizing-data/scripts/chart.py --data - \
  --save .super-data-analytics/results/bar-20260702-1030-area.png <<'EOF'
{"type":"bar","title":"区域销售额","subtitle":"2026年6月","data":[{"区域":"华东","销售额":120}],"encoding":{"x":"区域","y":"销售额"}}
EOF
```

**PowerShell 单引号 here-string + 显式 UTF-8：**

```powershell
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom

$json = @'
{"type":"bar","title":"区域销售额","subtitle":"2026年6月","data":[{"区域":"华东","销售额":120}],"encoding":{"x":"区域","y":"销售额"}}
'@

$json | python visualizing-data\scripts\chart.py --data - --save .super-data-analytics\results\bar-20260702-1030-area.png
```

CLI 在成功和失败时都会向 stdout 写入 JSON；落盘成功时额外在 stderr 打印 `结果已保存到: <path>`。验证错误不向 stderr 写内容。

## 顶层字段

```json
{
  "type": "bar",
  "title": "区域销售额",
  "subtitle": "2026年6月，单位：万元",
  "data": [{ "区域": "华东", "销售额": 120 }],
  "encoding": { "x": "区域", "y": "销售额" },
  "options": { "sort": "desc", "value_labels": "auto", "width": 1200, "height": 720 }
}
```

必填：

- `type`：支持的图表类型之一。
- `title`：非空字符串，会显示为图表标题。
- `subtitle`：非空字符串，通常写指标口径、单位、日期范围、人群、筛选条件等。
- `data`：非空对象数组。每个被 encoding 引用的字段都必须存在于每一行。
- `encoding`：对象，用于把图表角色映射到数据字段。

可选：

- `options`：图表配置对象。
- `options.width`：输出画布宽度，正整数，单位像素。默认 `1200`。
- `options.height`：输出画布高度，正整数，单位像素。默认 `720`。

## 支持类型与字段映射

| 类型 | 必填字段映射 | 说明 |
|---|---|---|
| `bar` | `x`, `y` | 纵向柱状图。`y` 必须是数值。 |
| `horizontal_bar` | `x`, `y` | 横向柱状图，适合长类目标签。`y` 必须是数值。 |
| `line` | `x`, `y` | 有序趋势线。除非数据已排序，否则会保留输入行顺序。 |
| `area` | `x`, `y` | 填充面积趋势图。`y` 必须是数值。 |
| `pie` | `label`, `value` | 少量切片的占比图。`value` 必须是数值。 |
| `scatter` | `x`, `y` | 散点图，两个轴都必须是数值。 |
| `heatmap` | `x`, `y`, `value` | 长表形式的矩阵输入。`value` 必须是数值。 |
| `histogram` | `x` | 单个数值字段的分布图。 |
| `boxplot` | `x`, `y` | 按组比较分布。`y` 必须是数值。 |
| `stacked_bar` | `x`, `series`, `value` | 按分段叠加的构成对比。`value` 必须是数值。 |
| `waterfall` | `label`, `delta` | 从起始值开始的正负增量桥图。`delta` 必须是数值。 |
| `funnel` | `stage`, `value` | 有序阶段漏斗图。保留输入行顺序。 |
| `pareto` | `x`, `y` | 降序柱状图加累计占比线。`y` 必须是数值。 |
| `table` | 无 | 渲染精确行表格。`encoding` 使用 `{}`。 |

如果额外提供了 `color` 等字段映射角色，也会被校验：引用的字段必须存在于每一行。只添加当前渲染器实际会用到的角色。

## 常用配置项

| 选项 | 适用类型 | 取值 |
|---|---|---|
| `width` | 全部 | 正整数像素。 |
| `height` | 全部 | 正整数像素。 |
| `sort` | `bar`, `horizontal_bar` | `asc`、`ascending`、`desc` 或 `descending`。 |
| `value_labels` | `bar`, `horizontal_bar` | `auto`、布尔值、`true`、`false`、`on`、`off`、`yes`、`no` 或 `none`。`auto` 会给 20 个以内的柱子加值标签。 |
| `bins` | `histogram` | 正整数，默认 `10`。 |
| `strip` | `boxplot` | 类布尔值。为 true 时添加确定性的散点叠加层。 |
| `value_format` | `heatmap` | Matplotlib 标注格式，如 `.0%` 或 `.2g`。 |
| `start_value` | `waterfall` | 数值型起始值，默认 `0`。 |
| `start_label` | `waterfall` | 第一个总量柱标签，默认 `Start`。 |
| `end_label` | `waterfall` | 最后一个总量柱标签，默认 `End`。 |

## 示例

带负值的中文柱状图：

```json
{
  "type": "bar",
  "title": "各区域销售额",
  "subtitle": "2026年6月，单位：万元，包含负值测试",
  "data": [
    { "区域": "华东", "销售额": 120 },
    { "区域": "华北", "销售额": -35 },
    { "区域": "华南", "销售额": 88 }
  ],
  "encoding": { "x": "区域", "y": "销售额" },
  "options": { "sort": "desc", "value_labels": "auto", "width": 900, "height": 560 }
}
```

热力图：

```json
{
  "type": "heatmap",
  "title": "留存矩阵",
  "subtitle": "行是 cohort，列是周次",
  "data": [
    { "cohort": "2026-05-01", "周次": "W1", "留存率": 0.62 },
    { "cohort": "2026-05-01", "周次": "W2", "留存率": 0.44 },
    { "cohort": "2026-05-08", "周次": "W1", "留存率": 0.59 },
    { "cohort": "2026-05-08", "周次": "W2", "留存率": 0.41 }
  ],
  "encoding": { "x": "周次", "y": "cohort", "value": "留存率" },
  "options": { "value_format": ".0%" }
}
```

瀑布图：

```json
{
  "type": "waterfall",
  "title": "收入变动桥图",
  "subtitle": "起始值加上各组成项的正负增量",
  "data": [
    { "组成项": "扩容收入", "增量": 80 },
    { "组成项": "流失影响", "增量": -30 },
    { "组成项": "新增收入", "增量": 45 }
  ],
  "encoding": { "label": "组成项", "delta": "增量" },
  "options": { "start_value": 300, "start_label": "期初", "end_label": "期末" }
}
```

## 输出 JSON

成功时返回退出码 `0`：

```json
{
  "ok": true,
  "path": "C:/abs/path/.super-data-analytics/results/chart.png",
  "format": "png",
  "dpi": 144,
  "width": 1200,
  "height": 720,
  "warnings": []
}
```

验证或输入错误返回退出码 `2`：

```json
{
  "ok": false,
  "error": "encoding.y field 'sales' is missing from data row 0"
}
```

非预期渲染失败返回退出码 `1`，结构同样是 `ok: false`。

## 错误码与修复

| 退出码 | 含义 | 常见修复 |
|---:|---|---|
| `0` | 图表已生成，并通过输出检查。 | 查看 `warnings` 并使用 `path`。 |
| `1` | 非预期渲染器或导出失败。 | 检查图表类型、数据结构和输出路径权限。 |
| `2` | CLI 参数、JSON 输入或契约校验错误。 | 根据 `error` 指出的字段修复后重跑。 |

常见验证错误：

- `--save 是必填项`：必须传 `--save <file-path>`，没有默认输出目录。
- `--save 扩展名必须是 .png 或 .svg`：输出格式由 `--save` 路径的扩展名决定，把路径改成 `.png` 或 `.svg`。
- `未提供 --data 且 stdin 是终端` / `等待 stdin 超时`：用 `--data '<JSON>'` 或 `--data @<文件>` 显式传入，或确保管道写完后关闭 stdin。
- `data is required and must be a non-empty list of objects`：至少提供一行数据。
- `title is required and must be a non-empty string`：提供可见图表标题。
- `subtitle is required and must be a non-empty string`：提供指标口径或范围说明。
- `encoding.<role> field '<field>' is missing from data row <n>`：给每一行补字段，或修改字段映射。
- `encoding.<role> field '<field>' must contain numeric values`：把该字段转为数字，不要用字符串或 `null`。
