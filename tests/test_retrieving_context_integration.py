"""retrieving_context 的真实 Neo4j / 飞书只读冒烟测试。

默认跳过；设置 ``SDA_INTEGRATION=1`` 后启用。
"""
import os

import pytest

from sda_mcp.skills.retrieving_context import cypher, doc, schema


pytestmark = pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="集成测试默认跳过；设 SDA_INTEGRATION=1 启用",
)


# 真实飞书测试文档（含代码块）；可用 SDA_TEST_DOC_TOKEN 覆盖。
_TEST_DOC_TOKEN = "V6TYdWScDoms5axrSmkcM5FHn0b"


def test_live_schema_is_compact_and_nonempty():
    result = schema()

    assert result["nodes"]
    assert isinstance(result["relationships"], list)
    for node in result["nodes"].values():
        assert node["properties"]
        assert "embedding" not in node["properties"]
        assert "search_text" not in node["properties"]


def test_live_cypher_read():
    result = cypher("MATCH (n) RETURN count(n) AS count LIMIT 1")

    assert result["rows"][0]["count"] >= 0


def test_live_doc_raw_content_is_plain_text():
    token = os.environ.get("SDA_TEST_DOC_TOKEN", _TEST_DOC_TOKEN)
    result = doc(token)

    assert result["document_id"] == token
    assert isinstance(result["content"], str) and result["content"].strip()
    # 官方 raw_content 直出纯文本：文档里有代码块也不应出现 Markdown 围栏
    assert "```" not in result["content"]
