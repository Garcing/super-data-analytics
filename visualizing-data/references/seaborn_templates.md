# 确定性图表图片的 Seaborn 模板

修改 `visualizing-data/scripts/chart_renderer/`、新增图表类型或调整视觉样式时，使用本参考。保持脚本确定性：相同 JSON 输入应生成相同的图表结构、标签和输出元数据。

## 构建顺序

1. 先通过 `chart_renderer.contract` 完成校验。
2. 用 `configure_fonts()` 配置字体。
3. 用 `apply_theme()` 应用共享主题。
4. 用 `prepare_axes(spec, dpi)` 创建 figure。
5. 适合 Seaborn 的标记用 Seaborn；自定义布局更清楚时用 Matplotlib。
6. 除 pie、table 等有意隐藏坐标轴的图表外，调用 `clean_axes(ax)`。
7. 用 `fig.savefig(..., format=fmt, dpi=dpi, bbox_inches="tight")` 导出。
8. CLI stdout 只输出紧凑 JSON。

## 样式 Token

使用显式颜色。交付图表不要依赖 Seaborn 或 Matplotlib 默认配色。

当前基础色板：

| Token | Hex | 适合用途 |
|---|---|---|
| `blue` | `#4C78A8` | 主柱、主线、总量。 |
| `orange` | `#F58518` | 次要对比或接近警示的标记。 |
| `green` | `#54A24B` | 正向增量。 |
| `purple` | `#B279A2` | 备用类别色。 |
| `red` | `#E45756` | 负向增量。 |
| `teal` | `#72B7B2` | 备用类别色。 |
| `pink` | `#FF9DA6` | 备用类别色。 |
| `brown` | `#9D755D` | 备用类别色。 |

共享中性色：

| Token | Hex | 适合用途 |
|---|---|---|
| `ink` | `#1F2937` | 标题和主文本。 |
| `label` | `#374151` | 数值标签。 |
| `muted` | `#6B7280` | 副标题和辅助文本。 |
| `axis` | `#D8DEE9` | 坐标轴线。 |
| `grid` | `#E5E9F0` | 网格线。 |
| `zero` | `#9CA3AF` | 零线和连接线。 |

配色规则：

- 简单柱状图、折线图、面积图、直方图、散点图和表格使用一个主色。
- 只有表达正负语义时才使用绿色和红色。
- 饼图、堆叠柱和类别图使用短而明确的色板。
- 如果标签会碰撞，先在数据层合并小类目再渲染。
- 不要在图表标记内部使用渐变。热力图可以使用顺序 colormap。

## 标题与副标题规则

每张图都必须有非空 `title` 和 `subtitle`，契约校验会强制这一点。

标题：

- 用清楚的语言说明图表对象或洞察。
- 保持足够短，能适应导出宽度。
- 不要只把单位写在标题里。

副标题：

- 写口径范围：日期范围、单位、分母、人群、筛选条件、数据切片、基准或置信水平。
- 用副标题消除数值歧义。
- PNG 导出后仍应可读。

使用 `theme.py` 里的 `add_header(fig, spec)`。不要混用 `ax.set_title(...)` 和单独的 figure 级副标题。

## 中文字体规则

中文是一等需求：标题、副标题、类目标签、图例、数值标签和表格单元格都应在不改源数据的情况下正常显示。

`fonts.py` 负责字体设置：

- 有可用字体时，按顺序优先使用 `Microsoft YaHei`、`SimHei`、`Noto Sans CJK SC`、`Source Han Sans SC`、`PingFang SC`、`WenQuanYi Micro Hei`、`Arial Unicode MS`。
- 追加拉丁字体回退：`DejaVu Sans`、`Arial`、`sans-serif`。
- 将 `font.family` 设置为 `sans-serif`。
- 设置 `axes.unicode_minus = False`，避免 CJK 字体栈下负号显示异常。
- 如果没有检测到已知 CJK 字体，返回 warning。

如果测试或手工渲染出现 CJK 字体 warning，不要把中文转拼音，也不要删除中文标签。应安装已知 CJK 字体，或在 CLI 结果里说明该 warning。

## 导出规则

支持格式（由 `--save` 路径扩展名决定，无 `--format` 参数）：

