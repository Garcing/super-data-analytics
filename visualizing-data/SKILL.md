---
name: visualizing-data
description: 当用户或工作流需要从结构化数据生成确定性的单图图表、PNG/SVG、静态图表素材、报告插图，或需要数值与标签准确可复现的数据可视化时使用。数值、标签或图表资产必须准确时，优先使用本技能而不是 AI 生图。
metadata:
  skill-series: super-data-analytics
  chinese-name: 可视化数据
---

# Visualizing Data

使用本地 Seaborn/Matplotlib 渲染器，从结构化 JSON 生成可复现的图表图片。所有命令在仓库根目录执行，前缀 `python visualizing-data/scripts/chart.py`。

```bash
python visualizing-data/scripts/chart.py --data <inline | @file | -> --save <file-path> [--dpi N]
```

本文件是自洽的操作手册：选图、写 payload、跑 CLI、看输出，都在这里。**改代码/加图表类型/调色板** 的维护知识见 [`references/developer-guide.md`](references/developer-guide.md)。

## 运行环境与依赖

- Python `>=3.10`。
- 在仓库根目录执行 `python -m pip install -r visualizing-data/requirements.txt`。
- 运行依赖：`matplotlib`、`pandas`、`pillow`、`seaborn`；测试依赖：`pytest`。
- 本技能不读取 `config.json` 或环境变量。中文渲染依赖系统中可用的 CJK 字体，缺失时 CLI 会返回 warning。

完整安装矩阵见仓库根目录 `DEPENDENCIES.MD`。

## 什么时候用本技能

需要**准确**图表素材时用：业务指标图、分析结果图、报告插图、幻灯片图表、可复现 PNG/SVG 导出，或任何必须与源数据一致的图表。

不要用 AI 生图生成精确数值图表——数值会失真。AI 生图只适合报告封面、海报、装饰性视觉等不要求数值精确的场景。

## 资源分离约定

skills 文件夹**不放任何动态资源**（输入 JSON、生成的图片）：

- 临时输入 JSON（需要审阅/复跑/留痕时）写到 `<工作区>/.super-data-analytics/scratch/`，再经 `--data @` 传入。
- 生成的图表一律由 `--save` 指定路径落到 `<工作区>/.super-data-analytics/results/`。
- `<工作区>/.super-data-analytics/` 已在仓库根 `.gitignore`，不会被提交。

## 核心流程

