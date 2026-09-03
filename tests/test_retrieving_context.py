"""retrieving_context 内核 mock 单元测试（离线）。"""
import json

import pytest
from sda_mcp.errors import DataSourceError, ExternalAPIError, ValidationError
from sda_mcp.skills import retrieving_context as r

GC = {
    "embedding": {"model": "BAAI/bge-small-zh-v1.5", "dimensions": 512},
    "entities": {"指标": {"key_field": "指标ID", "table_id": "tbl1"},
                 "表": {"key_field": "表ID", "table_id": "tbl2"}},
    "relationships": [{"type": "属于", "from": "指标", "to": "表"}],
}


def test_clean_properties_strips_internal():
    out = r._clean_properties({"name": "GMV", "embedding": [1, 2], "search_text": "x"})
    assert out == {"name": "GMV"}


def test_build_live_schema_is_compact_and_filters_stale_metadata():
    out = r._build_live_schema(
        [
            {"nodeLabels": ["指标"], "propertyName": "指标ID", "propertyTypes": ["STRING"]},
            {"nodeLabels": ["指标"], "propertyName": "指标名称", "propertyTypes": ["STRING"]},
            {"nodeLabels": ["指标"], "propertyName": "embedding", "propertyTypes": ["LIST<FLOAT>"]},
            {"nodeLabels": ["表"], "propertyName": "表名称", "propertyTypes": ["STRING"]},
        ],
        [
            {"type": "NODE_PROPERTY_UNIQUENESS", "labelsOrTypes": ["指标"], "properties": ["指标ID"]},
            {"type": "NODE_PROPERTY_UNIQUENESS", "labelsOrTypes": ["Movie"], "properties": ["title"]},
        ],
        [
            {"sourceLabel": "指标", "relationshipType": "使用", "targetLabel": "表"},
            {"sourceLabel": "指标", "relationshipType": "使用", "targetLabel": "表"},
        ],
    )

    assert out == {
        "nodes": {
            "指标": {
                "properties": {"指标ID": "STRING", "指标名称": "STRING"},
                "unique": ["指标ID"],
            },
            "表": {"properties": {"表名称": "STRING"}},
        },
        "relationships": ["(:`指标`)-[:`使用`]->(:`表`)"],
    }


def test_schema_reads_neo4j_only_and_closes_client(monkeypatch):
    class FakeClient:
        closed = False

        def _supports_vector_search_clause(self):
            return True

        def run_cypher(self, statement):
            if "nodeTypeProperties" in statement:
                return [{
                    "nodeLabels": ["指标"],
                    "propertyName": "指标ID",
                    "propertyTypes": ["STRING"],
                }]
            if statement.startswith("SHOW CONSTRAINTS"):
                return [{
                    "type": "NODE_PROPERTY_UNIQUENESS",
                    "labelsOrTypes": ["指标"],
                    "properties": ["指标ID"],
                }]
            return []

        def close(self):
            self.closed = True

    client = FakeClient()
    monkeypatch.setattr(r, "Neo4jClient", lambda: client)
    out = r.schema()

    assert out["nodes"]["指标"]["unique"] == ["指标ID"]
    assert client.closed is True


def test_schema_empty_graph_gives_actionable_error(monkeypatch):
    class EmptyClient:
        def _supports_vector_search_clause(self):
            return True

        def run_cypher(self, statement):
            return []

        def close(self):
            pass

    monkeypatch.setattr(r, "Neo4jClient", EmptyClient)
    with pytest.raises(DataSourceError, match="先执行 sync"):
        r.schema()


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
        def fetch_graph_context_batch(self, hits, rels, entities):
            return {h["id"]: {} for h in hits}
    monkeypatch.setattr(r, "Neo4jClient", FakeClient)
    out = r.search("GMV", top_k=5, strategy="vector")
    assert out["results"][0]["score"] == 0.9
    assert out["results"][0]["properties"] == {"name": "A"}
    assert not hasattr(out, "ok")


