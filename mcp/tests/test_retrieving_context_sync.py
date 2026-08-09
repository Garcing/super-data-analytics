"""retrieving_context_sync mock 单元测试（离线，不依赖真实 lark-cli/Neo4j/fastembed 模型）。"""
import json
import pytest
from sda_mcp.errors import ConfigError, ValidationError
from sda_mcp.skills import retrieving_context_sync as s

GC = {
    "embedding": {"model": "BAAI/bge-small-zh-v1.5", "dimensions": 512},
    "entities": {"指标": {"key_field": "指标ID", "table_id": "tbl1", "vector_index": True},
                 "表": {"key_field": "表ID", "table_id": "tbl2", "vector_index": False}},
    "relationships": [{"type": "属于", "from": "指标", "to": "表",
                       "match": {"source_field": "表", "target_field": "表ID"}}],
}


# ---------- Phase 1: fetch 解析 ----------

def test_fetch_extracts_records(monkeypatch):
    """mock _lark_cli 返回 field-list + record-list → 解析正确（select 取值、分页停止）。"""
    field_payload = {"data": {"fields": [
        {"name": "名称", "type": "text", "id": "f1"},
        {"name": "状态", "type": "select", "id": "f2"},
        {"name": "自增", "type": "auto_number", "id": "f3"},  # 应被过滤
    ]}}
    # 单页 has_more=False → 停止分页
    page1 = {"data": {"data": [["A", ["active"]], ["B", ["pending"]]],
                      "fields": ["名称", "状态"], "has_more": False}}
    outputs = [field_payload, page1]
    monkeypatch.setattr(s, "_lark_cli", lambda *a: outputs.pop(0))

    recs = s.fetch_table_records("APP", "tbl1")
    assert len(recs) == 2
    assert recs[0]["名称"] == "A"
    # select 单值取 cell[0]
    assert recs[0]["状态"] == "active"
    assert recs[1]["状态"] == "pending"
    # auto_number 字段不在结果里
    assert "自增" not in recs[0]


def test_fetch_paginates_until_has_more_false(monkeypatch):
    """满页(200) + has_more=True → 继续翻页；下一页短 → 停止。"""
    field_payload = {"data": {"fields": [{"name": "名称", "type": "text", "id": "f1"}]}}
    page1_rows = [["r%d" % i] for i in range(200)]  # 满页 → 触发翻页
    page1 = {"data": {"data": page1_rows, "fields": ["名称"], "has_more": True}}
    page2 = {"data": {"data": [["last"]], "fields": ["名称"], "has_more": False}}
    outputs = [field_payload, page1, page2]
    calls = []
    monkeypatch.setattr(s, "_lark_cli", lambda *a: (calls.append(a) or outputs.pop(0)))
    recs = s.fetch_table_records("APP", "tbl1")
    assert len(recs) == 201
    assert recs[-1]["名称"] == "last"
    assert len(calls) == 3  # field-list + 2 页 record-list


# ---------- 编排 ----------

class _FakeClient:
    """绕过 Neo4j __init__（避免真实 driver）。"""
    def __init__(self, *a, **k):
        self.closed = False
    def close(self):
        self.closed = True


def _stub_phases(monkeypatch, calls):
    """把六个内部阶段替换成记录调用的计数 stub。"""
    monkeypatch.setattr(s, "_fetch_all_feishu", lambda gc: (calls.append("fetch") or {"指标": [{"a": 1}]}))
    monkeypatch.setattr(s, "_clear_graph", lambda c: calls.append("clear"))
    monkeypatch.setattr(s, "_build_nodes", lambda c, e, d: (calls.append("nodes") or {"指标": 1}))
    monkeypatch.setattr(s, "_build_relationships", lambda c, r, e, d: (calls.append("rels") or {"x": 2}))
    monkeypatch.setattr(s, "_generate_search_text", lambda c, e: (calls.append("st") or {"指标": 1}))
    monkeypatch.setattr(s, "_create_vector_indexes", lambda c, e, dim: (calls.append("idx") or ["i0"]))
    monkeypatch.setattr(s, "_embed_nodes", lambda c, e, dim, f: (calls.append("embed") or {"指标": 1}))


