# visualizing-data 代码导览（开发参考）

本文件给**迭代这个子技能的 agent**（改代码、加图表类型、调色板/主题）使用，重点说明代码流转逻辑与维护约定。用户侧"怎么画一张图"看 [`../SKILL.md`](../SKILL.md)——它是自洽的操作手册（选图、写 payload、跑 CLI、看输出），不需要先读本文件。

## 目录职责

```text
visualizing-data/
  SKILL.md                         用户侧操作手册（选图 + payload + CLI + 输出）
  references/
    developer-guide.md             本文件：代码架构 + 维护约定（给改代码的 agent）
  scripts/
    chart.py                       稳定 CLI 入口
    chart_renderer/
      cli.py                       编排层：参数解析、三态 --data 读取、--output 格式推断、主流程
      contract.py                  输入契约校验，生成 ChartSpec
      fonts.py                     中文字体 fallback 和负号配置
      theme.py                     Seaborn/Matplotlib 共享主题与画布
      render.py                    图表分发、savefig 导出、导出后质量检查
      renderers/                   每种图表的 Matplotlib Figure 生成逻辑
  tests/
    test_chart_cli.py              CLI 合同、渲染 smoke、边界回归测试
    fixtures/                      典型输入样例
```

模块分两层：`cli.py` 是**编排层**（参数 + 输入读取 + 格式推断 + 主流程），`contract.py` / `render.py` / `renderers/` 是**引擎层**（校验、渲染、导出）。没有独立的 `io.py` / `quality.py`——输入读取只服务 CLI，住在 `cli.py`；导出后检查紧贴 `savefig`，住在 `render.py`。

skills 文件夹**不放动态资源**：临时输入 JSON 写到 `<工作区>/.super-data-analytics/scratch/`，生成图片落到 `<工作区>/.super-data-analytics/results/`（已在仓库根 `.gitignore`）。不再有 `scripts/input/`、`scripts/output/` 目录。

## 主调用链

```text
chart.py
  -> chart_renderer.cli.main()
    -> parse_args()                解析 --data / --output / --dpi；--output 扩展名决定格式
    -> read_data_source()          三态路由：inline / @file / stdin（均在 cli.py）
    -> contract.validate()
    -> ensure_output_parent()
    -> render.render_chart()
       -> fonts.configure_fonts()
       -> theme.apply_theme()
       -> import renderers/<type>.py
       -> renderer.render(spec, dpi)
       -> fig.savefig(...)
       -> plt.close(fig)
    -> render.ensure_output_exists()   导出后检查也住在 render.py
    -> render.ensure_png_nonblank()
    -> stderr "结果已保存到: <path>"
    -> stdout JSON
```

## CLI 层要点

`scripts/chart.py` 只做入口转发，尽量不要在这里加逻辑。

`chart_renderer/cli.py` 是编排层，负责：

- 用 `JsonArgumentParser` 接管 argparse 错误，保证参数错误也输出 JSON。
- `--data` 三态读取（对齐 querying-data 的 `--sql` / `--payload`）：`-`/不传 → stdin；`@<path>` → file；其他 → inline JSON。stdin 读取带 TTY 守卫 + 线程超时，避免非交互环境下挂死。
- `--output` 必填；扩展名 `.png` / `.svg` 决定输出格式，非法或缺扩展名报错（exit 2）。没有默认输出目录。
- 校验 `--dpi` 是正整数。
- 成功时输出：

```json
{"ok": true, "path": "...", "format": "png", "dpi": 144, "width": 1200, "height": 720, "warnings": []}
```

- 落盘成功时在 stderr 打印 `结果已保存到: <path>`；成功路径以外的 stderr 仍保持空，下游 agent 只读 stdout JSON。
- 输入、参数、契约错误返回 exit code `2`。
- 渲染或导出异常返回 exit code `1`。

## 契约校验层

