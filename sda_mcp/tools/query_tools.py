"""取数工具（querying_data 内核）→ MCP 工具。

入参平铺：每个字段是独立关键字参数，约束/描述走 Annotated[..., Field(...)]。
"""
from typing import Annotated, Any

from pydantic import Field

from sda_mcp.skills.querying_data import (
    sql_query as _sql_query, sql_schema as _sql_schema,
    powerbi_schema as _powerbi_schema, powerbi_query as _powerbi_query,
)
from sda_mcp.tools._common import mcp, map_tool_errors, to_dict, tool_annotations
from sda_mcp.tools._schemas import SqlQueryOutput, SqlSchemaOutput


_GUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


@mcp.tool(
    name="sql_query",
    annotations=tool_annotations(
        "执行 Hologres SQL",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def sql_query(
    sql: Annotated[str, Field(
        description="一条 Hologres/PostgreSQL SQL；事务强制只读。结果不会自动截断，大结果请在 SQL 中聚合或 LIMIT。",
        min_length=1,
    )],
) -> SqlQueryOutput:
    """在 Hologres 执行一条只读 SQL。

    返回 ``columns``（列名和类型 OID）、``rows``（行对象数组）与
    ``row_count``。不负责解析业务口径，也不自动限制返回行数。
    """
    return to_dict(_sql_query(sql))


@mcp.tool(
    name="sql_schema",
    annotations=tool_annotations(
        "读取 Hologres 表结构",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def sql_schema(
    tables: Annotated[list[str], Field(
        description='要内省的物理表列表；每项必须为 schema.table，例如 ["public.orders"]。',
        min_length=1,
    )],
) -> SqlSchemaOutput:
    """读取一张或多张 Hologres 物理表的列定义。

    返回 ``tables[]``；每项包含 ``schema``、``table`` 和来自
    ``information_schema`` 的 ``columns[]``。语义逻辑表不适用。
    """
    return {"tables": _sql_schema(tables)}


@mcp.tool(
    name="powerbi_schema",
    annotations=tool_annotations(
        "读取 Power BI 语义模型结构",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def powerbi_schema(
    artifact_id: Annotated[str, Field(
        description="Power BI 语义模型 artifact GUID，例如 11111111-2222-3333-4444-555555555555。",
        pattern=_GUID_PATTERN,
    )],
) -> dict[str, Any]:
    """通过 Fabric MCP 读取语义模型的表、列和度量值结构。

    返回 Microsoft ``GetSemanticModelSchema`` 的原始 JSON-RPC 结果；
    写 DAX 前用它确认准确名称。
    """
    return _powerbi_schema(artifact_id)


@mcp.tool(
    name="powerbi_query",
    annotations=tool_annotations(
        "执行 Power BI DAX",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def powerbi_query(
    artifact_id: Annotated[str, Field(
        description="Power BI 语义模型 artifact GUID。",
        pattern=_GUID_PATTERN,
    )],
    dax_queries: Annotated[list[str], Field(
        description='要批量执行的 1-4 条非空 DAX，例如 ["EVALUATE ROW(\\"test\\", 1)"]。',
        min_length=1,
        max_length=4,
    )],
    max_rows: Annotated[int, Field(
        description="每条 DAX 最多返回的行数，默认 250。",
        ge=1,
        le=1000,
    )] = 250,
) -> dict[str, Any]:
    """通过 Fabric MCP 批量执行 1-4 条只读 DAX。

    返回 Microsoft ``ExecuteQuery`` 的原始 JSON-RPC 结果。服务端会处理
    202 异步轮询，最长约 60 秒。
    """
    return _powerbi_query(artifact_id, dax_queries, max_rows)
