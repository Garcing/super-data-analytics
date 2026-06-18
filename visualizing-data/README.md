# visualizing-data 代码导览

本文件给后续迭代这个子技能的 agent 使用，重点说明代码流转逻辑。用户侧使用方法看 `SKILL.md`；输入格式看 `references/input_contract.md`；视觉规范看 `references/seaborn_templates.md`。

## 目录职责

```text
visualizing-data/
  SKILL.md                         技能触发与使用说明
  references/
    input_contract.md              输入 JSON 契约
    seaborn_templates.md           视觉规范与扩展规范
  scripts/
    chart.py                       稳定 CLI 入口
    input/                         运行时输入 JSON，按类型和时间命名
    output/                        默认图表输出目录
    chart_renderer/
      cli.py                       参数解析、主流程、JSON stdout
      contract.py                  输入契约校验，生成 ChartSpec
      io.py                        输入路径解析、JSON 读取、输出路径解析、标题 slug
      fonts.py                     中文字体 fallback 和负号配置
      theme.py                     Seaborn/Matplotlib 共享主题与画布
      render.py                    图表类型到 renderer 模块的分发与导出
      quality.py                   输出文件和 PNG 非空检查
      renderers/                   每种图表的 Matplotlib Figure 生成逻辑
  tests/
    test_chart_cli.py              CLI 合同、渲染 smoke、边界回归测试
    fixtures/                      典型输入样例
```

## 主调用链

```text
chart.py
  -> chart_renderer.cli.main()
    -> parse_args()
    -> io.resolve_input_path()
    -> io.load_json()
    -> contract.validate()
    -> io.resolve_output_path()
    -> render.render_chart()
       -> fonts.configure_fonts()
       -> theme.apply_theme()
       -> import renderers/<type>.py
       -> renderer.render(spec, dpi)
       -> fig.savefig(...)
       -> plt.close(fig)
    -> quality.ensure_output_exists()
    -> quality.ensure_png_nonblank()
    -> stdout JSON
```

## CLI 层要点

`scripts/chart.py` 只做入口转发，尽量不要在这里加逻辑。

`chart_renderer/cli.py` 负责：

- 用 `JsonArgumentParser` 接管 argparse 错误，保证参数错误也输出 JSON。
- 当只传文件名时，从 `scripts/input/` 读取 JSON；显式传完整路径或相对路径时按原路径读取。
- 校验 `--format` 只能是 `png` 或 `svg`。
- 校验 `--dpi` 是正整数。
- 未传 `--out` 或 `--out-dir` 时，默认输出到 `scripts/output/`。
- 成功时输出：

```json
{"ok": true, "path": "...", "format": "png", "dpi": 144, "width": 1200, "height": 720, "warnings": []}
```

- 输入、参数、契约错误返回 exit code `2`。
- 渲染或导出异常返回 exit code `1`。
- 不要在正常错误路径写 stderr；下游 agent 只读 stdout JSON。

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
4. `references/input_contract.md`
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

- 按候选顺序查找 CJK 字体。
- 写入 `rcParams["font.sans-serif"]`。
- 设置 `rcParams["axes.unicode_minus"] = False`。
- 没找到 CJK 字体时返回 warning，但仍继续生成图。

`theme.py` 处理共享样式：

- `PALETTE` 是全局色板。
- `create_figure()` 用 `options.width`、`options.height` 和 `dpi` 算 figsize。
- `add_header()` 写 figure 级标题和副标题。
- `prepare_axes()` 是多数 renderer 的入口。
- `clean_axes()` 统一清理坐标轴样式。

不要在 renderer 里重新设置全局字体；如果要改主题，优先改 `theme.py`。

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
- 需要分组汇总的图表才使用 `pivot_table(..., aggfunc="sum")`，例如 `stacked_bar`、`heatmap`。
- 随机 jitter 默认不可用；`boxplot` 的 strip 叠加已关闭 jitter，保证确定性。
- 负值标签要放在合理方向，避免压在图形内部。

## 新增图表类型流程

1. 先在 `tests/test_chart_cli.py` 添加失败测试。
2. 在 `contract.py` 加类型、必填角色和数值校验。
3. 在 `render.py` 加 `RENDERER_MODULES` 映射。
4. 新建 `renderers/<type>.py`。
5. 复用 `prepare_axes()`、`clean_axes()`、`PALETTE`。
6. 更新 `references/input_contract.md` 和 `references/seaborn_templates.md`。
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
python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py visualizing-data
```

如果涉及导出路径或格式，再手动 smoke：

```bash
python visualizing-data/scripts/chart.py bar-20260616-103012-a1B2c3D4e5.json
python visualizing-data/scripts/chart.py line-20260616-103045-Z9y8X7w6V5.json --format svg --out visualizing-data/tests/output/line.svg
```

手工 smoke 前需要把对应 JSON 放到 `visualizing-data/scripts/input/`。smoke 后删除自己生成的输入 JSON 和输出文件。

## 常见坑

- 不要直接用 `sns.barplot` 或 `sns.lineplot` 默认行为处理精确行数据；它们可能排序或聚合。
- 不要让 argparse 默认报错写 stderr；必须保持 JSON stdout 合同。
- 不要在 renderer 里 `savefig`；统一由 `render.py` 导出和关闭 figure。
- 不要把运行时 JSON 或生成图片提交进仓库；`scripts/input/` 和 `scripts/output/` 只放临时产物。
- 不要为了中文 warning 改源数据或把中文转拼音；应安装字体或把 warning 返回给调用方。
- 不要新增只在文档里存在、代码没有校验的 options。
- 不要提交 smoke 输出、`__pycache__` 或临时图表文件。