def test_sync_graph_orchestration(monkeypatch):
    """全跑：fetch→clear→nodes→rels→st→idx→embed 都执行，返回各阶段计数。"""
    monkeypatch.setattr(s, "load_config", lambda: {"graph-config": GC})
    calls = []
    _stub_phases(monkeypatch, calls)
    monkeypatch.setattr(s, "Neo4jClient", _FakeClient)
    out = s.sync_graph()
    assert out["fetch"] == {"指标": 1}
    assert out["nodes"] == {"指标": 1}
    assert out["relationships"] == {"x": 2}
    assert out["search_text"] == {"指标": 1}
    assert out["indexes"] == 1
    assert out["embed"] == {"指标": 1}
    assert calls == ["fetch", "clear", "nodes", "rels", "st", "idx", "embed"]


def test_sync_graph_only_embed_skips_build(monkeypatch):
    """only='embed'：不 fetch、不 build，只跑 embed 三步。"""
    monkeypatch.setattr(s, "load_config", lambda: {"graph-config": GC})
    calls = []
    _stub_phases(monkeypatch, calls)
    monkeypatch.setattr(s, "Neo4jClient", _FakeClient)
    out = s.sync_graph(only="embed")
    assert "fetch" not in out
    assert "nodes" not in out
    assert "relationships" not in out
    assert out["search_text"] == {"指标": 1}
    assert out["embed"] == {"指标": 1}
    assert calls == ["st", "idx", "embed"]


def test_sync_dry_run_no_write(monkeypatch):
    """dry_run=True：只 fetch 预览，不构造 Neo4jClient、不写库。"""
    monkeypatch.setattr(s, "load_config", lambda: {"graph-config": GC})
    constructed = []
    monkeypatch.setattr(s, "Neo4jClient", lambda *a, **k: constructed.append(1) or _FakeClient())
    monkeypatch.setattr(s, "_fetch_all_feishu", lambda gc: {"指标": [{"a": 1}], "表": []})
    out = s.sync_graph(dry_run=True)
    assert out == {"fetch": {"指标": 1, "表": 0}}
    assert constructed == []  # 没构造 client


def test_sync_bad_only_raises():
    with pytest.raises(ValidationError):
        s.sync_graph(only="bogus")


def test_sync_missing_entities_raises(monkeypatch):
    monkeypatch.setattr(s, "load_config", lambda: {"graph-config": {}})
    with pytest.raises(ConfigError):
        s.sync_graph()


# ---------- Phase 3: embed 用 fastembed 批量 + 写回字段齐全 ----------

class _EmbedFakeClient:
    """记录 execute() 的 SET 语句；run_cypher 返回待 embed 节点。"""
    def __init__(self):
        self.executed = []  # (cypher, params)
    def close(self):
        pass
    def run_cypher(self, statement):
        if "RETURN elementId(n)" in statement:
            return [{"id": "id-1", "text": "指标名：GMV。"}, {"id": "id-2", "text": "指标名：DAU。"}]
        return []
    def execute(self, cypher, **params):
        self.executed.append((cypher, params))


def test_embed_uses_fastembed_batch(monkeypatch):
    """mock TextEmbedding → 断言批量 embed 被调用、写回字段齐（embedding/model/dims/updated_at）。"""
    monkeypatch.setattr(s, "load_config", lambda: {"graph-config": GC})
    embed_calls = []

    class _FE:
        def __init__(self, model_name=None):
            self.model_name = model_name
        def embed(self, texts):
            embed_calls.append(list(texts))
            return [[0.1, 0.2, 0.3] for _ in texts]

    import fastembed
    monkeypatch.setattr(fastembed, "TextEmbedding", _FE)

    client = _EmbedFakeClient()
    counts = s._embed_nodes(client, GC["entities"], dimensions=512, force=False)

    # vector_index=False 的 "表" 被跳过，只有 "指标" 两个节点
    assert counts == {"指标": 2}
    # 批量一次性传入两条文本
    assert embed_calls == [["指标名：GMV。", "指标名：DAU。"]]
    # 写回语句数 == 节点数
    set_stmts = [c for c, _ in client.executed if "SET n.embedding" in c]
    assert len(set_stmts) == 2
    # 写回字段齐全
    _, params = client.executed[0]
    assert "emb" in params and "model" in params and "dims" in params and "now" in params
    assert params["model"] == "BAAI/bge-small-zh-v1.5"
    assert params["dims"] == 512
    assert params["emb"] == [0.1, 0.2, 0.3]
