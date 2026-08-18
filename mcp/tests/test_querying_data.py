"""querying_data 内核 mock 单元测试（离线，不连真服务）。"""
import pytest
from sda_mcp.errors import ConfigError, ValidationError, DataSourceError, SkillTimeoutError
from sda_mcp.skills import querying_data as q

GUID = "12345678-1234-1234-1234-123456789012"


# --- 校验 ---

def test_validate_dax_payload_ok():
    r = q.validate_dax_payload({"artifactId": GUID, "daxQueries": ["EVALUATE 'T'"], "maxRows": 100})
    assert r["max_rows"] == 100 and len(r["dax_queries"]) == 1


@pytest.mark.parametrize("payload", [
    {"artifactId": "not-a-guid", "daxQueries": ["x"]},
    {"artifactId": GUID, "daxQueries": []},
    {"artifactId": GUID, "daxQueries": ["a"] * 5},
    {"artifactId": GUID, "daxQueries": ["a"], "maxRows": 0},
    {"artifactId": GUID, "daxQueries": ["a"], "maxRows": 1001},
    {"artifactId": GUID, "daxQueries": [123]},
])
def test_validate_dax_payload_rejects(payload):
    with pytest.raises(ValidationError):
        q.validate_dax_payload(payload)


def test_split_table_missing_dot():
    with pytest.raises(ValidationError):
        q._split_table("noschema")


def test_sql_query_empty_rejected():
    with pytest.raises(ValidationError):
        q.sql_query("   ")


def test_config_missing_raises(monkeypatch):
    import sda_mcp.config as cfg
    monkeypatch.setattr(cfg, "load_config", lambda: {"env": {}})
    cfg.get_env.cache_clear() if hasattr(cfg.get_env, "cache_clear") else None
    # load_config is lru_cached; get_env calls it directly so the monkeypatch on load_config works
    with pytest.raises(ConfigError):
        q.HologresClient()


class _FakeDescr:
    def __init__(self, name, type_code):
        self.name = name
        self.type_code = type_code


class _FakeCursor:
    def __init__(self, descr, rows):
        self.description = descr
        self._rows = rows
        self.executed = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, statement, *a, **k): self.executed.append(statement)
    def fetchall(self): return self._rows
    def fetchone(self): return self._rows[0] if self._rows else None


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return self._cursor


def test_sql_query_normalizes_empty_column_names(monkeypatch):
    cursor = _FakeCursor([_FakeDescr("real_col", 23), _FakeDescr("", 25)], [(1, "x"), (2, "y")])
    monkeypatch.setattr(q.HologresClient, "__init__", lambda self: None)
    monkeypatch.setattr(q.HologresClient, "_connect", lambda self: _FakeConn(cursor))
    r = q.sql_query("SELECT 1")
    assert r.columns[0]["name"] == "real_col"
    assert r.columns[1]["name"] == "col_1"
    assert r.row_count == 2
    assert not hasattr(r, "ok")
    assert cursor.executed == ["SET TRANSACTION READ ONLY", "SELECT 1"]


def test_powerbi_query_rejects_bad_artifact():
    with pytest.raises(ValidationError):
        q.powerbi_query("bad", ["EVALUATE 'T'"])


def test_powerbi_query_too_many_dax(monkeypatch):
    monkeypatch.setattr(q.PowerBIClient, "__init__", lambda self: None)
    monkeypatch.setattr(q.PowerBIClient, "_mcp_call", lambda self, m, p=None: {"result": {}})
    with pytest.raises(ValidationError):
        q.powerbi_query(GUID, ["a"] * 5)


# --- _mcp_call HTTP 行为（monkeypatch q.httpx） ---

class _FakeResp:
    """极简 httpx.Response 替身：status_code / headers.get / text。"""
    def __init__(self, status_code, body="", headers=None):
        self.status_code = status_code
        self.text = body if isinstance(body, str) else __import__("json").dumps(body)
        self.headers = headers or {}


class _FakeHttpxClient:
    """按 FIFO 顺序吐出预设响应；分别记 POST / GET 调用次数方便断言。"""
    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = 0
        self.gets = 0
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def post(self, *a, **k):
        self.posts += 1
        return self._responses.pop(0)
    def get(self, *a, **k):
        self.gets += 1
        return self._responses.pop(0)


def _wire_powerbi(monkeypatch, responses):
    """统一准备 PowerBIClient（跳过 msal）+ 注入 fake httpx.Client。返回 fake client 工厂以便断言。"""
    monkeypatch.setattr(q.PowerBIClient, "__init__", lambda self: None)
    monkeypatch.setattr(q.PowerBIClient, "_token", lambda self: "fake")
    holder = {}

    def _factory(*a, **k):
        holder["client"] = _FakeHttpxClient(responses)
        return holder["client"]
    monkeypatch.setattr(q.httpx, "Client", _factory)
    return holder


def test_mcp_call_202_polling_then_success(monkeypatch):
    """场景 1：202 + operation-location → 轮询 → 200 返回 JSON。"""
    responses = [
        _FakeResp(202, headers={"operation-location": "https://x/loc"}),
        _FakeResp(200, body='{"result":{"tools":[{"name":"t"}]}}'),
    ]
    holder = _wire_powerbi(monkeypatch, responses)
    tools = q.PowerBIClient().list_tools()
    assert tools == [{"name": "t"}]
    fake = holder["client"]
    assert fake.posts == 1 and fake.gets == 1


def test_mcp_call_202_timeout(monkeypatch):
    """场景 2：始终 202 + operation-location，_POLL_TIMEOUT_MS=0 立即超时。"""
    monkeypatch.setattr(q, "_POLL_TIMEOUT_MS", 0)
    monkeypatch.setattr(q, "_POLL_INTERVAL_S", 0)
    responses = [_FakeResp(202, headers={"operation-location": "https://x/loc"})]
    _wire_powerbi(monkeypatch, responses)
    with pytest.raises(SkillTimeoutError):
        q.PowerBIClient().list_tools()


def test_mcp_call_401_raises_datasource_with_hints(monkeypatch):
    """场景 3：401 → DataSourceError，含 3 条排错提示（权限/管理员同意/租户）。"""
    responses = [_FakeResp(401, body="forbidden")]
    _wire_powerbi(monkeypatch, responses)
    with pytest.raises(DataSourceError) as ei:
        q.PowerBIClient().list_tools()
    msg = str(ei.value)
    assert "权限" in msg
    assert "管理员同意" in msg
    assert "租户" in msg
    assert "forbidden" in msg


def test_mcp_call_sse_parse(monkeypatch):
    """场景 4：200，非纯 JSON，含 `data: {...}` 行 → 解析为该 JSON。"""
    body = 'event: message\ndata: {"result":{"x":1}}\n\n'
    responses = [_FakeResp(200, body=body)]
    _wire_powerbi(monkeypatch, responses)
    r = q.PowerBIClient()._mcp_call("tools/list")
    assert r == {"result": {"x": 1}}


def test_mcp_call_unparseable_raises(monkeypatch):
    """场景 5：200，body 无法解析 → DataSourceError 含「无法解析」。"""
    responses = [_FakeResp(200, body="garbage")]
    _wire_powerbi(monkeypatch, responses)
    with pytest.raises(DataSourceError) as ei:
        q.PowerBIClient()._mcp_call("tools/list")
    assert "无法解析" in str(ei.value)
