"""retrieving_context 的真实 Neo4j 只读冒烟测试。

默认跳过；设置 ``SDA_INTEGRATION=1`` 后启用。
"""
import os

import pytest

from sda_mcp.skills.retrieving_context import cypher, schema


pytestmark = pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="Neo4j 集成测试默认跳过；设 SDA_INTEGRATION=1 启用",
)


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
