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