`contract.py` 是防线最重要的地方。后续新增图表类型时，优先在这里阻止坏输入，不要让 renderer 处理脏数据。

核心对象：

- `SUPPORTED_TYPES`：最终支持的图表类型集合。
- `ChartSpec`：renderer 只接收这个 dataclass。
- `validate()`：从原始 JSON 生成 `ChartSpec`。

当前校验规则：

- `title`、`subtitle` 必须是非空字符串。
- `data` 必须是非空对象数组。
- `encoding` 必须是对象。
- `options.width`、`options.height` 如果出现，必须是正整数。
- 每个必填 encoding 角色都必须引用真实字段。
- 额外提供的 encoding 角色也会校验字段存在。
- 数值角色不允许字符串、布尔值或 `null`。

新增图表类型时，需要同步更新：

1. `SUPPORTED_TYPES`
2. `required_roles`
3. 数值角色映射
4. `SKILL.md` 的 [type→encoding 映射表]、[常用配置项]（若有新 option）、[全类型 payload 示例]
5. 至少一个 CLI 渲染测试

## 渲染分发与导出

`render.py` 负责从 `spec.chart_type` 找 renderer：

```python
RENDERER_MODULES = {
    "bar": "bar",
    "horizontal_bar": "bar",
    ...
}
```

注意点：

- `matplotlib.use("Agg")` 保证无 GUI 环境可用。
- 一定先 `configure_fonts()`，再 `apply_theme()`；`apply_theme()` 会保留已经配置好的字体栈。
- renderer 只返回 `Figure`，不要保存文件。
- `fig.savefig(...)` 后必须 `plt.close(fig)`，避免批量生成时泄漏内存。
- `render_chart()` 返回字体 warning 列表，CLI 会放进成功 JSON。

## 字体与主题

`fonts.py` 处理中文友好：

- 按候选顺序查找 CJK 字体：`Microsoft YaHei`、`SimHei`、`Noto Sans CJK SC`、`Source Han Sans SC`、`PingFang SC`、`WenQuanYi Micro Hei`、`Arial Unicode MS`。
- 追加拉丁字体回退：`DejaVu Sans`、`Arial`、`sans-serif`。
- 写入 `rcParams["font.sans-serif"]`，设 `font.family` 为 `sans-serif`。
- 设置 `rcParams["axes.unicode_minus"] = False`，避免 CJK 字体栈下负号显示异常。
- 没找到 CJK 字体时返回 warning，但仍继续生成图。

`theme.py` 处理共享样式：

- `PALETTE` 是全局色板（见下表）。
- `create_figure()` 用 `options.width`、`options.height` 和 `dpi` 算 figsize。
- `add_header()` 写 figure 级标题和副标题（不要混用 `ax.set_title(...)`）。
- `prepare_axes()` 是多数 renderer 的入口。
- `clean_axes()` 统一清理坐标轴样式。

不要在 renderer 里重新设置全局字体；如果要改主题，优先改 `theme.py`。

### 色板 Token

交付图表用显式颜色，不依赖 Seaborn/Matplotlib 默认配色。颜色由 `theme.py` 的 `PALETTE` 自动应用，agent 写 payload 时**不传颜色**——所以色板是维护知识，不进 `SKILL.md`。

基础色板：

| Token | Hex | 适合用途 |
|---|---|---|
| `blue` | `#4C78A8` | 主柱、主线、总量 |
| `orange` | `#F58518` | 次要对比或接近警示的标记 |
| `green` | `#54A24B` | 正向增量 |
| `purple` | `#B279A2` | 备用类别色 |
| `red` | `#E45756` | 负向增量 |
| `teal` | `#72B7B2` | 备用类别色 |
| `pink` | `#FF9DA6` | 备用类别色 |
| `brown` | `#9D755D` | 备用类别色 |

共享中性色：

