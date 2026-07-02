---
name: visualizing-data
description: 当用户或工作流需要从结构化数据生成确定性的单图图表、PNG/SVG、静态图表素材、报告插图，或需要数值与标签准确可复现的数据可视化时使用。数值、标签或图表资产必须准确时，优先使用本技能而不是 AI 生图。
metadata:
  skill-series: super-data-analytics
  chinese-name: 可视化数据
---

# Visualizing Data

使用本地 Seaborn/Matplotlib 渲染器，从结构化 JSON 数据生成可复现的图表图片。所有命令在仓库根目录执行，前缀 `python visualizing-data/scripts/chart.py`。

```bash
python visualizing-data/scripts/chart.py --data <inline | @file | -> --save <file-path> [--dpi N]
```

## 资源分离约定（重要）

skills 文件夹**不放任何动态资源**（输入 JSON、生成的图片）：

- 临时输入 JSON（需要审阅/复跑/留痕时）写到 `<工作区>/.super-data-analytics/scratch/`，再经 `--data @` 传入。
- 生成的图表一律由 `--save` 指定路径落到 `<工作区>/.super-data-analytics/results/`。
- `<工作区>/.super-data-analytics/` 已在仓库根 `.gitignore` 里，不会被提交。

## 核心流程

### Step 1 写输入 JSON 前

先读 [`references/input_contract.md`](references/input_contract.md)——里面写明顶层字段、图表类型与字段映射、CLI 示例、输出 JSON 和常见错误。

### Step 2 构造图表 JSON 并选定输入方式

`--data` 是统一入口，按值的形式自动判定来源（同一套规则，对齐 querying-data 的 `--query`）：

| 取值 | 来源 | 说明 |
|---|---|---|
| 不传 或 `-` | stdin | 从管道读取；`-` 是 Unix 惯用的"显式 stdin" |
| `@<path>` | file | 从文件读取 JSON |
| 其他 | inline | 直接 JSON 字符串 |

按环境选择：

- **Agent 进程 API / bash heredoc / PowerShell here-string** → 优先管道 stdin（`--data -`），不在磁盘留临时文件。
- **JSON 需要审阅、复跑或留痕** → 写到 `<工作区>/.super-data-analytics/scratch/`，经 `--data @` 传入。
- **简短 JSON** → 直接 inline `--data '<JSON>'`。

### Step 3 必传 `--save`，扩展名决定格式

`--save` 是**必填**项，没有默认输出目录。输出格式（PNG/SVG）由 `--save` 路径的扩展名决定——`.png` 出 PNG，`.svg` 出 SVG，其他扩展名或缺扩展名直接报错。建议落到 `<工作区>/.super-data-analytics/results/`：

```bash
python visualizing-data/scripts/chart.py \
  --data @.super-data-analytics/scratch/bar-20260702-1030-area.json \
  --save .super-data-analytics/results/bar-20260702-1030-area.png
```

可选 `--dpi <正整数>`（默认 144）。

### Step 4 检查 CLI 返回的 JSON

`ok: true` 才表示成功；继续看 `path`、`format`、`dpi`、`width`、`height` 和 `warnings`，并确认输出文件确实存在后再说明图表已生成。落盘成功时脚本还会在 stderr 打印 `结果已保存到: <path>`。

## 什么时候优先使用本技能

当你需要的是准确图表素材时使用本技能：业务指标图、分析结果图、报告插图、幻灯片图表、可复现 PNG/SVG 导出，或任何必须与源数据一致的图表。

不要用 AI 生图生成精确数值图表。AI 生图更适合报告封面、海报、装饰性视觉等不要求数值精确的场景。

## 中文文本

中文标题、副标题、标签、图例和表格单元格都通过 Matplotlib 字体配置支持。渲染器会设置 CJK 字体回退链，优先使用 `Microsoft YaHei`、`SimHei`、`Noto Sans CJK SC`、`Source Han Sans SC`、`PingFang SC`、`WenQuanYi Micro Hei`、`Arial Unicode MS`，然后回退到 `DejaVu Sans`、`Arial` 和 `sans-serif`。

渲染器还会设置 `axes.unicode_minus = False`，避免中文字体栈下负号显示异常。

如果 CLI JSON 里出现 CJK 字体 warning，说明图表已经生成，但当前机器上的中文字符可能显示成方框。请安装上面任一 CJK 字体后，用同一条命令重新生成，并确认 warning 消失。不要为了规避字体 warning 去改源数据，也不要把中文标签替换成拼音。

## 参考文件

- `references/input_contract.md`：输入 JSON 结构、图表字段映射、CLI 示例、输出 JSON 和常见错误。
- `references/seaborn_templates.md`：视觉风格 token、图表类型选择、导出规则和渲染器维护指南。
