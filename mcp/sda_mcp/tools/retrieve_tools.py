"""语义检索工具（retrieving_context 内核）→ MCP 工具。

入参平铺：每个字段是独立关键字参数，约束/描述走 Annotated[..., Field(...)]。
"""
from typing import Annotated, Any, Literal

from pydantic import Field

from sda_mcp.skills.retrieving_context import (
    search as _search, cypher as _cypher, schema as _schema, doc as _doc, update_doc as _update_doc,
)
from sda_mcp.tools._common import mcp


@mcp.tool(name="retrieve_search")
def retrieve_search(
    question: Annotated[str, Field(description="自然语言问题", min_length=1)],
    top_k: Annotated[int, Field(
        default=5,
        ge=1,
        le=20,
        description="hybrid 返回融合后的全局 top_k；vector 保持每个目标索引 top_k",
    )] = 5,
    targets: Annotated[list[str] | None, Field(description="限定实体标签")] = None,
    strategy: Annotated[Literal["vector", "hybrid"], Field(
        default="hybrid",
        description="hybrid=默认的向量+CJK全文+RRF融合；vector=兼容的纯向量回退",
    )] = "hybrid",
) -> dict[str, Any]:
    """检索语义层并扩展图上下文；支持纯向量或 Hybrid RRF。只读。"""
    return _search(question, top_k, targets, strategy)


@mcp.tool(name="retrieve_cypher")
def retrieve_cypher(
    statement: Annotated[str, Field(description="Cypher 语句（可写库）", min_length=1)],
) -> dict[str, Any]:
    """直接执行 Cypher，可能修改数据库。"""
    return _cypher(statement)


@mcp.tool(name="retrieve_schema")
def retrieve_schema() -> dict[str, Any]:
    """返回 Neo4j 实时节点属性、唯一字段和关系路径。只读。"""
    return _schema()


@mcp.tool(name="retrieve_doc_read")
def retrieve_doc_read(
    doc: Annotated[str, Field(
        description="飞书 docx 文档 token；仅传 token，不支持完整 URL", min_length=1)],
) -> dict[str, Any]:
    """按 docx token 读取飞书文档并返回 Markdown。只读。"""
    return _doc(doc)


@mcp.tool(name="retrieve_doc_update")
def retrieve_doc_update(
    doc: Annotated[str, Field(
        description="飞书 docx 文档 token；仅传 token，不支持完整 URL", min_length=1)],
    content: Annotated[str, Field(description="覆盖写入的 markdown 正文", min_length=1)],
) -> dict[str, Any]:
    """按 docx token 覆盖更新飞书文档正文为 markdown（如修正报告模板内容）。"""
    return _update_doc(doc, content)


@mcp.tool(name="sync")
def sync(
    dry_run: Annotated[bool, Field(
        default=False,
        description="true=完成源数据、模型和数据库预检但不写库；false=全量重建",
    )] = False,
) -> dict[str, Any]:
    """预检或全量重建飞书语义层、Neo4j 图和 ONNX 向量。"""
    from sda_mcp.skills.retrieving_context_sync import sync_graph
    return sync_graph(dry_run)
