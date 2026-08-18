"""可视化工具：chart 渲染为图片，ImageContent + Vercel Blob URL 双保险。

hermes 能转发 ImageContent → 直推图；不能 → 用 URL（企微"上传素材再发"也吃 URL）。

入参平铺：每个字段是独立关键字参数，约束/描述走 Annotated[..., Field(...)]。
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import Field

from sda_mcp.skills.visualizing import render as _render
from sda_mcp.tools._common import mcp, tool_annotations

try:
    from mcp.server.mcpserver import Image
except ImportError:  # 旧版 SDK
    from mcp.server.fastmcp.utilities.types import Image  # type: ignore


def _safe_name(spec: dict[str, Any]) -> str:
    t = str(spec.get("title") or "chart")
    s = re.sub(r"[^\w\-]", "-", t).strip("-")[:32] or "chart"
    return s


@mcp.tool(
    name="chart",
    annotations=tool_annotations(
        "渲染确定性数据图表",
        read_only=False, destructive=False, idempotent=True, open_world=True,
    ),
)
def chart(
    spec: Annotated[dict[str, Any], Field(
        description=(
            "声明式图表：必含 type、title、subtitle、非空 data[]、encoding；可选 options。"
            "type 支持 area/bar/boxplot/combo/funnel/heatmap/histogram/horizontal_bar/"
            "line/pareto/pie/scatter/table/waterfall。数值通道必须传 number。"
        ),
    )],
    format: Annotated[Literal["png", "svg"], Field(
        default="png",
        description="png（默认）返回图片并尝试上传 Vercel Blob；svg 返回矢量图片但不上传。",
    )] = "png",
    dpi: Annotated[int, Field(
        default=144,
        description="渲染 DPI，范围 72-300。",
        ge=72,
        le=300,
    )] = 144,
):
    """按 JSON spec 确定性渲染一张数值准确的静态图表。

    返回 MCP ImageContent 与尺寸/URL 文本块。PNG 会尝试上传 Blob；上传失败
    仍返回图片且不算工具失败。此工具不生成 AI 海报。
    """
    res = _render(spec, format=format, dpi=dpi)
    url = ""
    # 双保险：尝试把 PNG 传到 Vercel Blob 给公网 URL（失败不影响返回图片）
    if format == "png":
        try:
            from sda_mcp.skills.building_reports.blob_store import VercelBlobClient
            info = VercelBlobClient().put(f"charts/{_safe_name(spec)}.png", res.data,
                                          content_type="image/png", cache_control_max_age=3600)
            url = info.url
        except Exception:
            url = ""
    blocks: list = [Image(data=res.data, format=format)]
    text = f"图表已生成（{res.width}x{res.height}）。" + (f" URL: {url}" if url else "（未上传 Blob，仅返回图片字节）")
    blocks.append(text)
    return blocks