1. **选图表类型** —— 按[图表选型](#图表选型)的决策逻辑定 `type`。
2. **构造 payload JSON** —— 按[顶层字段](#顶层字段)和[全类型 payload 示例](#全类型-payload-示例)写 `type` / `title` / `subtitle` / `data` / `encoding` + 可选 `options`。
3. **运行 CLI** —— 用 `--data` 传 payload、`--save` 传输出路径（扩展名决定格式）。写法见 [CLI 详解](#cli-详解)。
4. **检查输出** —— 看 stdout JSON：`ok: true` 才算成功，再核对 `path` / `format` / `warnings`，并确认文件确实存在。详见[输出与错误](#输出与错误)。

---

## 图表选型

**决策流**（先按数据形态分支，再落到具体类型）：

1. 要**精确查数**（一行行读数字），不要图形？→ `table`
2. **单变量分布**（看一群数值的分布形状）？→ `histogram`
3. **两个数值变量**的关系？→ `scatter`
4. **一个类目 + 一个数值**：
   - 比较类目大小 → `bar`（类目多/标签长 → `horizontal_bar`；还想看累计占比 → `pareto`）
   - 局部-整体构成 → 切片 ≤5 用 `pie`；有分段 series 用 `stacked_bar`
   - 按组比较分布（看离散程度）→ `boxplot`
5. **有序序列**（时间 / 阶段，行顺序有意义）：
   - 趋势 → `line`；强调累积量级 → `area`
   - 有序转化阶段 → `funnel`
   - 从起点到终点的**正负驱动拆解** → `waterfall`
6. **矩阵/网格数值**（如留存 cohort）→ `heatmap`

**选型对照表**：

| 需求 | 使用 | 避免 |
|---|---|---|
| 比较类目 | `bar` | 类目很多时用饼图 |
| 比较长标签 | `horizontal_bar` | 密集旋转 x 轴标签 |
| 展示有序趋势 | `line` | 长时间序列用柱状图 |
| 展示有序量级和填充趋势 | `area` | 负值会改变含义时用面积图 |
| 少量切片的局部-整体关系 | `pie` | 超过 5 个切片且未合并 |
| 两个数值指标关系 | `scatter` | 没有顺序却连线 |
| 矩阵或留存 cohort 结构 | `heatmap` | 3D 曲面或过小标注 |
| 展示分布 | `histogram` | 饼图或只看均值的柱图 |
| 按组比较分布 | `boxplot` | 用柱图隐藏离散程度 |
| 分段叠加构成 | `stacked_bar` | series 太多的堆叠图 |
| 用驱动项桥接起点和终点 | `waterfall` | 用普通柱图表达正负拆解 |
| 有序转化阶段 | `funnel` | 用饼图表达漏斗步骤 |
| 集中度（降序 + 累计占比） | `pareto` | 需要累计占比却用未排序柱图 |
| 保留精确行 | `table` | 需要查数时强行转成图形 |

---

## 输入 payload

### 顶层字段

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

- `type`：支持的图表类型之一（见下表）。
- `title`：非空字符串，显示为图表标题。用清楚的语言说明对象或洞察；不要只把单位写在标题里。
- `subtitle`：非空字符串，写**口径范围**——日期范围、单位、分母、人群、筛选条件、数据切片、基准或置信水平，用副标题消除数值歧义。
- `data`：非空对象数组。每个被 encoding 引用的字段都必须存在于每一行。
- `encoding`：对象，把图表角色映射到数据字段。

可选：

- `options`：图表配置对象。
- `options.width` / `options.height`：输出画布宽/高，正整数像素，默认 `1200` × `720`。

### type → encoding 必填映射

| 类型 | 必填字段映射 | 说明 |
|---|---|---|
| `bar` | `x`, `y` | 纵向柱状图。`y` 必须数值。 |
| `horizontal_bar` | `x`, `y` | 横向柱状图，适合长类目标签。`y` 必须数值。 |
| `line` | `x`, `y` | 有序趋势线。保留输入行顺序。 |
| `area` | `x`, `y` | 填充面积趋势图。`y` 必须数值。 |
| `pie` | `label`, `value` | 少量切片占比图。`value` 必须数值。 |
| `scatter` | `x`, `y` | 散点图，两轴都必须数值。 |
| `heatmap` | `x`, `y`, `value` | 长表矩阵输入。`value` 必须数值。 |
| `histogram` | `x` | 单数值字段分布图。 |
| `boxplot` | `x`, `y` | 按组比较分布。`y` 必须数值。 |
| `stacked_bar` | `x`, `series`, `value` | 分段叠加构成对比。`value` 必须数值。 |
| `waterfall` | `label`, `delta` | 从起始值开始的正负增量桥图。`delta` 必须数值。 |
| `funnel` | `stage`, `value` | 有序阶段漏斗图。保留输入行顺序。 |
| `pareto` | `x`, `y` | 降序柱状图 + 累计占比线。`y` 必须数值。 |
| `table` | 无 | 渲染精确行表格，`encoding` 用 `{}`。 |

> 额外提供的 encoding 角色（如 `color`）也会被校验：引用的字段必须存在于每一行。只添加当前渲染器实际会用到的角色。

### 常用配置项（options）

| 选项 | 适用类型 | 取值 |
|---|---|---|
| `width` / `height` | 全部 | 正整数像素。 |
| `sort` | `bar`, `horizontal_bar` | `asc` / `ascending` / `desc` / `descending`。 |
| `value_labels` | `bar`, `horizontal_bar` | `auto` / 布尔 / `true`/`false`/`on`/`off`/`yes`/`no`/`none`。`auto` 给 ≤20 个柱子加值标签。 |
| `bins` | `histogram` | 正整数，默认 `10`。 |
| `strip` | `boxplot` | 类布尔值。true 时加确定性散点叠加层。 |
| `value_format` | `heatmap` | Matplotlib 标注格式，如 `.0%` / `.2g`。 |
| `start_value` | `waterfall` | 数值型起始值，默认 `0`。 |
| `start_label` | `waterfall` | 第一个总量柱标签，默认 `Start`。 |
| `end_label` | `waterfall` | 最后一个总量柱标签，默认 `End`。 |

### 全类型 payload 示例

**bar** —— 比较类目大小（含负值）：

```json
{
  "type": "bar",
  "title": "各区域销售额",
  "subtitle": "2026年6月，单位：万元",
  "data": [
    { "区域": "华东", "销售额": 120 },
    { "区域": "华北", "销售额": -35 },
    { "区域": "华南", "销售额": 95 }
  ],
  "encoding": { "x": "区域", "y": "销售额" },
  "options": { "sort": "desc", "value_labels": "auto" }
}
```

**horizontal_bar** —— 长类目标签：

```json
{
  "type": "horizontal_bar",
  "title": "Top 产品线收入",
  "subtitle": "2026年6月，单位：万元，按收入降序",
  "data": [
    { "产品线": "企业版订阅续费", "收入": 380 },
    { "产品线": "自助服务扩展", "收入": 270 },
    { "产品线": "伙伴协助开通", "收入": 190 }
  ],
  "encoding": { "x": "产品线", "y": "收入" },
  "options": { "sort": "desc" }
}
```

**line** —— 有序趋势：

```json
{
  "type": "line",
  "title": "DAU 趋势",
  "subtitle": "2026年6月，按周",
  "data": [
    { "周": "W1", "DAU": 120000 },
    { "周": "W2", "DAU": 135000 },
    { "周": "W3", "DAU": 128000 },
    { "周": "W4", "DAU": 142000 }
  ],
  "encoding": { "x": "周", "y": "DAU" }
}
```

**area** —— 有序累积量级：

```json
{
  "type": "area",
  "title": "累计订单量",
  "subtitle": "2026年Q2，按周",
  "data": [
    { "周": "W1", "累计订单": 4200 },
    { "周": "W2", "累计订单": 8800 },
    { "周": "W3", "累计订单": 13500 },
    { "周": "W4", "累计订单": 18900 }
  ],
  "encoding": { "x": "周", "y": "累计订单" }
}
```

**pie** —— 少量切片占比：

```json
{
  "type": "pie",
  "title": "收入构成",
  "subtitle": "2026年6月，按渠道",
  "data": [
    { "渠道": "直营", "收入": 420 },
    { "渠道": "伙伴", "收入": 250 },
    { "渠道": "自助", "收入": 180 }
  ],
  "encoding": { "label": "渠道", "value": "收入" }
}
```

**scatter** —— 两个数值变量的关系：

```json
{
  "type": "scatter",
  "title": "投入与产出",
  "subtitle": "各 campaign，X=花费(万元) Y=GMV(万元)",
  "data": [
    { "花费": 12, "GMV": 80 },
    { "花费": 25, "GMV": 150 },
    { "花费": 18, "GMV": 110 },
    { "花费": 30, "GMV": 210 }
  ],
  "encoding": { "x": "花费", "y": "GMV" }
}
```

**heatmap** —— 矩阵/留存（长表输入，`value_format` 控制标注）：

```json
{
  "type": "heatmap",
  "title": "留存矩阵",
  "subtitle": "行=cohort 周，列=第 N 周",
  "data": [
    { "cohort": "2026-05-01", "周次": "W1", "留存率": 1.00 },
    { "cohort": "2026-05-01", "周次": "W2", "留存率": 0.62 },
    { "cohort": "2026-05-08", "周次": "W1", "留存率": 1.00 },
    { "cohort": "2026-05-08", "周次": "W2", "留存率": 0.59 }
  ],
  "encoding": { "x": "周次", "y": "cohort", "value": "留存率" },
  "options": { "value_format": ".0%" }
}
```

**histogram** —— 单数值字段分布：

```json
{
  "type": "histogram",
  "title": "客单价分布",
  "subtitle": "2026年6月，单位：元",
  "data": [
    { "客单价": 58 }, { "客单价": 120 }, { "客单价": 95 }, { "客单价": 210 },
    { "客单价": 140 }, { "客单价": 88 }, { "客单价": 320 }, { "客单价": 165 }
  ],
  "encoding": { "x": "客单价" },
  "options": { "bins": 8 }
}
```

**boxplot** —— 按组比较分布（`strip` 加散点叠加）：

```json
{
  "type": "boxplot",
  "title": "各线路配送时长",
  "subtitle": "2026年6月，单位：小时",
  "data": [
    { "线路": "北线", "时长": 20 }, { "线路": "北线", "时长": 24 }, { "线路": "北线", "时长": 18 },
    { "线路": "南线", "时长": 30 }, { "线路": "南线", "时长": 28 }, { "线路": "南线", "时长": 36 }
  ],
  "encoding": { "x": "线路", "y": "时长" },
  "options": { "strip": true }
}
```

**stacked_bar** —— 分段叠加构成：

```json
{
  "type": "stacked_bar",
  "title": "各区域产品构成",
  "subtitle": "2026年6月，单位：万元",
  "data": [
    { "区域": "华东", "产品": "A", "销售额": 120 },
    { "区域": "华东", "产品": "B", "销售额": 80 },
    { "区域": "华南", "产品": "A", "销售额": 95 },
    { "区域": "华南", "产品": "B", "销售额": 110 }
  ],
  "encoding": { "x": "区域", "series": "产品", "value": "销售额" }
}
```

**waterfall** —— 起点到终点的正负驱动拆解：

```json
{
  "type": "waterfall",
  "title": "收入变动桥图",
  "subtitle": "期初 + 各组成项增量 = 期末，单位：万元",
  "data": [
    { "组成项": "扩容收入", "增量": 80 },
    { "组成项": "流失影响", "增量": -30 },
    { "组成项": "新增收入", "增量": 45 }
  ],
  "encoding": { "label": "组成项", "delta": "增量" },
  "options": { "start_value": 300, "start_label": "期初", "end_label": "期末" }
}
```

**funnel** —— 有序转化阶段：

```json
{
  "type": "funnel",
  "title": "注册转化漏斗",
  "subtitle": "2026年6月，按阶段",
  "data": [
    { "阶段": "访问", "用户数": 100000 },
    { "阶段": "注册", "用户数": 42000 },
    { "阶段": "激活", "用户数": 18000 },
    { "阶段": "付费", "用户数": 5200 }
  ],
  "encoding": { "stage": "阶段", "value": "用户数" }
}
```

**pareto** —— 降序柱 + 累计占比线：

```json
{
  "type": "pareto",
  "title": "工单原因帕累托",
  "subtitle": "2026年6月，降序柱 + 累计占比线",
  "data": [
    { "原因": "计费", "工单数": 35 },
    { "原因": "登录", "工单数": 18 },
    { "原因": "性能", "工单数": 12 },
    { "原因": "其它", "工单数": 6 }
  ],
  "encoding": { "x": "原因", "y": "工单数" }
}
```

**table** —— 精确行表格（`encoding` 为 `{}`）：

```json
{
  "type": "table",
  "title": "Top 客户",
  "subtitle": "2026年6月，按收入降序前 3",
  "data": [
    { "客户": "甲公司", "负责人": "林某", "收入": 1230 },
    { "客户": "乙公司", "负责人": "陈某", "收入": 980 },
    { "客户": "丙公司", "负责人": "王某", "收入": 760 }
  ],
  "encoding": {}
}
```

---

## CLI 详解

```bash
python visualizing-data/scripts/chart.py --data <inline | @file | -> --save <file-path> [--dpi N]
```

### `--data` 三态输入

按值的形式自动判定来源（对齐 querying-data 的 `--query`）：

| 取值 | 来源 | 说明 |
|---|---|---|
| 不传 或 `-` | stdin | 从管道读取；`-` 是 Unix 惯用的"显式 stdin" |
| `@<path>` | file | 从文件读取 JSON |
| 其他 | inline | 直接 JSON 字符串 |

### `--save`（必填，扩展名决定格式）

`--save` 是**必填**项，没有默认输出目录。输出格式由路径扩展名决定：`.png` 出 PNG，`.svg` 出 SVG，其他扩展名或缺扩展名直接报错。建议落到 `<工作区>/.super-data-analytics/results/`。`--dpi` 可选，默认 `144`，必须正整数。

### 按环境选 `--data` 写法

| 环境条件 | 写法 | 执行方式 |
|---|---|---|
| Agent 进程 API | 管道 stdin | `spawn` 子进程，向 stdin 写 UTF-8 JSON，传 `--data -`；不要为了 spawn 把 JSON 落盘 |
| bash/zsh | 管道 stdin | quoted heredoc `<<'EOF'`（引号抑制 `$` 或反引号展开） |
| PowerShell | 管道 stdin | 显式设 `$OutputEncoding` 为 UTF-8 without BOM；单引号 here-string，管道到 `--data -` |
| JSON 需要审阅/复跑/留痕 | @文件 | 把 JSON 写入 `<工作区>/.super-data-analytics/scratch/`，经 `--data @` 传入 |
| 简短 JSON | inline | JSON 直接写入命令行 |

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

---

## 输出与错误

CLI 成功和失败都向 stdout 写 JSON；落盘成功时额外在 stderr 打 `结果已保存到: <path>`。验证错误不写 stderr。

成功（退出码 `0`）：

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

参数/输入/契约错误（退出码 `2`）：

```json
{ "ok": false, "error": "encoding.y field 'sales' is missing from data row 0" }
```

非预期渲染失败（退出码 `1`），结构同样是 `ok: false`。

| 退出码 | 含义 | 常见修复 |
|---:|---|---|
| `0` | 图表已生成并通过输出检查。 | 查看 `warnings`，使用 `path`。 |
| `1` | 非预期渲染器或导出失败。 | 检查图表类型、数据结构、输出路径权限。 |
| `2` | CLI 参数、JSON 输入或契约校验错误。 | 根据 `error` 指出的字段修复后重跑。 |

常见验证错误：

- `--save 是必填项`：必须传 `--save <file-path>`，没有默认输出目录。
- `--save 扩展名必须是 .png 或 .svg`：格式由扩展名决定，把路径改成 `.png` 或 `.svg`。
- `未提供 --data 且 stdin 是终端` / `等待 stdin 超时`：用 `--data '<JSON>'` 或 `--data @<文件>` 显式传入，或确保管道写完后关闭 stdin。
- `data is required and must be a non-empty list of objects`：至少一行数据。
- `title` / `subtitle` `is required and must be a non-empty string`：提供可见标题与口径说明。
- `encoding.<role> field '<field>' is missing from data row <n>`：每行补字段，或改字段映射。
- `encoding.<role> field '<field>' must contain numeric values`：该字段转成数字，不要用字符串或 `null`。

---

## 中文文本

中文标题、副标题、标签、图例和表格单元格都通过 Matplotlib 字体配置自动支持：渲染器设置 CJK 字体回退链（`Microsoft YaHei` / `SimHei` / `Noto Sans CJK SC` / `Source Han Sans SC` / `PingFang SC` / `WenQuanYi Micro Hei` / `Arial Unicode MS`，再回退拉丁字体），并设 `axes.unicode_minus = False` 避免负号异常。

如果输出 JSON 里出现 CJK 字体 warning，说明图已生成但当前机器可能缺中文字体、字符显示成方框。安装上述任一字体后用同一条命令重跑，确认 warning 消失。**不要为了规避字体 warning 去改源数据或把中文标签替换成拼音。**
