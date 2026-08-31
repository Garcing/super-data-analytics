"""飞书 Docx 原始块的确定性规范化、局部选择与写入规格转换。

本模块不感知 MCP，也不把块转换成 Markdown。飞书原始块是事实源；对外读取仅把
动态属性键规范化为 ``type/content``，同时保留 block_id、parent_id、children 和
原始行内 elements。写入只支持 SDA 当前需要的文本类块与 divider，复杂资源块保持
只读，避免伪造不完整结构。
"""
from __future__ import annotations

from typing import Any

from sda_mcp.errors import ValidationError


_BLOCK_KEYS: dict[int, tuple[str, str]] = {
    1: ("page", "page"),
    2: ("text", "text"),
    **{level + 2: (f"heading{level}", f"heading{level}") for level in range(1, 10)},
    12: ("bullet", "bullet"),
    13: ("ordered", "ordered"),
    14: ("code", "code"),
    15: ("quote", "quote"),
    22: ("divider", "divider"),
    31: ("table", "table"),
    32: ("table_cell", "table_cell"),
    34: ("quote_container", "quote_container"),
}
_TEXT_BLOCK_TYPES = frozenset(range(2, 16))
_INSERT_TYPES: dict[str, tuple[int, str]] = {
    "text": (2, "text"),
    **{f"heading{level}": (level + 2, f"heading{level}") for level in range(1, 10)},
    "bullet": (12, "bullet"),
    "ordered": (13, "ordered"),
    "code": (14, "code"),
    "quote": (15, "quote"),
    "divider": (22, "divider"),
}
_INLINE_ELEMENT_KEYS = frozenset({
    "text_run", "mention_user", "mention_doc", "reminder", "file",
    "undefined", "inline_block", "equation", "link_preview",
})


def is_text_block(block_type: int | None) -> bool:
    return isinstance(block_type, int) and block_type in _TEXT_BLOCK_TYPES


def validate_elements(elements: Any, *, field: str = "elements") -> list[dict[str, Any]]:
    if not isinstance(elements, list):
        raise ValidationError(f"{field} 必须是行内元素数组")
    checked: list[dict[str, Any]] = []
    for index, element in enumerate(elements):
        if not isinstance(element, dict) or len(element) != 1:
            raise ValidationError(f"{field}[{index}] 必须是仅含一种行内元素的对象")
        kind = next(iter(element))
        if kind not in _INLINE_ELEMENT_KEYS:
            raise ValidationError(f"{field}[{index}] 含不支持的行内元素 {kind}")
        if kind == "text_run":
            run = element[kind]
            if not isinstance(run, dict) or not isinstance(run.get("content"), str):
                raise ValidationError(f"{field}[{index}].text_run.content 必须是字符串")
        checked.append(element)
    return checked