def test_search_rejects_unknown_strategy(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC})
    with pytest.raises(ValidationError, match="strategy"):
        r.search("GMV", strategy="magic")


def test_search_rejects_unknown_context_mode(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC})
    with pytest.raises(ValidationError, match="context_mode"):
        r.search("GMV", context_mode="full")


def test_search_context_none_skips_graph_expansion(monkeypatch):
    monkeypatch.setattr(
        r, "load_config",
        lambda: {"graph-config": GC, "env": {"NEO4J_PASSWORD": "p"}},
    )
    monkeypatch.setattr(r, "embed", lambda text: [0.1] * 512)
    context_calls = []

    class FakeClient:
        def __init__(self): pass
        def close(self): pass
        def find_vector_index_name(self, label): return "idx" if label == "指标" else None
        def search_vector_index(self, idx, label, emb, top_k):
            return [{"id": "a", "score": 0.9, "properties": {"name": "A"}}]
        def fetch_graph_context_batch(self, hits, rels, entities):
            context_calls.append((hits, rels, entities))
            return {hit["id"]: {"表": {"items": [], "total": 0, "truncated": False}}
                    for hit in hits}

    monkeypatch.setattr(r, "Neo4jClient", FakeClient)
    out = r.search("GMV", strategy="vector", context_mode="none")

    assert context_calls == []
    assert all(item["context"] == {} for item in out["results"])
    assert out["context_bytes"] == 0


def test_search_reports_context_bytes(monkeypatch):
    monkeypatch.setattr(
        r, "load_config",
        lambda: {"graph-config": GC, "env": {"NEO4J_PASSWORD": "p"}},
    )
    monkeypatch.setattr(r, "embed", lambda text: [0.1] * 512)
    contexts = {"a": {"表": {"items": [{"表名称": "t"}], "total": 1, "truncated": False}}}

    class FakeClient:
        def __init__(self): pass
        def close(self): pass
        def find_vector_index_name(self, label): return "idx" if label == "指标" else None
        def search_vector_index(self, idx, label, emb, top_k):
            return [{"id": "a", "score": 0.9, "properties": {"name": "A"}}]
        def fetch_graph_context_batch(self, hits, rels, entities):
            return contexts

    monkeypatch.setattr(r, "Neo4jClient", FakeClient)
    out = r.search("GMV", strategy="vector")
    assert out["context_bytes"] == len(
        json.dumps(contexts, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )


def test_search_empty_question(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC, "env": {"NEO4J_PASSWORD": "p"}})
    with pytest.raises(ValidationError):
        r.search("   ")


def test_cypher_empty():
    with pytest.raises(ValidationError):
        r.cypher("  ")


def test_doc_returns_raw_content(monkeypatch):
    monkeypatch.setattr(
        r.FeishuClient, "get_raw_content",
        lambda self, tok: "指标口径说明\nselect * from orders",
    )
    out = r.doc("DOCTOKEN")
    assert out == {
        "document_id": "DOCTOKEN",
        "content": "指标口径说明\nselect * from orders",
    }


def test_doc_empty_id_raises():
    with pytest.raises(ValidationError):
        r.doc("")


def test_doc_client_error_propagates(monkeypatch):
    def _boom(self, tok):
        raise ExternalAPIError("飞书 API GET /raw_content 失败: 403")

    monkeypatch.setattr(r.FeishuClient, "get_raw_content", _boom)
    with pytest.raises(ExternalAPIError):
        r.doc("DOCTOKEN")


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


def test_batch_context_self_loop_is_undirected(monkeypatch):
    """from == to == label：自环走无向 -[:T]-。"""
    client, session = _make_client(monkeypatch)
    rels = [{"type": "关联", "from": "指标", "to": "指标"}]
    client.fetch_graph_context_batch(
        [{"id": "node-1", "label": "指标"}], rels, GC["entities"],
    )
    assert any("-[:`关联`]-" in c for c in session.captured_cyphers), session.captured_cyphers


