"""retrieving_context 内核 mock 单元测试（离线）。"""
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
        def fetch_graph_context_batch(self, hits, rels): return {h["id"]: {} for h in hits}
    monkeypatch.setattr(r, "Neo4jClient", FakeClient)
    out = r.search("GMV", top_k=5, strategy="vector")
    assert out["results"][0]["score"] == 0.9
    assert out["results"][0]["properties"] == {"name": "A"}
    assert not hasattr(out, "ok")


def test_search_rejects_unknown_strategy(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC})
    with pytest.raises(ValidationError, match="strategy"):
        r.search("GMV", strategy="magic")


def test_search_empty_question(monkeypatch):
    monkeypatch.setattr(r, "load_config", lambda: {"graph-config": GC, "env": {"NEO4J_PASSWORD": "p"}})
    with pytest.raises(ValidationError):
        r.search("   ")


def test_cypher_empty():
    with pytest.raises(ValidationError):
        r.cypher("  ")


def test_doc_returns_compact_consistent_structured_blocks(monkeypatch):
    metadata_calls = []

    def _metadata(self, tok):
        metadata_calls.append(tok)
        return {"document_id": tok, "title": "标题", "revision_id": 7}

    monkeypatch.setattr(r.FeishuClient, "get_document", _metadata)
    captured = []

    def _list(self, tok, document_revision_id=None):
        captured.append(document_revision_id)
        return [
            {"block_id": tok, "block_type": 1, "page": {}, "children": ["C1"]},
            {"block_id": "C1", "parent_id": tok, "block_type": 14,
             "code": {"elements": [{"text_run": {"content": "select * from t"}}],
                      "style": {"language": 56}}},
        ]

    monkeypatch.setattr(r.FeishuClient, "list_blocks", _list)
    out = r.doc("DOCTOKEN")
    assert captured == [-1]
    assert metadata_calls == ["DOCTOKEN", "DOCTOKEN"]
    assert out["revision_id"] == 7
    assert out["detail"] == "compact"
    assert out["title"] == "标题"
    assert out["root_block_id"] == "DOCTOKEN"
    assert out["blocks"][1]["type"] == "code"
    assert out["blocks"][1]["text"] == "select * from t"
    assert out["blocks"][1]["content"] == {"style": {"language": 56}}
    assert "elements" not in out["blocks"][1]
    assert out["document_id"] == "DOCTOKEN"


def test_doc_full_returns_content_elements_without_top_level_duplicate(monkeypatch):
    monkeypatch.setattr(
        r.FeishuClient,
        "get_document",
        lambda self, tok: {"document_id": tok, "title": "标题", "revision_id": 7},
    )
    monkeypatch.setattr(
        r.FeishuClient,
        "list_blocks",
        lambda self, tok, document_revision_id=None: [
            {"block_id": tok, "block_type": 1, "page": {}, "children": ["C1"]},
            {"block_id": "C1", "parent_id": tok, "block_type": 14,
             "code": {"elements": [{"text_run": {"content": "select 1"}}],
                      "style": {"language": 56}}},
        ],
    )
    out = r.doc("DOCTOKEN", detail="full")
    code = out["blocks"][1]
    assert out["detail"] == "full"
    assert code["content"]["elements"][0]["text_run"]["content"] == "select 1"
    assert "elements" not in code


def test_doc_retries_when_revision_changes_during_latest_block_read(monkeypatch):
    revisions = iter([7, 8, 8, 8])
    monkeypatch.setattr(
        r.FeishuClient,
        "get_document",
        lambda self, tok: {"document_id": tok, "title": "标题", "revision_id": next(revisions)},
    )
    calls = []

    def _list(self, tok, document_revision_id=None):
        calls.append(document_revision_id)
        return [{"block_id": tok, "block_type": 1, "page": {}, "children": []}]

    monkeypatch.setattr(r.FeishuClient, "list_blocks", _list)
    out = r.doc("DOCTOKEN")
    assert calls == [-1, -1]
    assert out["revision_id"] == 8
    assert any("重试" in warning for warning in out["warnings"])