- `.png` 适合报告图片、聊天附件和栅格预览。
- `.svg` 适合可编辑文档、幻灯片，以及需要清晰缩放的工作流。

输出行为：

- `--save <file-path>` 是**必填**项；扩展名必须是 `.png` 或 `.svg`，否则报错退出。
- 输入三态：`--data '<JSON>'` inline、`--data @<file-path>` 文件、`--data -` 或不传走 stdin。
- skills 文件夹不放动态资源：临时 JSON 写到 `<工作区>/.super-data-analytics/scratch/`，生成图片落到 `<工作区>/.super-data-analytics/results/`。
- 宽高来自 `options.width` 和 `options.height`，默认 `1200` × `720`。
- DPI 默认 `144`，且必须是正整数。

质量检查：

- 确认输出文件存在且非空。
- PNG 会检查是否不是空白图。
- SVG 在测试中检查文件存在和内容。

## 图表类型选择

选择能回答问题的最简单图表。

| 需求 | 使用 | 避免 |
|---|---|---|
| 比较类目 | `bar` | 类目很多时使用饼图。 |
| 比较长标签 | `horizontal_bar` | 密集旋转 x 轴标签。 |
| 展示有序趋势 | `line` | 长时间序列用柱状图。 |
| 展示有序量级和填充趋势 | `area` | 负值会改变含义时使用面积图。 |
| 少量切片的局部-整体关系 | `pie` | 超过 5 个切片且未合并。 |
| 展示两个数值指标关系 | `scatter` | 没有顺序却连线。 |
| 展示矩阵或留存 cohort 结构 | `heatmap` | 3D 曲面或过小标注。 |
| 展示分布 | `histogram` | 饼图或只看均值的柱图。 |
| 按组比较分布 | `boxplot` | 用柱图隐藏离散程度。 |
| 展示分段叠加构成 | `stacked_bar` | series 太多的堆叠图。 |
| 用驱动项桥接起点和终点 | `waterfall` | 用普通柱图表达正负拆解。 |
| 展示有序转化阶段 | `funnel` | 用饼图表达漏斗步骤。 |
| 展示集中度 | `pareto` | 需要累计占比却用未排序柱图。 |
| 保留精确行 | `table` | 需要查数时强行转成图形标记。 |

## 渲染器指南

每个渲染器应该：

- 接收已校验的 `ChartSpec`。
- 从 `spec.encoding` 读取角色字段名。
- 只在校验通过后转换数值列。
- 在顺序有意义时保留输入顺序：`line`、`funnel`、`waterfall` 和 `table`。
- 只有图表契约或 option 明确要求时才排序。
- 使用保守默认值处理渲染器专属配置项。
- 避免随机 jitter；如果必须使用，固定随机种子。
- 负值或小标记容易碰撞时，把标签放在标记外侧。
- 返回 Matplotlib `Figure`；不要在渲染器内保存文件。

## 新增图表类型

1. 在 `contract.py` 的 `SUPPORTED_TYPES` 中加入类型。
2. 在 `validate()` 中加入必填角色和数值角色校验。
3. 在 `render.py` 中加入模块映射。
4. 在 `renderers/` 下实现 `render(spec, dpi)`。
5. 至少添加一个 CLI 测试，渲染非空 PNG 或有效 SVG。
6. 如果新图表引入新角色，添加缺字段或非数值 encoding 的校验测试。
7. 更新 `references/input_contract.md` 和本文件。

## 修改 Renderer

改视觉输出前，先检查现有 fixture，或创建一个小输入 JSON。修改后运行：

```bash
.\venv\Scripts\python.exe -m pytest visualizing-data/tests/test_chart_cli.py -q
```

如果可能影响导出行为，同时手工渲染 PNG 和 SVG：

```bash
.\venv\Scripts\python.exe visualizing-data/scripts/chart.py \
  --data @.super-data-analytics/scratch/bar.json \
  --save .super-data-analytics/results/bar.png
.\venv\Scripts\python.exe visualizing-data/scripts/chart.py \
  --data @.super-data-analytics/scratch/line.json \
  --save .super-data-analytics/results/line.svg
```

手工渲染前，把对应 JSON 写到 `<工作区>/.super-data-analytics/scratch/`。检查 CLI JSON 结果，不要只看图片文件。