def test_batch_context_outgoing_is_directed(monkeypatch):
    """from == label 且 to != label：出边走 -[:T]->。"""
    client, session = _make_client(monkeypatch)
    rels = [{"type": "属于", "from": "指标", "to": "表"}]
    client.fetch_graph_context_batch(
        [{"id": "node-1", "label": "指标"}], rels, GC["entities"],
    )
    assert any("-[:`属于`]->" in c for c in session.captured_cyphers), session.captured_cyphers
    assert any("ORDER BY other.`表ID`" in c for c in session.captured_cyphers)


class _SearchSession(_FakeSession):
    def run(self, cypher, **kwargs):
        self.captured_cyphers.append(cypher)
        self.kwargs = kwargs
        return iter([])


def test_vector_search_uses_search_clause_on_neo4j_2026(monkeypatch):
    client = r.Neo4jClient.__new__(r.Neo4jClient)
    session = _SearchSession()
    monkeypatch.setattr(client, "_session", lambda: session)
    monkeypatch.setattr(client, "_supports_vector_search_clause", lambda: True)

    client.search_vector_index("指标`索引", "指标", [0.1, 0.2], 3)

    query = session.captured_cyphers[0]
    assert query.startswith("CYPHER 25 MATCH")
    assert "SEARCH node IN" in query
    assert "VECTOR INDEX `指标``索引`" in query
    assert "db.index.vector.queryNodes" not in query
    assert session.kwargs == {"topK": 3, "embedding": [0.1, 0.2]}


def test_vector_search_falls_back_for_older_neo4j(monkeypatch):
    client = r.Neo4jClient.__new__(r.Neo4jClient)
    session = _SearchSession()
    monkeypatch.setattr(client, "_session", lambda: session)
    monkeypatch.setattr(client, "_supports_vector_search_clause", lambda: False)

    client.search_vector_index("metric_index", "指标", [0.1], 5)

    query = session.captured_cyphers[0]
    assert "db.index.vector.queryNodes" in query
    assert "SEARCH node IN" not in query
    assert session.kwargs == {"indexName": "metric_index", "topK": 5, "embedding": [0.1]}


def test_lucene_query_escapes_parser_operators():
    assert r._escape_lucene_query('NPS: "推荐" +样本') == 'NPS\\: \\"推荐\\" \\+样本'


def test_rrf_rewards_items_found_by_both_sources():
    vector = [
        {"id": "v", "score": 0.9, "properties": {"指标ID": "v"}},
        {"id": "both", "score": 0.8, "properties": {"指标ID": "both"}},
    ]
    lexical = [
        {"id": "both", "score": 2.0, "properties": {"指标ID": "both"}},
        {"id": "l", "score": 1.0, "properties": {"指标ID": "l"}},
    ]
    fused = r._fuse_ranked_sources([
        ("vector", "指标", 1.0, vector),
        ("fulltext", "指标", 1.0, lexical),
    ])
    assert fused[0]["id"] == "both"
    assert fused[0]["vector_rank"] == 2
    assert fused[0]["lexical_rank"] == 1


def test_exact_property_hits_boosts_name_but_not_definition_mentions():
    hits = [
        {"id": "rate", "score": 0.9, "properties": {
            "指标名称": "复购率", "指标定义": "复购人数除以总承接人数",
        }},
        {"id": "users", "score": 0.8, "properties": {
            "指标名称": "复购人数", "指标定义": "复购下一正式营的人数",
        }},
    ]
    exact = r._exact_property_hits("复购人数是什么", hits)
    assert [item["id"] for item in exact] == ["users"]
    assert exact[0]["exact_match"] == "复购人数"


def test_exact_property_hits_ignores_generic_type_values():
    hits = [{"id": "table", "score": 0.8, "properties": {
        "表名称": "semantic.fact_order", "表类型": "事实表",
    }}]
    assert r._exact_property_hits("需要哪张事实表", hits) == []


