"""retrieving_context_sync mock 单元测试（离线，不依赖真实飞书/Neo4j/fastembed 模型）。"""
import pytest
from sda_mcp.errors import ConfigError, ValidationError
from sda_mcp.feishu import (_F_TEXT, _F_NUMBER, _F_SINGLE_SELECT, _F_MULTI_SELECT,
                            _F_DATE, _F_CHECKBOX, _F_USER, _F_PHONE, _F_URL,
                            _F_ATTACHMENT, _F_SINGLE_LINK, _F_LOOKUP, _F_FORMULA,
                            _F_DUPLEX_LINK, _F_LOCATION, _F_GROUP_CHAT,
                            _F_CREATED_TIME, _F_MODIFIED_TIME, _F_CREATED_USER,
                            _F_MODIFIED_USER, _F_AUTO_NUMBER)
from sda_mcp.skills import retrieving_context_sync as s

GC = {
    "embedding": {"model": "BAAI/bge-small-zh-v1.5", "dimensions": 512},
    "entities": {"指标": {"key_field": "指标ID", "table_id": "tbl1", "vector_index": True},
                 "表": {"key_field": "表ID", "table_id": "tbl2", "vector_index": False}},
    "relationships": [{"type": "属于", "from": "指标", "to": "表",
                       "match": {"source_field": "表", "target_field": "表ID"}}],
}


# ---------- Phase 1: fetch 解析（开放平台 FeishuClient）----------

def test_fetch_fields_descriptor_shape_keeps_auto_number(monkeypatch):
    """开放平台 raw fields → 描述符；auto_number 不再过滤；提取 options 与公式结果 data_type。"""
    monkeypatch.setattr(s.FeishuClient, "list_bitable_fields",
                        lambda self, app, tbl: [
                            {"field_id": "fid1", "field_name": "名称", "type": _F_TEXT, "ui_type": "Text"},
                            {"field_id": "fid2", "field_name": "自增", "type": _F_AUTO_NUMBER, "ui_type": "AutoNumber"},
                            {"field_id": "fid3", "field_name": "状态", "type": _F_SINGLE_SELECT,
                             "ui_type": "SingleSelect",
                             "property": {"options": [{"id": "o1", "name": "待处理"}]}},
                            {"field_id": "fid4", "field_name": "公式_日期", "type": _F_FORMULA,
                             "ui_type": "Formula",
                             "property": {"type": {"data_type": _F_DATE, "ui_type": "DateTime"}}},
                        ])
    fields = s.fetch_table_fields("APP", "tbl1")
    assert [f["name"] for f in fields] == ["名称", "自增", "状态", "公式_日期"]   # auto_number 保留
    assert fields[1]["type"] == _F_AUTO_NUMBER
    assert fields[2]["options"] == [{"id": "o1", "name": "待处理"}]
    assert fields[3]["formula_data_type"] == _F_DATE


def test_fetch_records_simplifies_values(monkeypatch):
    """text→拼字符串、单选→字符串、多选→list；空/None 过滤。"""
    monkeypatch.setattr(s.FeishuClient, "list_bitable_fields",
                        lambda self, app, tbl: [
                            {"field_id": "f1", "field_name": "名称", "type": _F_TEXT},
                            {"field_id": "f2", "field_name": "状态", "type": _F_SINGLE_SELECT},
                            {"field_id": "f3", "field_name": "标签", "type": _F_MULTI_SELECT},
                        ])
    monkeypatch.setattr(s.FeishuClient, "list_bitable_records",
                        lambda self, app, tbl: [
                            {"record_id": "r1", "fields": {
                                "名称": [{"text": "A"}],
                                "状态": "active",                       # 字符串形式
                                "标签": ["x", "y"]}},                   # 多选 list
                            {"record_id": "r2", "fields": {
                                "名称": [{"text": "B"}],
                                "状态": {"text": "pending"},            # 对象形式
                                "标签": [{"text": "z"}]}},              # 多选对象 list
                        ])
    recs = s.fetch_table_records("APP", "tbl1")
    assert len(recs) == 2
    assert recs[0]["名称"] == "A"
    assert recs[0]["状态"] == "active"
    assert recs[0]["标签"] == ["x", "y"]
    assert recs[1]["状态"] == "pending"          # 对象 → 取 text
    assert recs[1]["标签"] == ["z"]


def test_fetch_records_formula_and_lookup_join_text(monkeypatch):
    """公式(20)/查找引用(19) 文本结果 [{text,type}] → 拼成纯字符串（对齐 lark-cli）。
    关键：维度ID(公式) 是维度 key_field，必须拼成 'order.order_id'。"""
    monkeypatch.setattr(s.FeishuClient, "list_bitable_fields",
                        lambda self, app, tbl: [
                            {"field_id": "f1", "field_name": "维度ID", "type": _F_FORMULA},
                            {"field_id": "f2", "field_name": "起始表别名", "type": _F_LOOKUP},
                        ])
    monkeypatch.setattr(s.FeishuClient, "list_bitable_records",
                        lambda self, app, tbl: [
                            {"record_id": "r1", "fields": {
                                "维度ID": [{"text": "order.order_id", "type": "text"}],
                                "起始表别名": [{"text": "link", "type": "text"}]}}])
    recs = s.fetch_table_records("APP", "tbl1")
    assert recs[0]["维度ID"] == "order.order_id"
    assert recs[0]["起始表别名"] == "link"


