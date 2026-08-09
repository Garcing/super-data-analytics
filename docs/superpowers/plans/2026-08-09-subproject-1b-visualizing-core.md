# 子项目 1.B 实现计划：visualizing 图表渲染内核

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 `visualizing-data/scripts/chart_renderer` 剥离成干净 Python 内核，渲染到内存字节（BytesIO）而非文件，去掉 CLI/三态输入/`{ok}` 信封，供后续 MCP `chart` 工具直接拿到图片字节。

**Architecture:** 把 `chart_renderer` 包（除 `cli.py`）整体复制到 `mcp/sda_mcp/skills/visualizing/` 子包；唯一改动 `render.py`——把 `fig.savefig(文件路径)` 改成 `fig.savefig(BytesIO)` 并返回字节，质量校验改为基于字节。新增 `__init__.py` 作为内核入口（校验→渲染→返回 `ChartResult` dataclass，失败抛 `ValidationError`）。渲染逻辑（contract/theme/fonts/renderers）逐字搬迁，不改。

**Tech Stack:** Python 3.10+；matplotlib、pandas、seaborn、scipy、pillow（首次给 `mcp/` 加运行时依赖）。

**范围：** 仅子项目 1.B。原 `visualizing-data/` 一律不动（铁律）。

---

## 文件结构

- Copy（逐字）: `mcp/sda_mcp/skills/visualizing/contract.py` ← `visualizing-data/scripts/chart_renderer/contract.py`
- Copy（逐字）: `mcp/sda_mcp/skills/visualizing/theme.py` ← 同源 `theme.py`
- Copy（逐字）: `mcp/sda_mcp/skills/visualizing/fonts.py` ← 同源 `fonts.py`
- Copy（逐字）: `mcp/sda_mcp/skills/visualizing/labels.py` ← 同源 `labels.py`
- Copy（逐字）: `mcp/sda_mcp/skills/visualizing/renderers/` ← 同源 `renderers/`（含 `__init__.py` 与 14 个渲染器）
- Create（改写）: `mcp/sda_mcp/skills/visualizing/render.py` —— 输出改为 BytesIO
- Create（新）: `mcp/sda_mcp/skills/visualizing/__init__.py` —— 内核入口 `render()`
- Modify: `mcp/pyproject.toml` —— 加运行时依赖
- Modify: `mcp/sda_mcp/skills/__init__.py` —— 导出 `render`、`ChartResult`
- Create: `mcp/tests/test_visualizing.py`
- Create: `mcp/tests/fixtures/chart_bar.json`

**不修改**：`visualizing-data/` 下任何文件。

---

## Task 1: 复制包 + 改 render.py + 内核入口 + 依赖

**Files:** 见上。

- [ ] **Step 1: 复制逐字文件（用 cp，保持内部相对 import 不变）**

```bash
cd c:/Users/Administrator/.agents/skills/super-data-analytics
mkdir -p mcp/sda_mcp/skills/visualizing/renderers
cp visualizing-data/scripts/chart_renderer/contract.py mcp/sda_mcp/skills/visualizing/contract.py
cp visualizing-data/scripts/chart_renderer/theme.py    mcp/sda_mcp/skills/visualizing/theme.py
cp visualizing-data/scripts/chart_renderer/fonts.py    mcp/sda_mcp/skills/visualizing/fonts.py
cp visualizing-data/scripts/chart_renderer/labels.py   mcp/sda_mcp/skills/visualizing/labels.py
cp visualizing-data/scripts/chart_renderer/renderers/* mcp/sda_mcp/skills/visualizing/renderers/
```

> 不要复制 `cli.py`、`chart.py`、`__init__.py`（原 `chart_renderer/__init__.py` 只有 3 行无关导出，我们新写）。

- [ ] **Step 2: 写 `mcp/sda_mcp/skills/visualizing/render.py`（输出改 BytesIO）**

