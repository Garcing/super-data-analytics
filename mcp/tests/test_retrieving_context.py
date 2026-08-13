"""retrieving_context 内核 mock 单元测试（离线）。"""
import pytest
from sda_mcp.errors import ValidationError
from sda_mcp.skills import retrieving_context as r

GC = {
    "embedding": {"model": "BAAI/bge-small-zh-v1.5", "dimensions": 512},
    "entities": {"指标": {"key_field": "指标ID", "table_id": "tbl1", "vector_index": True},
                 "表": {"key_field": "表ID", "table_id": "tbl2", "vector_index": False}},
    "relationships": [{"type": "属于", "from": "指标", "to": "表"}],
}


def test_clean_properties_strips_internal():
    out = r._clean_properties({"name": "GMV", "embedding": [1, 2], "search_text": "x"})
    assert out == {"name": "GMV"}


def test_schema_builds_from_graph_config(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC})
    s = r.schema()
    labels = [e["label"] for e in s["entities"]]
    assert "指标" in labels and "表" in labels
    assert s["relationships"][0]["type"] == "属于"
    assert not hasattr(s, "ok")


def test_search_sorts_and_cleans(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC, "env": {"NEO4J_PASSWORD": "p"}})
    monkeypatch.setattr(r, "embed", lambda text: [0.1] * 512)

    class FakeClient:
        def __init__(self): pass
        def close(self): pass
        def find_vector_index_name(self, label): return "idx" if label == "指标" else None
        def search_vector_index(self, idx, label, emb, top_k):
            return [{"id": "a", "score": 0.9, "properties": {"name": "A", "embedding": [0]}},
                    {"id": "b", "score": 0.5, "properties": {"name": "B"}}]
        def fetch_graph_context(self, label, nid, rels): return {}
    monkeypatch.setattr(r, "Neo4jClient", FakeClient)
    out = r.search("GMV", top_k=5)
    assert out["results"][0]["score"] == 0.9
    assert out["results"][0]["properties"] == {"name": "A"}
    assert not hasattr(out, "ok")


def test_search_empty_question(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC, "env": {"NEO4J_PASSWORD": "p"}})
    with pytest.raises(ValidationError):
        r.search("   ")


def test_cypher_empty():
    with pytest.raises(ValidationError):
        r.cypher("  ")


def test_doc_returns_markdown(monkeypatch):
    monkeypatch.setattr(r.FeishuClient, "get_doc_markdown",
                        lambda self, tok: "# 标题\n正文")
    out = r.doc("DOCTOKEN")
    assert out["content"] == "# 标题\n正文"
    assert out["document_id"] == "DOCTOKEN"


def test_doc_empty_id_raises():
    with pytest.raises(ValidationError):
        r.doc("")


def test_update_doc_overwrite_calls_feishu(monkeypatch):
    """update_doc：清空正文 → convert → insert，返回 updated 标记。"""
    calls = []
    monkeypatch.setattr(r.FeishuClient, "delete_all_children",
                        lambda self, did: calls.append(("del", did)))
    monkeypatch.setattr(r.FeishuClient, "convert_markdown_to_blocks",
                        lambda self, md: ([{"block_type": 2}], ["b1"]))
    monkeypatch.setattr(r.FeishuClient, "insert_descendants",
                        lambda self, did, bl, cid: calls.append(("insert", did)))
    out = r.update_doc("DOC", "新内容")
    assert out == {"updated": True, "document_id": "DOC"}
    assert calls[0] == ("del", "DOC")
    assert calls[1] == ("insert", "DOC")


def test_update_doc_empty_content_raises():
    with pytest.raises(ValidationError):
        r.update_doc("DOC", "")


class _FakeSession:
    """记录传给 .run() 的 Cypher 与参数；返回空记录列表。"""

    def __init__(self):
        self.captured_cyphers = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, cypher, **kwargs):
        self.captured_cyphers.append(cypher)
        return iter([])


def _make_client(monkeypatch):
    """绕过 __init__（避免真实 driver），仅装配 fetch_graph_context 所需属性。"""
    client = r.Neo4jClient.__new__(r.Neo4jClient)
    client._database = "neo4j"
    fake_session = _FakeSession()
    monkeypatch.setattr(client, "_session", lambda: fake_session)
    return client, fake_session


def test_fetch_graph_context_self_loop_is_undirected(monkeypatch):
    """from == to == label：自环走无向 -[:T]-。"""
    client, session = _make_client(monkeypatch)
    rels = [{"type": "关联", "from": "指标", "to": "指标"}]
    client.fetch_graph_context("指标", "node-1", rels)
    assert any("-[:`关联`]-" in c for c in session.captured_cyphers), session.captured_cyphers


def test_fetch_graph_context_outgoing_is_directed(monkeypatch):
    """from == label 且 to != label：出边走 -[:T]->。"""
    client, session = _make_client(monkeypatch)
    rels = [{"type": "属于", "from": "指标", "to": "表"}]
    client.fetch_graph_context("指标", "node-1", rels)
    assert any("-[:`属于`]->" in c for c in session.captured_cyphers), session.captured_cyphers