def test_fulltext_search_uses_escaped_question(monkeypatch):
    client, session = _make_client(monkeypatch)
    client.search_fulltext_index("指标_search_text_index", "指标", "NPS:推荐", 5)
    assert "db.index.fulltext.queryNodes" in session.captured_cyphers[0]


def test_batch_context_groups_ids_by_relationship(monkeypatch):
    client, session = _make_client(monkeypatch)
    hits = [{"id": "m1", "label": "指标"}, {"id": "m2", "label": "指标"}]
    client.fetch_graph_context_batch(
        hits, [{"type": "使用", "from": "指标", "to": "表"}],
        GC["entities"],
    )
    assert len(session.captured_cyphers) == 1
    assert "elementId(n) IN $nodeIds" in session.captured_cyphers[0]


class _RecordSession(_FakeSession):
    """返回预置记录，用于验证 context 桶的截断标记。"""

    def __init__(self, records):
        super().__init__()
        self.records = records

    def run(self, cypher, **kwargs):
        super().run(cypher, **kwargs)
        return iter(self.records)


def _make_record_client(monkeypatch, records):
    client = r.Neo4jClient.__new__(r.Neo4jClient)
    client._database = "neo4j"
    session = _RecordSession(records)
    monkeypatch.setattr(client, "_session", lambda: session)
    return client


def test_batch_context_over_threshold_omits_items(monkeypatch):
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(11)]
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        GC["entities"],
    )
    bucket = ctx["m1"]["表"]
    assert bucket == {
        "items": [],
        "total": 11,
        "truncated": True,
        "omitted_reason": "high_cardinality",
    }


def test_batch_context_at_threshold_returns_all(monkeypatch):
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(10)]
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        GC["entities"],
    )
    assert ctx["m1"]["表"] == {
        "items": [{"表名称": f"t{i}"} for i in range(10)],
        "total": 10,
        "truncated": False,
    }


def test_batch_context_under_limit_not_truncated(monkeypatch):
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(3)]
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        GC["entities"],
    )
    assert ctx["m1"]["表"] == {
        "items": [{"表名称": "t0"}, {"表名称": "t1"}, {"表名称": "t2"}],
        "total": 3,
        "truncated": False,
    }


def test_item_bytes_is_deterministic_across_key_order():
    assert r._item_bytes({"表名称": "t", "表ID": "x"}) == r._item_bytes({"表ID": "x", "表名称": "t"})


def test_batch_context_over_byte_budget_omits_items(monkeypatch):
    """数量未超阈值但序列化字节超预算：整桶丢弃并标注 byte_budget。"""
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(3)]
    monkeypatch.setattr(r, "CONTEXT_BUCKET_BYTE_BUDGET", 1)
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        GC["entities"],
    )
    assert ctx["m1"]["表"] == {
        "items": [],
        "total": 3,
        "truncated": True,
        "omitted_reason": "byte_budget",
    }


def test_batch_context_at_byte_budget_keeps_items(monkeypatch):
    """字节预算边界含等号：累计恰好等于预算时整桶保留。"""
    items = [{"表名称": "t0"}, {"表名称": "t1"}]
    records = [{"nodeId": "m1", "props": item} for item in items]
    monkeypatch.setattr(
        r, "CONTEXT_BUCKET_BYTE_BUDGET", sum(r._item_bytes(item) for item in items)
    )
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        GC["entities"],
    )
    assert ctx["m1"]["表"] == {"items": items, "total": 2, "truncated": False}


def test_batch_context_count_gate_takes_precedence_over_byte(monkeypatch):
    """数量与字节双超限时计数门优先：omitted_reason 报 high_cardinality。"""
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(11)]
    monkeypatch.setattr(r, "CONTEXT_BUCKET_BYTE_BUDGET", 1)
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
        GC["entities"],
    )
    assert ctx["m1"]["表"] == {
        "items": [],
        "total": 11,
        "truncated": True,
        "omitted_reason": "high_cardinality",
    }
