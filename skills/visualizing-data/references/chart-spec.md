# chart spec 完整契约

来源：`sda_mcp/skills/visualizing/contract.py`（校验）+ `renderers/`（各图型实际用到的通道与 options）。字段必填性、类型、默认值均以代码为准。

## 顶层五字段

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `type` | str | 是 | 14 种之一：`area` `bar` `boxplot` `combo` `funnel` `heatmap` `histogram` `horizontal_bar` `line` `pareto` `pie` `scatter` `table` `waterfall`（前后空格会 strip） |
| `title` | str | 是 | 非空字符串（strip 后非空），过长自动换行（约 56 字符/行） |
| `subtitle` | str | 是 | 非空字符串；建议写单位/时间范围/口径来源，约 86 字符/行自动换行 |
| `data` | list[object] | 是 | 非空数组，每行必须是对象（dict） |
| `encoding` | dict | 是 | 角色 → data 字段名映射；**出现的每个角色映射的字段必须存在于每一行 data**；数值角色要求值必须是 number（bool/null/字符串报错） |
| `options` | dict | 否 | 缺省 `{}`；见各图型与公共 options |

校验失败的错误信息可操作：指明字段名、行号、实际值，按提示补正。

## 公共 options（所有图型）

| option | 类型/取值 | 默认 | 说明 |
|---|---|---|---|
| `width` | 正整数 | 1200 | 逻辑像素宽（figsize = width/dpi） |
| `height` | 正整数 | 720 | 逻辑像素高 |
| `data_labels` | `true`/`false`/`"auto"` | `"auto"` | 数值标签。`auto`：点/柱数 ≤20 时显示（且仅对 auto 生效的图型，见各图型明细）。**不支持 `value_labels`**（用了会报错）；传 `true`/`false`/`"auto"` 以外的值也会校验报错 |
| `axis_labels` | dict（角色 → 非空字符串） | 无 | 自定义轴/图例文字，键为 encoding 角色名（`x`/`y`/`value`/`stage`/`bar`/`line`/`cumulative` 等），值替换默认字段名 |

主题（不可配）：统一白底白格主题、8 色调色板（#4C78A8 起）、标题左上、CJK 字体内置、无顶/右边框。

数值标签格式：默认 `%g`（bar/line/scatter 等）；堆叠百分比模式与 pie 显示百分比；`data_labels: false` 时 pie 不显示占比。

## 各图型明细

### line（趋势折线）

- **必填 encoding**：`x`、`y`（y 数值）。
- **可选 encoding**：`series` 或 `color`（多系列分组着色，两者取先出现的）。
- **options**：`markers: bool=true`（点标记）；`smooth: bool=false`（Pchip 平滑，**每条线需 ≥3 个互不重复的 x 值**，否则渲染报错）；公共 options。`data_labels` 的 auto 阈值同样生效（`enabled(..., auto=False)`——即 `auto` 时不显示标签，需显式 `true`）。
- 行为：x 等距位置序排列（按 data 顺序），多系列按 series 首现顺序取色。

```json
{"type": "line", "title": "DAU 走势", "subtitle": "2026-07 每日",
 "data": [{"d": "7-01", "dau": 12000}, {"d": "7-02", "dau": 12500}],
 "encoding": {"x": "d", "y": "dau"}, "options": {"markers": true}}
```

### area（面积）

- **必填 encoding**：`x`、`y`（数值，单系列）。
- **options**：仅公共 options（`data_labels` 需显式 `true`）。零基线自动绘制。

```json
{"type": "area", "title": "月度收入", "subtitle": "单位：万元",
 "data": [{"m": "1月", "rev": 320}, {"m": "2月", "rev": 355}],
 "encoding": {"x": "m", "y": "rev"}}
```

### bar / horizontal_bar（柱状 / 条形）

