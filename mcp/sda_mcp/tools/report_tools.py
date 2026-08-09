"""报告工具（building_reports 内核，html+image）→ MCP 工具。streamlit 已砍。"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.building_reports import (
    publish_report as _publish, list_reports as _list, get_report as _get,
    delete_report as _delete, generate_image as _gen,
)
from sda_mcp.tools._common import mcp, to_dict


class PublishIn(BaseModel):
    id: str = Field(..., min_length=1, description="报告 ID")
    report: dict[str, Any] = Field(..., description="报告 JSON：meta/summary/conclusions")


class IdIn(BaseModel):
    id: str = Field(..., min_length=1)


class ImageGenIn(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str | None = Field(default=None, description="gpt-image-2 | gpt-image-2-official")
    size: str | None = None
    resolution: str | None = None
    n: int | None = Field(default=None, ge=1, le=4)


@mcp.tool(name="report_html_publish")
def report_html_publish(params: PublishIn) -> dict[str, Any]:
    """发布 HTML 报告到 Vercel Blob，返回可分享前端 URL。"""
    r = _publish(params.report, params.id)
    return {"url": r.url, "report_id": r.report_id, "blob_url": r.blob_url}


@mcp.tool(name="report_html_list")
def report_html_list() -> dict[str, Any]:
    """列出已发布报告（索引）。readOnly。"""
    return {"reports": _list()}


@mcp.tool(name="report_html_get")
def report_html_get(params: IdIn) -> dict[str, Any]:
    """取某报告完整 JSON。readOnly。"""
    return _get(params.id)


@mcp.tool(name="report_html_delete")
def report_html_delete(params: IdIn) -> dict[str, Any]:
    """删除报告（destructive）。"""
    return _delete(params.id)


@mcp.tool(name="report_image_generate")
def report_image_generate(params: ImageGenIn) -> dict[str, Any]:
    """apimart gpt-image-2 异步生图（最长 ~180s）。返回图片 URL+字节。"""
    opts = {k: v for k, v in params.model_dump().items() if k != "prompt" and v is not None}
    r = _gen(params.prompt, **opts)
    return to_dict(r)