def test_simplify_value_storage_basics():
    """存储字段基本形态：text 拼串、single→串、multi→list。"""
    assert s._simplify_value(_F_TEXT, [{"text": "x"}]) == "x"
    assert s._simplify_value(_F_SINGLE_SELECT, "订单") == "订单"   # 裸字符串（本 base 实际形态）
    assert s._simplify_value(_F_MULTI_SELECT, ["a", "b"]) == ["a", "b"]
    assert s._simplify_value(_F_FORMULA, 42) == 42           # 公式无 ui_type 时裸数字原样降级


def test_simplify_value_number_field_string_to_numeric():
    """Number(2) 字段开放平台返回【字符串】，须规整为 int/float；非数字串原样。"""
    assert s._simplify_value(_F_NUMBER, "12.5") == 12.5
    assert s._simplify_value(_F_NUMBER, "8") == 8            # 整数字符串 → int
    assert s._simplify_value(_F_NUMBER, 125) == 125          # 已是数字原样
    assert s._simplify_value(_F_NUMBER, "abc") == "abc"      # 非数字串原样保留
    assert s._simplify_value(_F_NUMBER, "") is None
    assert s._simplify_value(_F_NUMBER, None) is None


def test_simplify_value_datetime_field_ms_epoch():
    """DateTime(5) 字段返回 ms 毫秒时间戳 → 'YYYY-MM-DD HH:MM:SS'（+8 时区）。"""
    # 1774317600000ms = 2026-03-21 02:00 UTC = 10:00 +8（用户写入 '2026-03-24'? 飞书实际值）
    out = s._simplify_value(_F_DATE, 1774317600000)
    assert isinstance(out, str) and out.endswith(":00") and out.startswith("2026-")
    assert s._simplify_value(_F_DATE, None) is None


def test_simplify_value_checkbox_passthrough_bool():
    """Checkbox(7) → bool 原样（Neo4j 原生支持）。"""
    assert s._simplify_value(_F_CHECKBOX, True) is True
    assert s._simplify_value(_F_CHECKBOX, False) is False


def test_simplify_value_auto_number_string():
    """AutoNumber(1005) 已纳入支持（不再过滤）→ 'NO.001' 串原样。"""
    assert s._simplify_value(_F_AUTO_NUMBER, "NO.001") == "NO.001"
    assert s._simplify_value(_F_AUTO_NUMBER, "NO.002") == "NO.002"


def test_simplify_formula_text_and_number():
    """公式结果 text → 拼串；number → 数字规整。按结果 data_type 分派。"""
    assert s._simplify_formula([{"text": "订单分析-X", "type": "text"}], _F_TEXT, None) == "订单分析-X"
    assert s._simplify_formula(125, _F_NUMBER, None) == 125
    # 公式数字也可能以字符串回来（部分场景）
    assert s._simplify_formula("125", _F_NUMBER, None) == 125


def test_simplify_formula_date_ms():
    """公式日期：search 接口统一返回 ms（裸 int 或 [ms] 列表）→ 'YYYY-MM-DD HH:MM:SS'。
    旧 GET /records 的 Excel 日序号形态已不再兼容（接口下架）。"""
    ms_bare = s._simplify_formula(1774317600000, _F_DATE, None)
    assert ms_bare is not None and len(ms_bare) == 19 and ms_bare[4:5] == "-"
    ms_list = s._simplify_formula([1774317600000], _F_DATE, None)   # 包装解包后的 [ms]
    assert ms_list == ms_bare
    assert s._simplify_formula(None, _F_DATE, None) is None


def test_simplify_formula_select_resolves_option_id():
    """公式单选返回选项 ID（如 ['opt4x1aCdv']），用表级 opt_map 反查为选项名。
    单选→串、多选→list；未知 ID 返回的名字原样（fallback）。"""
    opt_map = {"opt4x1aCdv": "进行中", "optA": "标签A", "optB": "标签B"}
    assert s._simplify_formula(["opt4x1aCdv"], _F_SINGLE_SELECT, opt_map) == "进行中"
    assert s._simplify_formula(["optA", "optB"], _F_MULTI_SELECT, opt_map) == ["标签A", "标签B"]
    # 未知 ID：opt_map 无则原样返回该串
    assert s._simplify_formula(["optZZZ"], _F_SINGLE_SELECT, opt_map) == "optZZZ"


def test_simplify_formula_wrapper_form_defensive():
    """官方文档示例公式值是 {type, value} 包装（实测为裸值），防御性兼容：包装内 type 优先。"""
    # 包装形式：type=5(日期) + value=[ms]
    assert s._simplify_formula({"type": _F_DATE, "value": [1774317600000]}, None, None) is not None
    # 裸值 + 无 data_type → 文本降级
    assert s._simplify_formula([{"text": "x"}], None, None) == "x"


