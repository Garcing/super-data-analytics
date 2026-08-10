"""飞书报告模板内核。

全部走飞书开放平台 REST（FeishuClient）：list/read/delete/create/update 均用
FeishuClient 的对应端点，不再依赖 lark-cli 子进程。

行为对齐点：
- list：根目录 + 每个子文件夹一层（ThreadPoolExecutor 并行），过滤 docx/doc。
- read：FeishuClient.get_doc_markdown 直出 markdown。
- delete：FEISHU_TEMPLATE_DELETE_PASSWORD 已配置则强制校验，否则跳过门。
- create：FeishuClient.create_doc 建空文档；有 content 则 convert_markdown_to_blocks
  → insert_descendants（表格 merge_info 已在 convert 内剥除）。
- update（覆盖语义）：delete_all_children 清空正文 → convert_markdown_to_blocks
  → insert_descendants。

失败抛 ConfigError(凭证缺失)/ValidationError(参数)；飞书 API 错误由 FeishuClient
内部抛 ExternalAPIError。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from sda_mcp.config import get_env, load_config
from sda_mcp.errors import ConfigError, ValidationError
from sda_mcp.feishu import FeishuClient


@dataclass
class CreateResult:
    document_id: str
    title: str


@dataclass
class UpdateResult:
    updated: bool
    document_id: str


@dataclass
class DeleteResult:
    deleted: bool
    document_id: str


def list_templates() -> list[dict[str, Any]]:
    """列出文件夹下文档：根目录（category 为空）+ 每个子文件夹一层。"""
    folder_token = get_env("FEISHU_TEMPLATE_FOLDER_TOKEN")["FEISHU_TEMPLATE_FOLDER_TOKEN"]
    client = FeishuClient()
    root_files = client.list_folder_files(folder_token)

    def _entry(f: dict[str, Any], category: str) -> dict[str, Any]:
        return {
            "id": f.get("token") or f.get("id"),
            "name": f.get("name"),
            "category": category,
            "type": f.get("type"),
            "url": f.get("url"),
            "modified_time": f.get("modified_time"),
        }

    results = [_entry(f, "") for f in root_files if f.get("type") in ("docx", "doc")]
    sub_folders = [f for f in root_files if f.get("type") == "folder"]

    def _sub(folder: dict[str, Any]) -> list[dict[str, Any]]:
        files = client.list_folder_files(folder.get("token") or folder.get("id"))
        return [_entry(f, folder.get("name", "")) for f in files if f.get("type") in ("docx", "doc")]

    if sub_folders:
        with ThreadPoolExecutor(max_workers=min(8, len(sub_folders))) as ex:
            for sub in ex.map(_sub, sub_folders):
                results.extend(sub)
    return results


def read_template(doc_id: str) -> str:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    return FeishuClient().get_doc_markdown(doc_id)


def create_template(title: str, content: str | None = None) -> CreateResult:
    if not title:
        raise ValidationError("title 不能为空")
    folder_token = get_env("FEISHU_TEMPLATE_FOLDER_TOKEN")["FEISHU_TEMPLATE_FOLDER_TOKEN"]
    client = FeishuClient()
    doc_id = client.create_doc(folder_token, title)
    if content is not None:
        if not isinstance(content, str) or not content:
            raise ValidationError("content 不能为空")
        blocks, children_id = client.convert_markdown_to_blocks(content)
        if blocks:
            client.insert_descendants(doc_id, blocks, children_id)
    return CreateResult(document_id=doc_id, title=title)


def update_template(doc_id: str, content: str) -> UpdateResult:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    if not isinstance(content, str) or not content:
        raise ValidationError("content 不能为空")
    client = FeishuClient()
    client.delete_all_children(doc_id)
    blocks, children_id = client.convert_markdown_to_blocks(content)
    if blocks:
        client.insert_descendants(doc_id, blocks, children_id)
    return UpdateResult(updated=True, document_id=doc_id)


def delete_template(doc_id: str, password: str | None = None) -> DeleteResult:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    env_password = (load_config().get("env", {}) or {}).get("FEISHU_TEMPLATE_DELETE_PASSWORD")
    if env_password:
        if not password:
            raise ValidationError("需要密码（已设置 FEISHU_TEMPLATE_DELETE_PASSWORD）")
        if password != env_password:
            raise ValidationError("密码错误")
    FeishuClient().delete_file(doc_id, "docx")
    return DeleteResult(deleted=True, document_id=doc_id)