| Token | Hex | 适合用途 |
|---|---|---|
| `ink` | `#1F2937` | 标题和主文本 |
| `label` | `#374151` | 数值标签 |
| `muted` | `#6B7280` | 副标题和辅助文本 |
| `axis` | `#D8DEE9` | 坐标轴线 |
| `grid` | `#E5E9F0` | 网格线 |
| `zero` | `#9CA3AF` | 零线和连接线 |

配色规则：

- 简单柱/折线/面积/直方/散点/表格用一个主色。
- 只有表达正负语义时才用绿色和红色。
- 饼图、堆叠柱和类别图用短而明确的色板。
- 标签会碰撞时，先在数据层合并小类目再渲染。
- 不要在图表标记内部用渐变；热力图可用顺序 colormap。

## Renderer 约定

所有 `renderers/*.py` 都实现：

```python
def render(spec: ChartSpec, dpi: int):
    ...
    return fig
```

约定：

- 只从 `spec.encoding` 读取字段名。
- 只从 `spec.options` 读取配置项。
- 输入顺序有意义时必须保留：`line`、`funnel`、`waterfall`、`table`。
- 不要让 Seaborn 默认聚合破坏精确值。`bar` 和 `line` 已经刻意避免默认聚合。
- 需要分组汇总的图表才使用 `pivot_table(..., aggfunc="sum")`，例如带 `series` 的 `bar`、`heatmap`。
- 随机 jitter 默认不可用；`boxplot` 的 strip 叠加已关闭 jitter，保证确定性。
- 负值标签要放在合理方向，避免压在图形内部。

## 新增图表类型流程

1. 先在 `tests/test_chart_cli.py` 添加失败测试。
2. 在 `contract.py` 加类型、必填角色和数值校验。
3. 在 `render.py` 加 `RENDERER_MODULES` 映射。
4. 新建 `renderers/<type>.py`。
5. 复用 `prepare_axes()`、`clean_axes()`、`PALETTE`。
6. 在 `SKILL.md` 更新映射表 / 配置项 / payload 示例。
7. 跑完整测试。

推荐测试命令：

```bash
python -m pytest visualizing-data/tests/test_chart_cli.py -q
```

如果当前 Python 没有依赖，请使用项目约定的 venv 或安装 `pytest pandas matplotlib seaborn pillow`。

## 修改已有 renderer 的检查清单

改代码前先确认：

- 是否会改变精确值？
- 是否会改变输入行顺序？
- 是否会引入随机性？
- 是否会影响中文字体或负号？
- 是否会导致 PNG 空白检查误判？
- 是否需要同步文档中的输入契约？

改完至少跑：

```bash
python -m pytest visualizing-data/tests/test_chart_cli.py -q
```

如果涉及导出路径或格式，再手动 smoke：

```bash
python visualizing-data/scripts/chart.py \
  --data @.super-data-analytics/scratch/bar.json \
  --output .super-data-analytics/results/bar.png
python visualizing-data/scripts/chart.py \
  --data @.super-data-analytics/scratch/line.json \
  --output .super-data-analytics/results/line.svg
```

手工 smoke 前把对应 JSON 写到 `<工作区>/.super-data-analytics/scratch/`。smoke 后删除自己生成的输入 JSON 和输出文件。

## 常见坑

- 不要直接用 `sns.barplot` 或 `sns.lineplot` 默认行为处理精确行数据；它们可能排序或聚合。
- 不要让 argparse 默认报错写 stderr；必须保持 JSON stdout 合同。
- 不要在 renderer 里 `savefig`；统一由 `render.py` 导出和关闭 figure。
- 不要把运行时 JSON 或生成图片提交进仓库；动态资源一律放到 `<工作区>/.super-data-analytics/`（已 gitignore），skills 文件夹保持纯净。
- 不要为了中文 warning 改源数据或把中文转拼音；应安装字体或把 warning 返回给调用方。
- 不要新增只在文档里存在、代码没有校验的 options。
- 不要提交 smoke 输出、`__pycache__` 或临时图表文件。
