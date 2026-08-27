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
from sda_mcp.tools._common import mcp, map_tool_errors, tool_annotations
from sda_mcp.tools._schemas import (
    ReportDeleteOutput,
    ReportListOutput,
    ReportPublishOutput,
)

try:
    from mcp.server.mcpserver import Image
except ImportError:  # 旧版 SDK
    from mcp.server.fastmcp.utilities.types import Image  # type: ignore


@mcp.tool(
    name="report_html_publish",
    annotations=tool_annotations(
        "发布 SDA HTML 报告",
        read_only=False, destructive=True, idempotent=False, open_world=True,
    ),
)
@map_tool_errors
def report_html_publish(
    id: Annotated[str, Field(
        description="报告唯一 ID；建议使用日期+主题 slug，例如 2026-08-weekly-gmv。同 ID 会覆盖已有报告。",
        min_length=1,
    )],
    report: Annotated[dict[str, Any], Field(
        description="完整报告 JSON；至少需要 meta.title，标准结构为 meta、summary、conclusions。",
    )],
) -> ReportPublishOutput:
    """把结构化报告 JSON 发布到 Vercel Blob 并更新报告索引。

    同 ID 为整体覆盖。返回可分享 ``url``、``report_id`` 与原始 JSON
    ``blob_url``；发布后仍需打开前端 URL 验证渲染。
    """
    r = _publish(report, id)
    return {"url": r.url, "report_id": r.report_id, "blob_url": r.blob_url}


@mcp.tool(
    name="report_html_list",
    annotations=tool_annotations(
        "列出 SDA HTML 报告",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def report_html_list() -> ReportListOutput:
    """读取已发布报告索引。

    返回 ``reports[]``，条目通常含 id、title、created_at、updated_at、
    summary 和 tags，按索引中的最新顺序排列。
    """
    return {"reports": _list()}


@mcp.tool(
    name="report_html_get",
    annotations=tool_annotations(
        "读取 SDA HTML 报告",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def report_html_get(
    id: Annotated[str, Field(
        description="要读取的报告 ID，来自 report_html_list 或发布时使用的 ID。",
        min_length=1,
    )],
) -> dict[str, Any]:
    """按 ID 读取已发布报告的完整 JSON。

    返回报告原始结构（通常含 meta、summary、conclusions）；适合检查或
    读出后修改并重新发布。不存在时返回工具错误。
    """
    return _get(id)


@mcp.tool(
    name="report_html_delete",
    annotations=tool_annotations(
        "删除 SDA HTML 报告",
        read_only=False, destructive=True, idempotent=False, open_world=True,
    ),
)
@map_tool_errors
def report_html_delete(
    id: Annotated[str, Field(
        description="要永久删除的报告 ID。删除报告 JSON 并从索引移除，不可恢复。",
        min_length=1,
    )],
) -> ReportDeleteOutput:
    """永久删除一个 HTML 报告及其索引项。

    这是不可恢复的破坏性操作；返回 ``success`` 与 ``report_id``。
    """
    return _delete(id)


@mcp.tool(
    name="report_image_generate",
    annotations=tool_annotations(
        "生成单张 AI 图片报告",
        read_only=False, destructive=False, idempotent=False, open_world=True,
    ),
)
@map_tool_errors
def report_image_generate(
    prompt: Annotated[str, Field(
        description="完整生图提示词；应明确版式比例、标题、KPI 数值、趋势结论和视觉风格。调用会产生外部模型费用。",
        min_length=1,
    )],
    model: Annotated[str | None, Field(
        default=None,
        description="可选模型 ID 或 Endpoint ID；不传则使用 config.json 的默认 Seedream 模型",
    )] = None,
    size: Annotated[str | None, Field(
        default=None,
        description="生成尺寸，例如 2K 或模型支持的 WxH；画面比例仍应在 prompt 中明确。",
    )] = None,
    response_format: Annotated[Literal["url", "b64_json"], Field(
        default="url",
        description="url（默认，返回下载链接）| b64_json（转换为 MCP 图片内容块）",
    )] = "url",
    seed: Annotated[int | None, Field(
        default=None,
        description="可选随机种子，范围 -1 到 2147483647。",
        ge=-1,
        le=2_147_483_647,
    )] = None,
    watermark: Annotated[bool, Field(
        default=False,
        description="是否请求模型添加水印，默认 false。",
    )] = False,
) -> CallToolResult:
    """调用火山方舟 Seedream 同步生成一张图片报告。

    structuredContent 返回 provider/model/usage/images 等；url 模式给出约 24h
    有效下载链接，b64_json 另返回 ImageContent。失败不自动重试，避免重复计费。
    """
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
