"""语义检索工具（retrieving_context 内核）→ MCP 工具。

入参平铺：每个字段是独立关键字参数，约束/描述走 Annotated[..., Field(...)]。
"""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class _DocOperationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocReplaceTextOperation(_DocOperationBase):
    op: Literal["replace_text"]
    block_id: str = Field(min_length=1, description="要替换完整文本的已有块 ID。")
    text: str = Field(description="新的完整纯文本；会重置该块全部行内样式和评论锚点。")


class DocReplaceElementsOperation(_DocOperationBase):
    op: Literal["replace_elements"]
    block_id: str = Field(min_length=1, description="要替换全部行内元素的已有块 ID。")
    elements: list[dict[str, Any]] = Field(
        description=(
            "新的飞书原生 TextElement 数组；先用 retrieve_doc_read(detail='full')，"
            "从目标块 content.elements 复制修改后传回。"
        ),
    )


_INSERT_BLOCK_TYPE = Literal[
    "text", "heading1", "heading2", "heading3", "heading4", "heading5",
    "heading6", "heading7", "heading8", "heading9", "bullet", "ordered",
    "code", "quote", "divider",
]


class DocInsertBlockSpec(_DocOperationBase):
    local_id: str = Field(
        min_length=1,
        description="本次请求内唯一的临时 ID；children/root_ids 用它建立子树。",
    )
    type: _INSERT_BLOCK_TYPE
    text: str | None = Field(
        default=None,
        description="纯文本内容；与 elements 二选一。divider 不需要内容。",
    )
    elements: list[dict[str, Any]] | None = Field(
        default=None,
        description="飞书原生 TextElement 数组；与 text 二选一。",
    )
    style: dict[str, Any] = Field(
        default_factory=dict,
        description="可选块级原生 style；未指定即使用飞书默认样式。",
    )
    language: int | None = Field(
        default=None,
        ge=0,
        description="仅 code 块可用的飞书 CodeLanguage 数值，例如 SQL=56。",
    )
    children: list[str] = Field(
        default_factory=list,
        description="直接子块的 local_id，按文档顺序排列。",
    )


class DocInsertSubtreeOperation(_DocOperationBase):
    op: Literal["insert_subtree"]
    parent_block_id: str = Field(min_length=1, description="承载新子树的已有父块 ID。")
    index: int = Field(ge=0, description="插入到父块 children 的零基位置；末尾等于当前 children 数。")
    root_ids: list[str] = Field(min_length=1, description="要插入的顶层临时 local_id，按顺序排列。")
    blocks: list[DocInsertBlockSpec] = Field(
        min_length=1,
        description="整棵子树的扁平 BlockSpec；一次 descendant 请求完成嵌套插入。",
    )


class DocDeleteChildrenOperation(_DocOperationBase):
    op: Literal["delete_children"]
    parent_block_id: str = Field(min_length=1, description="要删除其直接 children 的父块 ID。")
    start_index: int = Field(ge=0, description="删除半开区间的起始位置（包含）。")
    end_index: int = Field(gt=0, description="删除半开区间的结束位置（不包含）。")


DocOperation = Annotated[
    DocReplaceTextOperation | DocReplaceElementsOperation |
    DocInsertSubtreeOperation | DocDeleteChildrenOperation,
    Field(discriminator="op"),
]


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
    root_block_id: Annotated[str | None, Field(
        description="可选局部读取根块 ID；省略时从 page 根块读取整篇。",
        min_length=1,
    )] = None,
    max_depth: Annotated[int, Field(
        default=-1,
        ge=-1,
        description="从 root_block_id 向下展开的最大层数；-1=不限，0=仅根块。",
    )] = -1,
    detail: Annotated[Literal["compact", "full"], Field(
        default="compact",
        description=(
            "返回详细度。compact（默认）保留块结构、逐字 text 与非行内 content，"
            "省略 content.elements；full 在 content.elements 原样返回富文本行内元素。"
        ),
    )] = "compact",
) -> DocReadOutput:
    """按 docx token 读取飞书文档的结构化块快照。

    返回标题、稳定 ``revision_id``、详细度、局部根块、扁平 ``blocks[]`` 和警告。
    默认 compact 适合读取 SQL/模板并省略冗长行内元素；需要无损富文本更新时对目标
    子树使用 full，原始元素只位于 ``content.elements``，不会重复到块顶层。不经过
    Markdown。更新时必须把本次 ``revision_id`` 传给更新工具。
    """
    return _doc(doc, root_block_id, max_depth, detail)


@mcp.tool(
    name="retrieve_doc_update",
    annotations=tool_annotations(
        "精确更新飞书 Docx 块",
        read_only=False, destructive=True, idempotent=True, open_world=True,
    ),
)
@map_tool_errors
def retrieve_doc_update(
    doc: Annotated[str, Field(
        description="飞书 docx 文档 token；只传 token，不支持完整 URL。",
        min_length=1,
    )],
    expected_revision_id: Annotated[int, Field(
        ge=0,
        description="上一次 retrieve_doc_read 返回的 revision_id；服务端写前与最新 revision 显式比较，不一致即拒绝。",
    )],
    operations: Annotated[list[DocOperation], Field(
        min_length=1,
        max_length=200,
        description=(
            "块操作。多个 replace_text/replace_elements 会走一次批量更新；"
            "insert_subtree 或 delete_children 必须单独调用。"
        ),
    )],
) -> DocUpdateOutput:
    """在指定文档 revision 上精确更新已有块或修改一处子块结构。

    ``replace_text`` 适合 SQL 等纯文本块并会重置行内样式；需要保留富文本时从
    read(detail="full") 的 ``content.elements`` 修改后使用 ``replace_elements``。``insert_subtree``
    接受临时 ID 扁平块图并一次插入嵌套子树；``delete_children`` 删除父块直接
    children 的半开区间。所有操作都执行 revision 前置校验，不再清空全文或经过 Markdown。
    返回前后 revision、受影响 block ID、临时 ID 映射与警告。
    """
    return _update_doc(
        doc,
        expected_revision_id,
        [operation.model_dump(exclude_none=True) for operation in operations],
    )


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