def test_doc_fails_when_revision_never_stabilizes(monkeypatch):
    revisions = iter([1, 2, 2, 3, 3, 4])
    monkeypatch.setattr(
        r.FeishuClient,
        "get_document",
        lambda self, tok: {"document_id": tok, "title": "标题", "revision_id": next(revisions)},
    )
    monkeypatch.setattr(
        r.FeishuClient,
        "list_blocks",
        lambda self, tok, document_revision_id=None: [
            {"block_id": tok, "block_type": 1, "page": {}, "children": []},
        ],
    )
    with pytest.raises(ExternalAPIError, match="持续发生变化"):
        r.doc("DOCTOKEN")


def test_doc_empty_id_raises():
    with pytest.raises(ValidationError):
        r.doc("")


def test_doc_invalid_detail_raises():
    with pytest.raises(ValidationError, match="detail"):
        r.doc("DOC", detail="verbose")


def test_update_doc_batches_text_operations_at_expected_revision(monkeypatch):
    captured = {}
    metadata_calls = []

    def _metadata(self, did):
        metadata_calls.append(did)
        return {"document_id": did, "revision_id": 7}

    monkeypatch.setattr(
        r.FeishuClient, "get_document", _metadata,
    )

    def _list(self, did, document_revision_id=None):
        captured["list_revision"] = document_revision_id
        return [
            {"block_id": did, "block_type": 1, "children": ["T1", "C1"]},
            {"block_id": "T1", "block_type": 2, "parent_id": did, "text": {}},
            {"block_id": "C1", "block_type": 14, "parent_id": did, "code": {}},
        ]

    monkeypatch.setattr(
        r.FeishuClient,
        "list_blocks",
        _list,
    )

    def _update(self, did, revision, requests):
        captured.update(doc=did, revision=revision, requests=requests)
        return {"code": 0, "data": {"document_revision_id": 8, "blocks": []}}

    monkeypatch.setattr(r.FeishuClient, "batch_update_blocks", _update)
    out = r.update_doc("DOC", 7, [
        {"op": "replace_text", "block_id": "C1", "text": "select * from t"},
        {"op": "replace_elements", "block_id": "T1", "elements": [
            {"text_run": {"content": "粗体", "text_element_style": {"bold": True}}},
        ]},
    ])
    assert captured["revision"] == 7
    assert captured["list_revision"] == -1
    assert metadata_calls == ["DOC", "DOC"]
    assert captured["requests"][0]["update_text_elements"]["elements"][0]["text_run"]["content"] == "select * from t"
    assert out["previous_revision_id"] == 7
    assert out["revision_id"] == 8
    assert out["affected_block_ids"] == ["C1", "T1"]


def test_update_doc_insert_subtree_uses_single_descendant_request(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        r.FeishuClient, "get_document",
        lambda self, did: {"document_id": did, "revision_id": 8},
    )
    monkeypatch.setattr(
        r.FeishuClient,
        "list_blocks",
        lambda self, did, document_revision_id=None: [
            {"block_id": did, "block_type": 1, "children": []},
        ],
    )

    def _insert(self, did, blocks, root_ids, **kwargs):
        captured.update(doc=did, blocks=blocks, root_ids=root_ids, kwargs=kwargs)
        return {"code": 0, "data": {
            "document_revision_id": 9,
            "block_id_relations": [
                {"temporary_block_id": "b1", "block_id": "REAL1"},
                {"temporary_block_id": "b2", "block_id": "REAL2"},
            ],
        }}

    monkeypatch.setattr(r.FeishuClient, "insert_descendants", _insert)
    out = r.update_doc("DOC", 8, [{
        "op": "insert_subtree", "parent_block_id": "DOC", "index": 0,
        "root_ids": ["b1"],
        "blocks": [
            {"local_id": "b1", "type": "bullet", "text": "父项", "children": ["b2"]},
            {"local_id": "b2", "type": "bullet", "text": "子项", "children": []},
        ],
    }])
    assert captured["root_ids"] == ["b1"]
    assert captured["blocks"][0]["children"] == ["b2"]
    assert captured["kwargs"] == {
        "parent_block_id": "DOC", "revision_id": 8, "index": 0,
    }
    assert out["affected_block_ids"] == ["REAL1", "REAL2"]


