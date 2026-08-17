"""可视化工具：chart 渲染为图片，ImageContent + Vercel Blob URL 双保险。

hermes 能转发 ImageContent → 直推图；不能 → 用 URL（企微"上传素材再发"也吃 URL）。

入参平铺：每个字段是独立关键字参数，约束/描述走 Annotated[..., Field(...)]。
"""
from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import Field

from sda_mcp.skills.visualizing import render as _render
from sda_mcp.tools._common import mcp

try:
    from mcp.server.mcpserver import Image
except ImportError:  # 旧版 SDK
    from mcp.server.fastmcp.utilities.types import Image  # type: ignore


def _safe_name(spec: dict[str, Any]) -> str:
    t = str(spec.get("title") or "chart")
    s = re.sub(r"[^\w\-]", "-", t).strip("-")[:32] or "chart"
    return s


@mcp.tool(name="chart")
def chart(
    spec: Annotated[dict[str, Any], Field(
        description="图表 JSON：type/title/subtitle/data/encoding/options")],
    format: Annotated[str, Field(
        default="png", description="png（默认，飞书/企微兼容）| svg")] = "png",
    dpi: Annotated[int, Field(default=144, ge=72, le=300)] = 144,
):
    """渲染图表。返回图片(image content) + 一个文本块(可分享 URL)。"""
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
