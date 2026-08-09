"""模板工具（using_templates 内核，包 lark-cli）→ MCP 工具。"""
from typing import Any

from pydantic import BaseModel, Field

from sda_mcp.skills.using_templates import (
    list_templates as _list, read_template as _read, create_template as _create,
    update_template as _update, delete_template as _delete,
)
from sda_mcp.tools._common import mcp


class ReadTemplateIn(BaseModel):
    doc_id: str = Field(..., min_length=1)


class CreateTemplateIn(BaseModel):
    title: str = Field(..., min_length=1)
    content: str | None = Field(default=None, description="markdown 正文；缺省则建空文档")


class UpdateTemplateIn(BaseModel):
    doc_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1, description="覆盖写入的 markdown")


class DeleteTemplateIn(BaseModel):
    doc_id: str = Field(..., min_length=1)
    password: str | None = Field(default=None, description="FEISHU_TEMPLATE_DELETE_PASSWORD 已配置时必填")


@mcp.tool(name="template_list")
def template_list() -> dict[str, Any]:
    """列出飞书模板文件夹下的文档。readOnly。"""
    return {"templates": _list()}


@mcp.tool(name="template_read")
def template_read(params: ReadTemplateIn) -> dict[str, Any]:
    """读取模板为 markdown。readOnly。"""
    return {"content": _read(params.doc_id)}


@mcp.tool(name="template_create")
def template_create(params: CreateTemplateIn) -> dict[str, Any]:
    """创建模板文档。"""
    r = _create(params.title, params.content)
    return {"document_id": r.document_id, "title": r.title}


@mcp.tool(name="template_update")
def template_update(params: UpdateTemplateIn) -> dict[str, Any]:
    """覆盖更新模板。"""
    r = _update(params.doc_id, params.content)
    return {"updated": r.updated, "document_id": r.document_id}


@mcp.tool(name="template_delete")
def template_delete(params: DeleteTemplateIn) -> dict[str, Any]:
    """删除模板（destructive，可能需密码）。"""
    r = _delete(params.doc_id, params.password)
    return {"deleted": r.deleted, "document_id": r.document_id}
