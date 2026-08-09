"""取数工具（querying_data 内核）→ MCP 工具。"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.querying_data import (
    sql_query as _sql_query, sql_schema as _sql_schema,
    powerbi_list_models as _powerbi_list_models, powerbi_schema as _powerbi_schema,
    powerbi_query as _powerbi_query,
)
from sda_mcp.tools._common import mcp, to_dict


class SqlQueryIn(BaseModel):
    sql: str = Field(..., description="单条 SELECT SQL", min_length=1)
    max_rows: int | None = Field(default=None, description="预留（内核未用）", ge=1)


class SqlSchemaIn(BaseModel):
    tables: list[str] = Field(..., description='schema.table 列表，如 ["public.orders"]', min_length=1)


class ArtifactIn(BaseModel):
    artifact_id: str = Field(..., description="Power BI 语义模型 GUID")


class PowerBIQueryIn(BaseModel):
    artifact_id: str = Field(..., description="Power BI 语义模型 GUID")
    dax_queries: list[str] = Field(..., description="1-4 条 DAX", min_length=1, max_length=4)
    max_rows: int = Field(default=250, description="每条最大行数", ge=1, le=1000)


@mcp.tool(name="sql_query")
def sql_query(params: SqlQueryIn) -> dict[str, Any]:
    """在 Hologres 执行单条 SQL，返回列与行。readOnly。"""
    return to_dict(_sql_query(params.sql))


@mcp.tool(name="sql_schema")
def sql_schema(params: SqlSchemaIn) -> dict[str, Any]:
    """查多张表的列定义。readOnly。"""
    return {"tables": to_dict(_sql_schema(params.tables))}


@mcp.tool(name="powerbi_list_models")
def powerbi_list_models() -> dict[str, Any]:
    """列出 config.json 配置的 Power BI 语义模型。readOnly。"""
    return {"models": _powerbi_list_models()}


@mcp.tool(name="powerbi_schema")
def powerbi_schema(params: ArtifactIn) -> dict[str, Any]:
    """取某语义模型的表/列 schema。readOnly。"""
    return _powerbi_schema(params.artifact_id)


@mcp.tool(name="powerbi_query")
def powerbi_query(params: PowerBIQueryIn) -> dict[str, Any]:
    """对语义模型跑 1-4 条 DAX。readOnly。"""
    return _powerbi_query(params.artifact_id, params.dax_queries, params.max_rows)
