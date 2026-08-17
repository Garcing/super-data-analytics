"""取数工具（querying_data 内核）→ MCP 工具。

入参平铺：每个字段是独立关键字参数，约束/描述走 Annotated[..., Field(...)]。
"""
from typing import Annotated, Any

from pydantic import Field

from sda_mcp.skills.querying_data import (
    sql_query as _sql_query, sql_schema as _sql_schema,
    powerbi_schema as _powerbi_schema, powerbi_query as _powerbi_query,
)
from sda_mcp.tools._common import mcp, to_dict


@mcp.tool(name="sql_query")
def sql_query(
    sql: Annotated[str, Field(description="单条 SELECT SQL", min_length=1)],
    max_rows: Annotated[int | None, Field(description="预留（内核未用）", ge=1)] = None,
) -> dict[str, Any]:
    """在 Hologres 执行单条 SQL，返回列与行。readOnly。"""
    return to_dict(_sql_query(sql))


@mcp.tool(name="sql_schema")
def sql_schema(
    tables: Annotated[list[str], Field(
        description='schema.table 列表，如 ["public.orders"]', min_length=1)],
) -> dict[str, Any]:
    """查多张表的列定义。readOnly。"""
    return {"tables": to_dict(_sql_schema(tables))}


@mcp.tool(name="powerbi_schema")
def powerbi_schema(
    artifact_id: Annotated[str, Field(description="Power BI 语义模型 GUID")],
) -> dict[str, Any]:
    """取某语义模型的表/列 schema。readOnly。"""
    return _powerbi_schema(artifact_id)


@mcp.tool(name="powerbi_query")
def powerbi_query(
    artifact_id: Annotated[str, Field(description="Power BI 语义模型 GUID")],
    dax_queries: Annotated[list[str], Field(description="1-4 条 DAX", min_length=1, max_length=4)],
    max_rows: Annotated[int, Field(description="每条最大行数", ge=1, le=1000)] = 250,
) -> dict[str, Any]:
    """对语义模型跑 1-4 条 DAX。readOnly。"""
    return _powerbi_query(artifact_id, dax_queries, max_rows)