```python
from __future__ import annotations

import importlib
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .contract import ChartSpec
from .fonts import configure_fonts
from .theme import apply_theme


RENDERER_MODULES = {
    "area": "area", "bar": "bar", "boxplot": "boxplot", "combo": "combo",
    "funnel": "funnel", "heatmap": "heatmap", "histogram": "histogram",
    "horizontal_bar": "bar", "line": "line", "pareto": "pareto", "pie": "pie",
    "scatter": "scatter", "table": "table", "waterfall": "waterfall",
}


def renderer_module_for(chart_type: str) -> str | None:
    return RENDERER_MODULES.get(chart_type)


def render_chart(spec: ChartSpec, fmt: str, dpi: int) -> tuple[bytes, list[str]]:
    """渲染到内存字节。返回 (图片字节, warnings)。"""
    warnings = configure_fonts()
    apply_theme()
    module_name = renderer_module_for(spec.chart_type)
    if module_name is None:
        raise RuntimeError(f"renderer for {spec.chart_type} is not implemented")

    try:
        module = importlib.import_module(f".renderers.{module_name}", package=__package__)
    except ModuleNotFoundError as exc:
        if exc.name == f"{__package__}.renderers.{module_name}":
            raise RuntimeError(f"renderer for {spec.chart_type} is not implemented") from exc
        raise

    fig = module.render(spec, dpi)
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format=fmt, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(fig)
    image_bytes = buf.getvalue()

    _ensure_nonempty(image_bytes)
    _ensure_png_nonblank(image_bytes, fmt)
    return image_bytes, warnings


# --- 渲染后质量检查（基于字节，不再依赖文件路径）-----------------------------

def _ensure_nonempty(image_bytes: bytes) -> None:
    if not image_bytes:
        raise RuntimeError("chart rendering produced no output")


def _ensure_png_nonblank(image_bytes: bytes, fmt: str) -> None:
    if fmt != "png":
        return
    from PIL import Image, ImageChops
    with Image.open(io.BytesIO(image_bytes)).convert("RGB") as image:
        diff = ImageChops.difference(image, Image.new("RGB", image.size, (255, 255, 255)))
        if diff.getbbox() is None:
            raise RuntimeError("chart output appears blank")
```

- [ ] **Step 3: 写 `mcp/sda_mcp/skills/visualizing/__init__.py`（内核入口）**

```python
"""图表渲染内核（从 visualizing-data/scripts/chart_renderer 剥离）。

渲染到内存字节（BytesIO），不写文件；去 CLI/三态/{ok} 信封。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sda_mcp.errors import ValidationError
from sda_mcp.skills.visualizing.contract import ContractError, validate
from sda_mcp.skills.visualizing.render import render_chart as _render

SUPPORTED_FORMATS = {"png", "svg"}


@dataclass
class ChartResult:
    format: str
    dpi: int
    width: int
    height: int
    data: bytes
    warnings: list[str]


def render(spec: Mapping[str, Any], format: str = "png", dpi: int = 144) -> ChartResult:
    """渲染图表到字节。spec 为图表 JSON（type/title/subtitle/data/encoding/options）。"""
    if format not in SUPPORTED_FORMATS:
        raise ValidationError(f"format must be one of {sorted(SUPPORTED_FORMATS)}, got {format!r}")
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi <= 0:
        raise ValidationError("dpi must be a positive integer")
    try:
        chart_spec = validate(dict(spec))
    except ContractError as exc:
        raise ValidationError(str(exc)) from exc
    image_bytes, warnings = _render(chart_spec, format, dpi)
    return ChartResult(
        format=format,
        dpi=dpi,
        width=int(chart_spec.options.get("width", 1200)),
        height=int(chart_spec.options.get("height", 720)),
        data=image_bytes,
        warnings=warnings,
    )
```

- [ ] **Step 4: 给 `mcp/pyproject.toml` 加运行时依赖**

把 `[project]` 下的 `dependencies = []` 改为：

```toml
dependencies = [
    "matplotlib>=3.8",
    "pandas>=2.0",
    "seaborn>=0.13",
    "scipy>=1.11",
    "pillow>=10.0",
]
```

- [ ] **Step 5: 验证可 import + 能渲染出字节**

```bash
cd mcp && python -c "
from sda_mcp.skills.visualizing import render
r = render({'type':'bar','title':'T','subtitle':'S','data':[{'x':'A','y':1},{'x':'B','y':2}],'encoding':{'x':'x','y':'y'}}, format='png')
print('bytes', len(r.data), 'fmt', r.format, 'size', r.width, r.height)
"
```
Expected: 打印非零字节数、`fmt png`、`size 1200 720`。

- [ ] **Step 6: 提交**

```bash
git add mcp/sda_mcp/skills/visualizing/ mcp/pyproject.toml
git commit -m "feat(mcp): visualizing core (chart render to bytes)"
```

