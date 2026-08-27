"""P1-1 回归：run_cypher 必须把图元素序列化为 JSON 安全结构。

背景：neo4j driver 6.x 移除了 ``Node.properties`` 属性（Node 改为纯 Mapping 协议），
旧实现 ``hasattr(val, "properties")`` 判定失效 → ``RETURN n`` / ``RETURN properties(n)``
原样穿透，MCP 序列化崩溃成裸错误（2026-08-26 QA 实锤）。
"""
import json
from collections.abc import Mapping

from sda_mcp.skills import retrieving_context as rc


class _FakeNode(Mapping):
    """模拟 neo4j driver 6.x Node：Mapping 协议、无 .properties 属性。"""

    def __init__(self, props):
        self._props = props

    def __getitem__(self, key):
        return self._props[key]

    def __iter__(self):
        return iter(self._props)

    def __len__(self):
        return len(self._props)


class _FakePath:
    """模拟 neo4j Path：有 nodes / relationships 属性、非 Mapping。"""

    def __init__(self, nodes):
        self.nodes = nodes
        self.relationships = []


class _Rec:
    def __init__(self, data):
        self._data = data

    def keys(self):
        return list(self._data)

    def __getitem__(self, key):
        return self._data[key]


class _FakeSession:
    def __init__(self, records):
        self._records = records

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run(self, statement):
        return iter(self._records)


def _client(monkeypatch, records):
    client = rc.Neo4jClient.__new__(rc.Neo4jClient)  # 跳过 __init__（不连真库）
    monkeypatch.setattr(client, "_session", lambda: _FakeSession(records))
    return client


def test_run_cypher_serializes_driver6_nodes(monkeypatch):
    node = _FakeNode({"业务线名称": "A", "embedding": [0.1] * 4, "search_text": "x"})
    other = _FakeNode({"维度名称": "d"})
    client = _client(monkeypatch, [_Rec({"n": node, "others": [other]})])

    rows = client.run_cypher("MATCH (n) RETURN n, [other] LIMIT 1")

    json.dumps(rows)  # 必须整体 JSON 可序列化（旧实现在此 TypeError）
    assert rows[0]["n"]["业务线名称"] == "A"
    assert "embedding" not in rows[0]["n"]      # 内部字段被清洗
    assert "search_text" not in rows[0]["n"]
    assert rows[0]["others"][0]["维度名称"] == "d"


def test_run_cypher_cleans_plain_properties_dict(monkeypatch):
    """RETURN properties(n) 返回普通 dict，同样要清洗内部字段。"""
    props = {"指标ID": "m1", "embedding": [0.1] * 4, "embedding_model": "bge"}
    client = _client(monkeypatch, [_Rec({"props": props})])

    rows = client.run_cypher("MATCH (n) RETURN properties(n) AS props")

    json.dumps(rows)
    assert rows[0]["props"]["指标ID"] == "m1"
    assert "embedding" not in rows[0]["props"]


def test_run_cypher_serializes_paths(monkeypatch):
    node = _FakeNode({"名称": "x"})
    client = _client(monkeypatch, [_Rec({"p": _FakePath([node])})])

    rows = client.run_cypher("MATCH p=(a)-[r]->(b) RETURN p LIMIT 1")

    data = json.dumps(rows)
    assert "nodes" in rows[0]["p"]
    assert rows[0]["p"]["nodes"][0]["名称"] == "x"
    assert "relationships" in rows[0]["p"]
