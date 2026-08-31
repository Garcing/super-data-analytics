"""真实飞书 Docx 块读写集成测试（默认跳过）。

测试文档由维护者提供。写测试只在末尾插入一个带唯一 marker 的临时子树，验证后按
顶层 child 区间删除；即使中途断言失败，finally 也会重新读取最新 revision 尝试清理。
"""
import os
from uuid import uuid4

import pytest

from sda_mcp.errors import ValidationError
from sda_mcp.skills import retrieving_context as r


TEST_DOC = os.environ.get("SDA_TEST_DOC_TOKEN", "V6TYdWScDoms5axrSmkcM5FHn0b")
_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="集成测试默认跳过；设 SDA_INTEGRATION=1 启用真实飞书读写",
)


@_INTEGRATION
def test_structured_read_has_nested_table_and_list_blocks():
    snapshot = r.doc(TEST_DOC)
    assert snapshot["title"] == "Markdown 格式测试文档"
    assert snapshot["revision_id"] >= 23
    by_id = {block["block_id"]: block for block in snapshot["blocks"]}
    assert any(block["type"] == "table" and block["children"] for block in snapshot["blocks"])
    assert any(
        block["type"] == "table_cell"
        and any(by_id[child]["type"] == "text" for child in block["children"])
        for block in snapshot["blocks"]
    )
    assert any(block["type"] == "bullet" and block["children"] for block in snapshot["blocks"])
    code = next(block for block in snapshot["blocks"] if block["type"] == "code")
    assert isinstance(code["text"], str)
    assert "```" not in code["text"]


@_INTEGRATION
def test_stale_revision_is_rejected_without_mutation():
    latest = r.doc(TEST_DOC)
    code = next(block for block in latest["blocks"] if block["type"] == "code")
    with pytest.raises(ValidationError, match="revision 冲突"):
        r.update_doc(TEST_DOC, latest["revision_id"] - 1, [{
            "op": "replace_text", "block_id": code["block_id"], "text": code["text"],
        }])
    after = r.doc(TEST_DOC)
    assert after["revision_id"] == latest["revision_id"]


@_INTEGRATION
def test_insert_update_read_delete_nested_subtree_roundtrip():
    marker = f"SDA-BLOCK-INTEGRATION-{uuid4()}"
    sql = f"select * from t where a >= '&' and b < \"{marker}\""
    initial = r.doc(TEST_DOC)
    page = next(block for block in initial["blocks"] if block["type"] == "page")
    real_parent_id = None
    try:
        inserted = r.update_doc(TEST_DOC, initial["revision_id"], [{
            "op": "insert_subtree",
            "parent_block_id": page["block_id"],
            "index": len(page["children"]),
            "root_ids": ["tmp_parent"],
            "blocks": [
                {"local_id": "tmp_parent", "type": "bullet", "text": marker,
                 "children": ["tmp_code"]},
                {"local_id": "tmp_code", "type": "code", "text": "placeholder",
                 "language": 56, "children": []},
            ],
        }])
        relations = {
            item["temporary_block_id"]: item["block_id"]
            for item in inserted["block_id_relations"]
        }
        real_parent_id = relations["tmp_parent"]
        real_code_id = relations["tmp_code"]

        updated = r.update_doc(TEST_DOC, inserted["revision_id"], [{
            "op": "replace_text", "block_id": real_code_id, "text": sql,
        }])
        subtree = r.doc(TEST_DOC, root_block_id=real_parent_id)
        assert subtree["revision_id"] == updated["revision_id"]
        code = next(block for block in subtree["blocks"] if block["block_id"] == real_code_id)
        assert code["text"] == sql
        assert code["elements"][0]["text_run"]["content"] == sql
    finally:
        latest = r.doc(TEST_DOC)
        page = next(block for block in latest["blocks"] if block["type"] == "page")
        target_id = real_parent_id
        if target_id not in page["children"]:
            # 关系映射尚未拿到时，用唯一 marker 定位顶层临时块。
            target_id = next((
                block["block_id"] for block in latest["blocks"]
                if block.get("text") == marker and block.get("parent_id") == page["block_id"]
            ), None)
        if target_id in page["children"]:
            index = page["children"].index(target_id)
            r.update_doc(TEST_DOC, latest["revision_id"], [{
                "op": "delete_children",
                "parent_block_id": page["block_id"],
                "start_index": index,
                "end_index": index + 1,
            }])