- **必填 encoding**：`x`、`y`（y 数值）。`type: "horizontal_bar"` 横向条形（适合长类目名），坐标轴标签 x/y 互换。
- **可选 encoding**：`series`（多系列，**仅 `type: "bar"` 生效**——horizontal_bar 分支优先，传了 series 会被静默忽略）。
- **options**：
  - `series_mode: "grouped"（默认）|"stacked"|"percent_stacked"`——非 grouped 必须有 `encoding.series`；`percent_stacked` 要求所有 y 值非负，y 轴固定 0–100%。**仅 `type: "bar"` 校验此选项**（horizontal_bar 传了不生效）。
  - `sort: "asc"|"desc"`（识别 `ascending`/`descending`）——按 y 排序；缺省保持 data 顺序。
  - 公共 options（单系列与 grouped `auto` 时 ≤20 柱自动标数值）。
- 多系列按 x×series 透视 `sum` 聚合，缺失补 0。

```json
{"type": "bar", "title": "渠道×月 GMV", "subtitle": "单位：万元",
 "data": [{"m": "1月", "ch": "自然", "v": 100}, {"m": "1月", "ch": "广告", "v": 80}, {"m": "2月", "ch": "自然", "v": 120}, {"m": "2月", "ch": "广告", "v": 90}],
 "encoding": {"x": "m", "y": "v", "series": "ch"}, "options": {"series_mode": "stacked"}}
```

### histogram（直方图）

- **必填 encoding**：`x`（数值列）。
- **options**：`bins: 正整数=10`；公共 options（`data_labels` 需显式 `true`）。y 轴固定为 count。

```json
{"type": "histogram", "title": "客单价分布", "subtitle": "单位：元",
 "data": [{"price": 89}, {"price": 129}, {"price": 240}],
 "encoding": {"x": "price"}, "options": {"bins": 20}}
```

### boxplot（箱线）

- **必填 encoding**：`x`（分组类别）、`y`（数值，原始逐行样本，不要预先聚合）。
- **options**：`strip: bool=false`（叠加抖动散点，也接受 `"true"/"on"/"1"` 等字符串）；公共 options（`data_labels` 需显式 `true`，标的是各组中位数）。

```json
{"type": "boxplot", "title": "各端加载耗时", "subtitle": "单位：ms",
 "data": [{"os": "iOS", "ms": 820}, {"os": "iOS", "ms": 910}, {"os": "Android", "ms": 1150}],
 "encoding": {"x": "os", "y": "ms"}, "options": {"strip": true}}
```

### pie（饼图）

- **必填 encoding**：`label`（类别）、`value`（数值）。
- **行为**：按 value 降序排列；`data_labels` 非 false（含 auto）时显示 `%1.1f%%` 占比。
- **options**：仅公共 options。类别多（>6）建议改 bar。

```json
{"type": "pie", "title": "流量来源构成", "subtitle": "2026-07",
 "data": [{"src": "自然", "v": 5200}, {"src": "广告", "v": 3100}, {"src": "直接", "v": 900}],
 "encoding": {"label": "src", "value": "v"}}
```

### scatter（散点）

- **必填 encoding**：`x`、`y`（**均须数值**）。
- **options**：仅公共 options（`data_labels` 需显式 `true`）。

```json
{"type": "scatter", "title": "广告费 vs 成交额", "subtitle": "按城市",
 "data": [{"ad": 12.5, "gmv": 380}, {"ad": 20.1, "gmv": 610}],
 "encoding": {"x": "ad", "y": "gmv"}}
```

### funnel（漏斗）

- **必填 encoding**：`stage`（阶段名）、`value`（数值，逐级递减由数据保证）。
- **options**：仅公共 options（auto ≤20 时自动标数值）。

```json
{"type": "funnel", "title": "购买漏斗", "subtitle": "2026-07",
 "data": [{"step": "浏览", "n": 100000}, {"step": "加购", "n": 18000}, {"step": "下单", "n": 5200}, {"step": "支付", "n": 4700}],
 "encoding": {"stage": "step", "value": "n"}}
```

### waterfall（瀑布）

