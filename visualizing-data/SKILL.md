---
name: visualizing-data
description: 当用户或工作流需要从结构化数据生成确定性的单图图表、PNG/SVG、静态图表素材、报告插图，或需要数值与标签准确可复现的数据可视化时使用。数值、标签或图表资产必须准确时，优先使用本技能而不是 AI 生图。
metadata: 
  skill-series: super-data-analytics
  chinese-name: 可视化数据
---

# Visualizing Data

使用本地 Seaborn/Matplotlib 渲染器，从结构化 JSON 数据生成可复现的图表图片。

## 默认流程

1. 手写 JSON 前，先阅读 `references/input_contract.md`。
2. 创建图表输入 JSON，包含 `type`、`title`、`subtitle`、`data`、`encoding`，以及可选的 `options`。
3. 将输入 JSON 保存到 `visualizing-data/scripts/input/`。文件名必须使用：

```text
<图表类型>-YYYYMMDD-HHMMSS-<random>.json
```

其中 `<random>` 是 10 位随机英文大小写字母或数字，例如 `bar-20260616-103012-a1B2c3D4e5.json`。

4. 在仓库根目录运行渲染器。CLI 只需要传入文件名，脚本会自动从 `scripts/input/` 读取：

```bash
python visualizing-data/scripts/chart.py bar-20260616-103012-a1B2c3D4e5.json
```

默认输出到 `visualizing-data/scripts/output/`，文件名由图表标题生成。

5. 当图表需要嵌入可编辑报告、幻灯片或文档时，使用 SVG：

```bash
python visualizing-data/scripts/chart.py bar-20260616-103012-a1B2c3D4e5.json --format svg
```

6. 检查 CLI 返回的 JSON。`ok: true` 才表示成功；继续查看 `path`、`format`、`width`、`height` 和 `warnings`，并确认输出文件确实存在后再说明图表已生成。

如需指定输出文件，用 `--out <file>`；如需改用其他输出目录，用 `--out-dir <dir>`。不传时默认使用 `visualizing-data/scripts/output/`。

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