---

## Task 2: 测试

**Files:**
- Create: `mcp/tests/fixtures/chart_bar.json`
- Test: `mcp/tests/test_visualizing.py`

- [ ] **Step 1: 写 fixture `mcp/tests/fixtures/chart_bar.json`**

```json
{"type": "bar", "title": "各渠道 GMV", "subtitle": "2025年8月",
 "data": [{"channel": "APP", "gmv": 120}, {"channel": "Web", "gmv": 80}, {"channel": "小程序", "gmv": 60}],
 "encoding": {"x": "channel", "y": "gmv"}}
```

- [ ] **Step 2: 写 `mcp/tests/test_visualizing.py`**

```python
"""visualizing 内核契约测试 + 与原 CLI 像素级对照。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from sda_mcp.errors import ValidationError
from sda_mcp.skills.visualizing import render, ChartResult

FIX = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parent.parent.parent


def test_render_bar_png():
    spec = json.loads((FIX / "chart_bar.json").read_text(encoding="utf-8"))
    r = render(spec, format="png")
    assert isinstance(r, ChartResult)
    assert r.format == "png"
    assert r.data[:8] == b"\x89PNG\r\n\x1a\n"   # PNG 魔数
    assert len(r.data) > 1000
    assert not hasattr(r, "ok")


def test_render_svg():
    spec = json.loads((FIX / "chart_bar.json").read_text(encoding="utf-8"))
    r = render(spec, format="svg")
    assert r.format == "svg"
    assert r.data.lstrip().startswith(b"<")


def test_bad_format_rejected():
    spec = json.loads((FIX / "chart_bar.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        render(spec, format="gif")


def test_bad_spec_rejected():
    with pytest.raises(ValidationError):
        render({"type": "bar", "title": "x"})  # 缺 subtitle/data/encoding


def test_parity_vs_original_cli(tmp_path):
    """原 CLI 写文件、新内核出字节；解码后像素应完全一致。"""
    spec_path = FIX / "chart_bar.json"
    out = tmp_path / "orig.png"
    proc = subprocess.run(
        [sys.executable, str(REPO / "visualizing-data/scripts/chart.py"),
         "--data", f"@{spec_path}", "--output", str(out)],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    orig = Image.open(out).convert("RGB")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    core = render(spec, format="png")
    new = Image.open(__import__("io").BytesIO(core.data)).convert("RGB")

    assert orig.size == new.size
    assert ImageChops.difference(orig, new).getbbox() is None  # 像素完全一致
```

- [ ] **Step 3: 运行**

```bash
cd mcp && python -m pytest tests/test_visualizing.py -v
```
Expected: 5 passed。若像素对照失败，排查 render.py 改动是否引入差异（应是 0 差异）。

- [ ] **Step 4: 提交**

```bash
git add mcp/tests/fixtures/chart_bar.json mcp/tests/test_visualizing.py
git commit -m "test(mcp): visualizing core contract + pixel parity vs original CLI"
```

---

## Task 3: 导出 + 全量测试

- [ ] **Step 1: 更新 `mcp/sda_mcp/skills/__init__.py` 导出 render**

在现有 import 之后追加：

```python
from sda_mcp.skills.visualizing import render as render_chart, ChartResult
```

并把 `render_chart`、`ChartResult` 加入 `__all__`。

- [ ] **Step 2: 全量测试**

```bash
cd mcp && python -m pytest -q
```
Expected: 全绿（原 18 + visualizing 5 = 23）。

- [ ] **Step 3: 提交**

```bash
git add mcp/sda_mcp/skills/__init__.py
git commit -m "feat(mcp): export render_chart from skills package"
```

---

## 完成标准

- [ ] `render(spec, format, dpi) -> ChartResult` 渲染到字节，不写文件。
- [ ] 去 CLI/三态/`{ok}` 信封；失败抛 `ValidationError`。
- [ ] PNG/SVG 均可渲染；坏格式/坏 spec 抛 `ValidationError`。
- [ ] 像素级对照：新内核与原 CLI 输出完全一致。
- [ ] pyproject 声明 matplotlib/pandas/seaborn/scipy/pillow。
- [ ] 原 `visualizing-data/` 零改动（`git diff -- visualizing-data` 无输出）。
- [ ] 全量 23 个测试通过。
