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
