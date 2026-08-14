"""语义检索工具（retrieving_context 内核）→ MCP 工具。"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sda_mcp.skills.retrieving_context import (
    search as _search, cypher as _cypher, schema as _schema, doc as _doc, update_doc as _update_doc,
)
from sda_mcp.tools._common import mcp


class SearchIn(BaseModel):
    question: str = Field(..., min_length=1, description="自然语言问题")
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="hybrid 返回融合后的全局 top_k；vector 保持每个目标索引 top_k",
    )
    targets: list[str] | None = Field(default=None, description="限定实体标签")
    strategy: Literal["vector", "hybrid"] = Field(
        default="hybrid",
        description="hybrid=默认的向量+CJK全文+RRF融合；vector=兼容的纯向量回退",
    )


class CypherIn(BaseModel):
    statement: str = Field(..., min_length=1, description="Cypher 语句（可写库）")


class DocIn(BaseModel):
    doc: str = Field(..., min_length=1, description="飞书文档 URL 或 token")


class DocUpdateIn(BaseModel):
    doc: str = Field(..., min_length=1, description="飞书文档 token（URL 链接字段里的 docx token）")
    content: str = Field(..., min_length=1, description="覆盖写入的 markdown 正文")


@mcp.tool(name="retrieve_search")
def retrieve_search(params: SearchIn) -> dict[str, Any]:
    """检索语义层并扩展图上下文；支持纯向量或 Hybrid RRF。只读。"""
    return _search(params.question, params.top_k, params.targets, params.strategy)


@mcp.tool(name="retrieve_cypher")
def retrieve_cypher(params: CypherIn) -> dict[str, Any]:
    """直接执行 Cypher，可能修改数据库。"""
    return _cypher(params.statement)


@mcp.tool(name="retrieve_schema")
def retrieve_schema() -> dict[str, Any]:
    """返回 Neo4j 实时节点属性、唯一字段和关系路径。只读。"""
    return _schema()


@mcp.tool(name="retrieve_doc_read")
def retrieve_doc_read(params: DocIn) -> dict[str, Any]:
    """读取飞书文档并返回 Markdown。只读。"""
    return _doc(params.doc)


@mcp.tool(name="retrieve_doc_update")
def retrieve_doc_update(params: DocUpdateIn) -> dict[str, Any]:
    """覆盖更新飞书文档正文为 markdown（如修正报告模板内容）。"""
    return _update_doc(params.doc, params.content)


class SyncIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = Field(
        default=False,
        description="true=完成源数据、模型和数据库预检但不写库；false=全量重建",
    )


@mcp.tool(name="sync")
def sync(params: SyncIn) -> dict[str, Any]:
    """预检或全量重建飞书语义层、Neo4j 图和 ONNX 向量。"""
    from sda_mcp.skills.retrieving_context_sync import sync_graph
    return sync_graph(params.dry_run)
