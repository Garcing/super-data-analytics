"""语义检索工具（retrieving_context 内核）→ MCP 工具。

入参平铺：每个字段是独立关键字参数，约束/描述走 Annotated[..., Field(...)]。
"""
from typing import Annotated, Any, Literal

from pydantic import Field

from sda_mcp.skills.retrieving_context import (
    search as _search, cypher as _cypher, schema as _schema, doc as _doc, update_doc as _update_doc,
)
from sda_mcp.tools._common import mcp, map_tool_errors, tool_annotations
from sda_mcp.tools._schemas import (
    DocReadOutput,
    DocUpdateOutput,
    RetrieveCypherOutput,
    RetrieveSchemaOutput,
    RetrieveSearchOutput,
)


@mcp.tool(
    name="retrieve_search",
    annotations=tool_annotations(
        "检索 SDA 业务语义层",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def retrieve_search(
    question: Annotated[str, Field(
        description="要在受治理业务语义层中检索的自然语言问题，例如“复购人数是什么口径”。",
        min_length=1,
    )],
    top_k: Annotated[int, Field(
        default=5,
        ge=1,
        le=20,
        description="结果数。hybrid 为融合后的全局数量；vector 为每个目标索引的数量。",
    )] = 5,
    targets: Annotated[list[str] | None, Field(
        description='可选实体标签白名单，例如 ["指标", "表"]；省略时检索全部已启用实体。',
        min_length=1,
    )] = None,
    strategy: Annotated[Literal["vector", "hybrid"], Field(
        default="hybrid",
        description="hybrid（默认）=向量+CJK全文+精确命中后 RRF 融合；vector=纯向量回退基线。",
    )] = "hybrid",
) -> RetrieveSearchOutput:
    """检索受治理的指标、维度、表和业务上下文，并扩展图邻居。

    返回 ``question``、``strategy``、``results[]``；每个结果含实体
    ``label``、业务 ``properties``、图 ``context``，hybrid 另含
    ``retrieval`` 排序证据。``context`` 按邻居实体类型分桶，桶为
    ``{"items", "total", "truncated"}``；``truncated=true`` 表示邻居超过
    保留上限被截断（``total`` 为真实总数），完整邻居改用 ``retrieve_cypher``。
    """
    return _search(question, top_k, targets, strategy)


@mcp.tool(
    name="retrieve_cypher",
    annotations=tool_annotations(
        "执行 Neo4j Cypher",
        read_only=False, destructive=True, idempotent=False, open_world=True,
    ),
)
@map_tool_errors
def retrieve_cypher(
    statement: Annotated[str, Field(
        description="要直接执行的 Cypher。支持读写语句；写入会修改 SDA Neo4j，执行前必须确认范围。",
        min_length=1,
    )],
) -> RetrieveCypherOutput:
    """直接执行一条 Cypher，并返回 ``cypher`` 与 ``rows[]``。

    此工具允许写库，因此可能产生破坏性变更；常规查询优先使用 MATCH，
    编写前可先调用 ``retrieve_schema``。
    """
    return _cypher(statement)


@mcp.tool(
    name="retrieve_schema",
    annotations=tool_annotations(
        "读取 SDA Neo4j Schema",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def retrieve_schema() -> RetrieveSchemaOutput:
    """实时内省 SDA Neo4j 的节点属性、唯一字段和有向关系路径。

    返回 ``nodes{label: {properties, unique}}`` 与
    ``relationships[]``；不包含 embedding 等检索内部字段。
    """
    return _schema()


@mcp.tool(
    name="retrieve_doc_read",
    annotations=tool_annotations(
        "读取飞书 Docx 正文",
        read_only=True, destructive=False, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def retrieve_doc_read(
    doc: Annotated[str, Field(
        description="飞书 docx 文档 token，例如 SaQ5dDqWfox5DWxLGp5cRPSwnhg；只传 token，不支持完整 URL。",
        min_length=1,
    )],
) -> DocReadOutput:
    """按 docx token 读取飞书文档正文。

    返回 ``content``（Markdown）和 ``document_id``。目标文档必须已共享
    给服务端飞书自建应用。
    """
    return _doc(doc)


@mcp.tool(
    name="retrieve_doc_update",
    annotations=tool_annotations(
        "覆盖更新飞书 Docx 正文",
        read_only=False, destructive=True, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def retrieve_doc_update(
    doc: Annotated[str, Field(
        description="飞书 docx 文档 token；只传 token，不支持完整 URL。",
        min_length=1,
    )],
    content: Annotated[str, Field(
        description="替换文档正文的完整 Markdown；不是追加内容。",
        min_length=1,
    )],
) -> DocUpdateOutput:
    """用完整 Markdown 覆盖飞书文档正文。

    先清空正文块再写入，返回 ``updated`` 与 ``document_id``；不修改
    多维表元数据。调用前应先读取并保留需要继续存在的原内容。
    """
    return _update_doc(doc, content)


@mcp.tool(
    name="sync",
    annotations=tool_annotations(
        "同步 SDA 业务语义层",
        read_only=False, destructive=True, idempotent=False, open_world=True,
    ),
)
@map_tool_errors
def sync(
    dry_run: Annotated[bool, Field(
        default=False,
        description="true=仅拉取并校验飞书数据、模型与 Neo4j，不写库；false（默认）=清空并全量重建图、约束、索引和向量。",
    )] = False,
) -> dict[str, Any]:
    """预检或全量重建飞书多维表到 Neo4j/ONNX 的语义层。

    ``dry_run=true`` 返回校验、源记录数、警告和计划；默认 false 会先清空
    Neo4j 再返回实际节点、关系、索引和 embedding 构建统计。
    """
    from sda_mcp.skills.retrieving_context_sync import sync_graph
    return sync_graph(dry_run)