def test_update_doc_delete_children_validates_range(monkeypatch):
    monkeypatch.setattr(
        r.FeishuClient, "get_document",
        lambda self, did: {"document_id": did, "revision_id": 9},
    )
    monkeypatch.setattr(
        r.FeishuClient,
        "list_blocks",
        lambda self, did, document_revision_id=None: [
            {"block_id": did, "block_type": 1, "children": ["A", "B"]},
            {"block_id": "A", "block_type": 2, "parent_id": did},
            {"block_id": "B", "block_type": 2, "parent_id": did},
        ],
    )
    monkeypatch.setattr(
        r.FeishuClient,
        "delete_children",
        lambda self, did, parent, revision, start, end: {
            "code": 0, "data": {"document_revision_id": 10}},
    )
    out = r.update_doc("DOC", 9, [{
        "op": "delete_children", "parent_block_id": "DOC",
        "start_index": 1, "end_index": 2,
    }])
    assert out["affected_block_ids"] == ["B"]


def test_update_doc_empty_operations_raises():
    with pytest.raises(ValidationError):
        r.update_doc("DOC", 1, [])


def test_update_doc_rejects_stale_revision_before_listing_blocks(monkeypatch):
    calls = []
    monkeypatch.setattr(
        r.FeishuClient, "get_document",
        lambda self, did: {"document_id": did, "revision_id": 12},
    )
    monkeypatch.setattr(
        r.FeishuClient, "list_blocks",
        lambda *args, **kwargs: calls.append("listed"),
    )
    with pytest.raises(ValidationError, match="revision 冲突"):
        r.update_doc("DOC", 11, [{
            "op": "replace_text", "block_id": "B", "text": "x",
        }])
    assert calls == []


def test_update_doc_rejects_duplicate_block_in_batch(monkeypatch):
    monkeypatch.setattr(
        r.FeishuClient, "get_document",
        lambda self, did: {"document_id": did, "revision_id": 3},
    )
    monkeypatch.setattr(
        r.FeishuClient, "list_blocks",
        lambda self, did, document_revision_id=None: [
            {"block_id": did, "block_type": 1, "children": ["B"]},
            {"block_id": "B", "block_type": 2, "text": {}},
        ],
    )
    with pytest.raises(ValidationError, match="重复更新"):
        r.update_doc("DOC", 3, [
            {"op": "replace_text", "block_id": "B", "text": "a"},
            {"op": "replace_text", "block_id": "B", "text": "b"},
        ])


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
    client.fetch_graph_context_batch([{"id": "node-1", "label": "指标"}], rels)
    assert any("-[:`关联`]-" in c for c in session.captured_cyphers), session.captured_cyphers


def test_batch_context_outgoing_is_directed(monkeypatch):
    """from == label 且 to != label：出边走 -[:T]->。"""
    client, session = _make_client(monkeypatch)
    rels = [{"type": "属于", "from": "指标", "to": "表"}]
    client.fetch_graph_context_batch([{"id": "node-1", "label": "指标"}], rels)
    assert any("-[:`属于`]->" in c for c in session.captured_cyphers), session.captured_cyphers


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


def test_batch_context_marks_truncation_over_limit(monkeypatch):
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(25)]
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
    )
    bucket = ctx["m1"]["表"]
    assert bucket["total"] == 25
    assert len(bucket["items"]) == r.CONTEXT_NEIGHBOR_LIMIT
    assert bucket["truncated"] is True


def test_batch_context_under_limit_not_truncated(monkeypatch):
    records = [{"nodeId": "m1", "props": {"表名称": f"t{i}"}} for i in range(3)]
    client = _make_record_client(monkeypatch, records)
    ctx = client.fetch_graph_context_batch(
        [{"id": "m1", "label": "指标"}],
        [{"type": "使用", "from": "指标", "to": "表"}],
    )
    assert ctx["m1"]["表"] == {
        "items": [{"表名称": "t0"}, {"表名称": "t1"}, {"表名称": "t2"}],
        "total": 3,
        "truncated": False,
    }