- **必填 encoding**：`label`（因子名）、`delta`（增量，可正可负，数值）。
- **options**：`start_value: number=0.0`；`start_label: str="Start"`；`end_label: str="End"`；公共 options（auto ≤20 时自动标数值：起点值、各增量、终点值）。正增量绿色、负增量红色、首尾合计蓝色，带连接线。

```json
{"type": "waterfall", "title": "GMV 环比变化拆解", "subtitle": "单位：万元；6月→7月",
 "data": [{"f": "流量", "d": 45}, {"f": "转化率", "d": -18}, {"f": "客单价", "d": 12}],
 "encoding": {"label": "f", "delta": "d"}, "options": {"start_value": 1200, "start_label": "6月GMV", "end_label": "7月GMV"}}
```

### pareto（帕累托）

- **必填 encoding**：`x`、`y`（数值）。
- **行为**：按 y 降序排列；右侧副轴画累计占比曲线（0–100%）；x 标签多/长时自动旋转 18°。
- **options**：`axis_labels.cumulative` 可改曲线名（默认 "Cumulative share"）；公共 options（auto ≤20 时柱上标数值）。

```json
{"type": "pareto", "title": "品类销售帕累托", "subtitle": "2026-07",
 "data": [{"cat": "A", "v": 500}, {"cat": "B", "v": 300}, {"cat": "C", "v": 120}, {"cat": "D", "v": 60}],
 "encoding": {"x": "cat", "y": "v"}}
```

### heatmap（热力矩阵）

- **必填 encoding**：`x`、`y`、`value`（数值）。
- **行为**：按 y×value 透视 `sum` 聚合成矩阵；Blues 色带 + 颜色条；`data_labels` 非 false（含 auto）时格内标数值。
- **options**：`value_format: str=".2g"`（ annot 数值格式，Python format spec）；公共 options。

```json
{"type": "heatmap", "title": "城市×品类 GMV", "subtitle": "单位：万元",
 "data": [{"city": "上海", "cat": "A", "v": 120}, {"city": "上海", "cat": "B", "v": 80}, {"city": "北京", "cat": "A", "v": 95}],
 "encoding": {"x": "cat", "y": "city", "value": "v"}}
```

### combo（柱+线双轴）

- **必填 encoding**：`x`、`bar`（柱，数值）、`line`（线，数值，右轴）。
- **options**：公共 options（`data_labels` 需显式 `true`，柱/线同时标）；`axis_labels.bar`/`axis_labels.line` 改轴名。

```json
{"type": "combo", "title": "销量与转化率", "subtitle": "按月",
 "data": [{"m": "1月", "qty": 4200, "cvr": 0.031}, {"m": "2月", "qty": 4600, "cvr": 0.028}],
 "encoding": {"x": "m", "bar": "qty", "line": "cvr"}}
```

### table（数值表）

- **必填 encoding**：**无**（可传空 `{}`）；列 = data 各行键的并集（按首现顺序）。
- **options**：仅公共 options（width/height 有用，data_labels 无效）。
- 适合精确数值展示或嵌入报告的汇总表。

```json
{"type": "table", "title": "渠道汇总", "subtitle": "2026-07",
 "data": [{"渠道": "自然", "GMV": 320.5, "环比": "+8.2%"}, {"渠道": "广告", "GMV": 274.0, "环比": "-1.5%"}],
 "encoding": {}}
```

## 快速核对清单

1. `type` 拼写正确（14 种，含下划线的 `horizontal_bar`/`percent_stacked`）。
2. `title`、`subtitle` 都是非空字符串。
3. `data` 非空，encoding 里每个角色指向的字段在**每一行**都存在。
4. 数值角色（各图型的 y/value/delta/bar/line，scatter 的 x 也算）的值是真数字。
5. `series_mode` 非 grouped 必须有 `encoding.series`；`percent_stacked` 数值非负。
6. 想强制数值标签 → `options.data_labels: true`（不是 `value_labels`）。
