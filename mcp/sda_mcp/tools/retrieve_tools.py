"""语义检索工具（retrieving_context 内核）→ MCP 工具。"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.retrieving_context import (
    search as _search, cypher as _cypher, schema as _schema, doc as _doc,
)
from sda_mcp.tools._common import mcp


class SearchIn(BaseModel):
    question: str = Field(..., min_length=1, description="自然语言问题")
    top_k: int = Field(default=5, ge=1, le=20)
    targets: list[str] | None = Field(default=None, description="限定实体标签")


class CypherIn(BaseModel):
    statement: str = Field(..., min_length=1, description="Cypher 语句（可写库）")


class DocIn(BaseModel):
    doc: str = Field(..., min_length=1, description="飞书文档 URL 或 token")


@mcp.tool(name="retrieve_search")
def retrieve_search(params: SearchIn) -> dict[str, Any]:
    """向量检索语义层 + 图扩展上下文。readOnly。"""
    return _search(params.question, params.top_k, params.targets)


@mcp.tool(name="retrieve_cypher")
def retrieve_cypher(params: CypherIn) -> dict[str, Any]:
    """直接跑 Cypher（可能写库）。destructive。"""
    return _cypher(params.statement)


@mcp.tool(name="retrieve_schema")
def retrieve_schema() -> dict[str, Any]:
    """返回图 schema（实体/关系/embedding 配置）。readOnly。"""
    return _schema()


@mcp.tool(name="retrieve_doc")
def retrieve_doc(params: DocIn) -> dict[str, Any]:
    """读取飞书文档为 markdown。readOnly。"""
    return _doc(params.doc)
