from __future__ import annotations

import importlib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .contract import ChartSpec
from .fonts import configure_fonts
from .theme import apply_theme


RENDERER_MODULES = {
    "area": "area",
    "bar": "bar",
    "boxplot": "boxplot",
    "funnel": "funnel",
    "heatmap": "heatmap",
    "histogram": "histogram",
    "horizontal_bar": "bar",
    "line": "line",
    "pareto": "pareto",
    "pie": "pie",
    "scatter": "scatter",
    "stacked_bar": "stacked_bar",
    "table": "table",
    "waterfall": "waterfall",
}


def renderer_module_for(chart_type: str) -> str | None:
    return RENDERER_MODULES.get(chart_type)


def render_chart(spec: ChartSpec, output_path: Path, fmt: str, dpi: int) -> list[str]:
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
    try:
        fig.savefig(output_path, format=fmt, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(fig)
    return warnings


# --- 导出后质量检查 -----------------------------------------------------------
# savefig 之后立刻校验产物，跟导出本身在同一条时间轴上，所以住在 render.py。

def ensure_output_exists(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"chart output was not created: {path}")


def ensure_png_nonblank(path: Path) -> None:
    if path.suffix.lower() != ".png":
        return

    from PIL import Image, ImageChops

    with Image.open(path).convert("RGB") as image:
        diff = ImageChops.difference(image, Image.new("RGB", image.size, (255, 255, 255)))
        if diff.getbbox() is None:
            raise RuntimeError(f"chart output appears blank: {path}")
