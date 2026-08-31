"""飞书 Docx 结构化块规范化与子树写入规格测试。"""
import pytest

from sda_mcp.errors import ValidationError
from sda_mcp.skills.docx_blocks import (
    build_descendants,
    normalize_blocks,
    select_subtree,
    update_request,
)


def _nested_blocks():
    return [
        {"block_id": "PAGE", "block_type": 1, "page": {}, "children": ["B1", "TB"]},
        {"block_id": "B1", "parent_id": "PAGE", "block_type": 12,
         "children": ["B2"], "bullet": {"elements": [
             {"text_run": {"content": "父项", "text_element_style": {}}},
         ], "style": {}}},
        {"block_id": "B2", "parent_id": "B1", "block_type": 12,
         "bullet": {"elements": [
             {"text_run": {"content": "子项", "text_element_style": {"italic": True}}},
         ], "style": {}}},
        {"block_id": "TB", "parent_id": "PAGE", "block_type": 31,
         "children": ["CELL"], "table": {"cells": ["CELL"],
             "property": {"row_size": 1, "column_size": 1}}},
        {"block_id": "CELL", "parent_id": "TB", "block_type": 32,
         "children": ["T1"], "table_cell": {}},
        {"block_id": "T1", "parent_id": "CELL", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "表格文本"}}], "style": {}}},
    ]


def test_select_subtree_is_local_and_preserves_preorder():
    selected, warnings = select_subtree(_nested_blocks(), "TB")
    assert [block["block_id"] for block in selected] == ["TB", "CELL", "T1"]
    assert warnings == []


def test_select_subtree_honors_max_depth():
    selected, _ = select_subtree(_nested_blocks(), "PAGE", max_depth=1)
    assert [block["block_id"] for block in selected] == ["PAGE", "B1", "TB"]


def test_normalize_keeps_exact_text_and_native_elements():
    normalized, warnings = normalize_blocks(_nested_blocks())
    by_id = {block["block_id"]: block for block in normalized}
    assert by_id["B2"]["type"] == "bullet"
    assert by_id["B2"]["text"] == "子项"
    assert by_id["B2"]["elements"][0]["text_run"]["text_element_style"]["italic"] is True
    assert by_id["TB"]["content"]["property"]["column_size"] == 1
    assert warnings == []


def test_normalize_unknown_block_is_opaque_not_fatal():
    raw = {"block_id": "X", "parent_id": "PAGE", "block_type": 999,
           "future_widget": {"answer": 42}}
    normalized, warnings = normalize_blocks([raw])
    assert normalized[0]["type"] == "block_type_999"
    assert normalized[0]["raw"] == raw
    assert "未规范化" in warnings[0]


def test_update_request_replace_text_is_verbatim_without_markdown():
    request = update_request({
        "op": "replace_text", "block_id": "C1",
        "text": "select * from t where a >= '&' and b < \"x\"",
    })
    run = request["update_text_elements"]["elements"][0]["text_run"]
    assert run["content"] == "select * from t where a >= '&' and b < \"x\""
    assert run["text_element_style"] == {}


def test_build_descendants_converts_nested_specs_once():
    roots, blocks = build_descendants({
        "root_ids": ["a"],
        "blocks": [
            {"local_id": "a", "type": "bullet", "text": "父", "children": ["b"]},
            {"local_id": "b", "type": "code", "text": "select *", "language": 56,
             "children": []},
        ],
    })
    assert roots == ["a"]
    assert blocks[0]["block_type"] == 12 and blocks[0]["children"] == ["b"]
    assert blocks[1]["code"]["style"]["language"] == 56
    assert blocks[1]["code"]["elements"][0]["text_run"]["content"] == "select *"


def test_build_descendants_rejects_cycle():
    with pytest.raises(ValidationError, match="循环"):
        build_descendants({
            "root_ids": ["a"],
            "blocks": [
                {"local_id": "a", "type": "bullet", "children": ["b"]},
                {"local_id": "b", "type": "bullet", "children": ["a"]},
            ],
        })


def test_build_descendants_rejects_shared_child():
    with pytest.raises(ValidationError, match="多个父块"):
        build_descendants({
            "root_ids": ["a", "b"],
            "blocks": [
                {"local_id": "a", "type": "bullet", "children": ["c"]},
                {"local_id": "b", "type": "bullet", "children": ["c"]},
                {"local_id": "c", "type": "text", "text": "x", "children": []},
            ],
        })
