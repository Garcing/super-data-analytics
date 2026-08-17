"""报告工具（building_reports 内核，html+image）→ MCP 工具。streamlit 已砍。

入参平铺：每个字段是独立关键字参数，约束/描述走 Annotated[..., Field(...)]。
"""
import json
from typing import Annotated, Literal
from typing import Any

from mcp.types import CallToolResult, TextContent
from pydantic import Field

from sda_mcp.skills.building_reports import (
    publish_report as _publish, list_reports as _list, get_report as _get,
    delete_report as _delete, generate_image as _gen,
)
from sda_mcp.tools._common import mcp

try:
    from mcp.server.mcpserver import Image
except ImportError:  # 旧版 SDK
    from mcp.server.fastmcp.utilities.types import Image  # type: ignore


@mcp.tool(name="report_html_publish")
def report_html_publish(
    id: Annotated[str, Field(description="报告 ID", min_length=1)],
    report: Annotated[dict[str, Any], Field(description="报告 JSON：meta/summary/conclusions")],
) -> dict[str, Any]:
    """发布 HTML 报告到 Vercel Blob，返回可分享前端 URL。"""
    r = _publish(report, id)
    return {"url": r.url, "report_id": r.report_id, "blob_url": r.blob_url}


@mcp.tool(name="report_html_list")
def report_html_list() -> dict[str, Any]:
    """列出已发布报告（索引）。readOnly。"""
    return {"reports": _list()}


@mcp.tool(name="report_html_get")
def report_html_get(
    id: Annotated[str, Field(min_length=1)],
) -> dict[str, Any]:
    """取某报告完整 JSON。readOnly。"""
    return _get(id)


@mcp.tool(name="report_html_delete")
def report_html_delete(
    id: Annotated[str, Field(min_length=1)],
) -> dict[str, Any]:
    """删除报告（destructive）。"""
    return _delete(id)


@mcp.tool(name="report_image_generate")
def report_image_generate(
    prompt: Annotated[str, Field(min_length=1)],
    model: Annotated[str | None, Field(
        default=None,
        description="可选模型 ID 或 Endpoint ID；不传则使用 config.json 的默认 Seedream 模型",
    )] = None,
    size: Annotated[str | None, Field(
        default=None, description="生成尺寸，例如 2K 或模型支持的 WxH")] = None,
    response_format: Annotated[Literal["url", "b64_json"], Field(
        default="url",
        description="url（默认，返回下载链接）| b64_json（转换为 MCP 图片内容块）",
    )] = "url",
    seed: Annotated[int | None, Field(default=None, ge=-1, le=2_147_483_647)] = None,
    watermark: Annotated[bool, Field(default=False)] = False,
) -> CallToolResult:
    """生成单张图片报告。默认返回方舟下载 URL；b64_json 返回图片内容块。"""
    opts = {
        k: v for k, v in {
            "model": model, "size": size, "response_format": response_format,
            "seed": seed, "watermark": watermark,
        }.items() if v is not None
    }
    r = _gen(prompt, **opts)
    structured = {
        "provider": r.provider,
        "model": r.model,
        "response_format": r.response_format,
        "status": r.status,
        "created": r.created,
        "request_id": r.request_id,
        "usage": r.usage,
        "images": [
            {
                "url": im.url,
                "size": im.size,
                "format": im.format,
                "error": im.error,
            }
            for im in r.images
        ],
    }
    content = [
        Image(data=im.data, format=im.format).to_image_content()
        for im in r.images if im.data is not None
    ]
    content.append(TextContent(type="text", text=json.dumps(structured, ensure_ascii=False)))
    return CallToolResult(content=content, structuredContent=structured)