def normalize_blocks(
    blocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """把飞书动态块属性规范化为稳定的扁平块数组；未知类型显式保留 raw。"""
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    for block in blocks:
        block_id = block.get("block_id")
        block_type = block.get("block_type")
        known = _BLOCK_KEYS.get(block_type)
        out: dict[str, Any] = {
            "block_id": block_id or "",
            "parent_id": block.get("parent_id") or "",
            "block_type": block_type,
            "type": known[0] if known else f"block_type_{block_type}",
            "children": list(block.get("children") or []),
        }
        if known:
            content = block.get(known[1]) or {}
            out["content"] = content
            if is_text_block(block_type):
                elements = content.get("elements") or []
                out["elements"] = elements
                parts: list[str] = []
                for index, element in enumerate(elements):
                    run = element.get("text_run") if isinstance(element, dict) else None
                    if isinstance(run, dict):
                        parts.append(run.get("content") or "")
                    else:
                        kind = next(iter(element), "unknown") if isinstance(element, dict) else "unknown"
                        warnings.append(
                            f"块 {block_id} 的行内元素 {index} 为 {kind}；text 仅拼接 text_run，"
                            "完整内容见 elements"
                        )
                out["text"] = "".join(parts)
        else:
            out["raw"] = block
            warnings.append(
                f"块 {block_id} 使用未规范化的 block_type={block_type}；已在 raw 中原样保留"
            )
        normalized.append(out)
    return normalized, warnings


def select_subtree(
    blocks: list[dict[str, Any]], root_block_id: str, max_depth: int = -1,
) -> tuple[list[dict[str, Any]], list[str]]:
    """按 children ID 在本地选出先序子树；不产生递归网络请求。"""
    if max_depth < -1:
        raise ValidationError("max_depth 必须为 -1 或非负整数")
    by_id = {block.get("block_id"): block for block in blocks if block.get("block_id")}
    if root_block_id not in by_id:
        raise ValidationError(f"文档中不存在 root_block_id={root_block_id}")

    selected: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()

    def visit(block_id: str, depth: int) -> None:
        if block_id in seen:
            warnings.append(f"检测到重复或循环引用 block_id={block_id}，已停止继续展开")
            return
        block = by_id.get(block_id)
        if block is None:
            warnings.append(f"children 引用了响应中不存在的 block_id={block_id}")
            return
        seen.add(block_id)
        selected.append(block)
        if max_depth != -1 and depth >= max_depth:
            return
        for child_id in block.get("children") or []:
            visit(child_id, depth + 1)

    visit(root_block_id, 0)
    return selected, warnings


def plain_text_element(text: str) -> dict[str, Any]:
    return {"text_run": {"content": text, "text_element_style": {}}}


def update_request(operation: dict[str, Any]) -> dict[str, Any]:
    op = operation.get("op")
    block_id = operation.get("block_id")
    if op == "replace_text":
        text = operation.get("text")
        if not isinstance(text, str):
            raise ValidationError("replace_text.text 必须是字符串")
        elements = [plain_text_element(text)]
    elif op == "replace_elements":
        elements = validate_elements(operation.get("elements"), field="replace_elements.elements")
    else:
        raise ValidationError(f"不支持的文本更新操作 {op}")
    return {"block_id": block_id, "update_text_elements": {"elements": elements}}


def build_descendants(operation: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """把紧凑 BlockSpec 转换成 descendant API 的临时 ID 扁平块图。"""
    specs = operation.get("blocks")
    root_ids = operation.get("root_ids")
    if not isinstance(specs, list) or not specs:
        raise ValidationError("insert_subtree.blocks 不能为空")
    if not isinstance(root_ids, list) or not root_ids:
        raise ValidationError("insert_subtree.root_ids 不能为空")
    if any(not isinstance(root_id, str) or not root_id for root_id in root_ids):
        raise ValidationError("insert_subtree.root_ids 必须是非空字符串数组")
    if len(root_ids) != len(set(root_ids)):
        raise ValidationError("insert_subtree.root_ids 不能重复")

    by_id: dict[str, dict[str, Any]] = {}
    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise ValidationError(f"insert_subtree.blocks[{index}] 必须是对象")
        local_id = spec.get("local_id")
        if not isinstance(local_id, str) or not local_id:
            raise ValidationError(f"insert_subtree.blocks[{index}].local_id 不能为空")
        if local_id in by_id:
            raise ValidationError(f"insert_subtree.local_id 重复: {local_id}")
        by_id[local_id] = spec

    referenced: set[str] = set()
    parent_counts: dict[str, int] = {}
    for local_id, spec in by_id.items():
        for child_id in spec.get("children") or []:
            if child_id not in by_id:
                raise ValidationError(f"块 {local_id} 引用了不存在的 child local_id={child_id}")
            referenced.add(child_id)
            parent_counts[child_id] = parent_counts.get(child_id, 0) + 1
            if parent_counts[child_id] > 1:
                raise ValidationError(f"child local_id={child_id} 不能同时属于多个父块")
    for root_id in root_ids:
        if root_id not in by_id:
            raise ValidationError(f"root_ids 引用了不存在的 local_id={root_id}")

    visited: set[str] = set()
    active: set[str] = set()

    def visit(local_id: str) -> None:
        if local_id in active:
            raise ValidationError(f"insert_subtree 存在循环引用: {local_id}")
        if local_id in visited:
            return
        active.add(local_id)
        for child_id in by_id[local_id].get("children") or []:
            visit(child_id)
        active.remove(local_id)
        visited.add(local_id)

    for root_id in root_ids:
        visit(root_id)
    for root_id in root_ids:
        if root_id in referenced:
            raise ValidationError(f"root_id={root_id} 同时被其他块作为 child 引用")
    if visited != set(by_id):
        unreachable = sorted(set(by_id) - visited)
        raise ValidationError(f"insert_subtree 含未从 root_ids 可达的块: {unreachable}")

    descendants: list[dict[str, Any]] = []
    for spec in specs:
        kind = spec.get("type")
        mapped = _INSERT_TYPES.get(kind)
        if mapped is None:
            raise ValidationError(f"insert_subtree 暂不支持块类型 {kind}")
        block_type, key = mapped
        children = list(spec.get("children") or [])
        native: dict[str, Any] = {
            "block_id": spec["local_id"],
            "block_type": block_type,
        }
        if children:
            native["children"] = children
        if kind == "divider":
            native[key] = {}
        else:
            elements = spec.get("elements")
            text = spec.get("text")
            if elements is not None and text is not None:
                raise ValidationError(f"块 {spec['local_id']} 不能同时设置 text 与 elements")
            if elements is None:
                elements = [plain_text_element(text or "")]
            else:
                elements = validate_elements(elements, field=f"块 {spec['local_id']}.elements")
            style = dict(spec.get("style") or {})
            language = spec.get("language")
            if language is not None:
                if kind != "code":
                    raise ValidationError(f"只有 code 块可设置 language（块 {spec['local_id']}）")
                style["language"] = language
            native[key] = {"elements": elements, "style": style}
        descendants.append(native)
    return list(root_ids), descendants