def test_simplify_formula_wrapper_number_unwraps_single_list():
    """search 接口公式值以 {type, value:[n]} 包装：数字/复选框解包后是单元素列表，
    须拆成标量（否则 [125] 列表写进图，语义错）。真实 base 实测形态。"""
    assert s._simplify_formula({"type": _F_NUMBER, "value": [125]}, None, None) == 125
    assert s._simplify_formula({"type": _F_NUMBER, "value": [12.5]}, None, None) == 12.5


def test_simplify_value_url_field_flattens_to_text():
    """Url(15) 字段开放平台返回 {text, link} 裸 dict（单值）或 [{text,link}]，
    须拍平成可读 text 串，否则 dict 写进 Neo4j 报 Map 类型错（线上 sync 实踩）。"""
    assert s._simplify_value(_F_URL, {"text": "link｜用户期数主链路事实表",
                                      "link": "https://my.feishu.cn/docx/SaQ5"}) == "link｜用户期数主链路事实表"
    # 片段数组形态同样拍平
    assert s._simplify_value(_F_URL, [{"text": "a", "link": "u1"},
                                      {"text": "b", "link": "u2"}]) == "ab"
    # 空 text → None（过滤掉，不进图）
    assert s._simplify_value(_F_URL, {"text": "", "link": "u"}) is None


def test_simplify_value_unknown_type_dict_flattened():
    """未识别字段类型若返回结构化 dict/[{text}]，兜底拍平成串，避免写坏 Neo4j。"""
    assert s._simplify_value(999, {"text": "x", "extra": 1}) == "x"
    assert s._simplify_value(999, [{"text": "a"}, {"text": "b"}]) == "ab"
    # 数字等原始值仍原样
    assert s._simplify_value(999, 7) == 7


def test_simplify_value_unsupported_types_return_hint():
    """人员/附件/群组/位置/系统时间/关联 等暂不支持的类型 → 返回简短提示，不做清洗。"""
    assert s._simplify_value(_F_USER, [{"id": "ou_x", "name": "黄泡泡"}]) == "（人员字段，暂不支持取值）"
    assert s._simplify_value(_F_ATTACHMENT, [{"name": "r.png"}]) == "（附件字段，暂不支持取值）"
    assert s._simplify_value(_F_LOCATION, {"full_address": "北京"}) == "（地理位置字段，暂不支持取值）"
    assert s._simplify_value(_F_CREATED_TIME, 1774317600000) == "（创建时间字段，暂不支持取值）"
    assert s._simplify_value(_F_SINGLE_LINK, {"link_record_ids": ["r1"]}) == "（单向关联字段，暂不支持取值）"


def test_simplify_value_phone_autonumber_fallthrough_str():
    """电话(13)/自动编号(1005) 本身是串，走通用 str 分支（无需专门处理）。"""
    assert s._simplify_value(_F_PHONE, "13800000000") == "13800000000"
    assert s._simplify_value(_F_AUTO_NUMBER, "NO.001") == "NO.001"


def test_fetch_records_single_page_no_extra_call(monkeypatch):
    """client 已翻页；fetch_table_records 只调一次 records。"""
    monkeypatch.setattr(s.FeishuClient, "list_bitable_fields",
                        lambda self, app, tbl: [{"field_id": "f1", "field_name": "名称",
                                                 "type": _F_TEXT}])
    calls = []
    monkeypatch.setattr(s.FeishuClient, "list_bitable_records",
                        lambda self, app, tbl: calls.append(1) or [
                            {"record_id": "r1", "fields": {"名称": [{"text": "A"}]}}])
    recs = s.fetch_table_records("APP", "tbl1")
    assert len(recs) == 1 and recs[0]["名称"] == "A"
    assert len(calls) == 1


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
    monkeypatch.setattr(s, "_create_fulltext_indexes", lambda c, e: (calls.append("ftidx") or ["f0"]))
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
    assert out["fulltext_indexes"] == 1
    assert out["embed"] == {"指标": 1}
    assert calls == ["fetch", "clear", "nodes", "rels", "st", "idx", "ftidx", "embed"]


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
    assert calls == ["st", "idx", "ftidx", "embed"]


def test_create_fulltext_indexes_uses_cjk_and_skips_disabled_entities():
    class Client:
        def __init__(self):
            self.cyphers = []
        def execute(self, cypher, **params):
            self.cyphers.append(cypher)

    client = Client()
    names = s._create_fulltext_indexes(client, GC["entities"])

    assert names == ["指标_search_text_index"]
    assert len(client.cyphers) == 1
    assert "CREATE FULLTEXT INDEX `指标_search_text_index` IF NOT EXISTS" in client.cyphers[0]
    assert "ON EACH [n.search_text]" in client.cyphers[0]
    assert "`fulltext.analyzer`: 'cjk'" in client.cyphers[0]


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
