"""FeishuClient mock 单元测试（mock httpx，不依赖真实飞书）。"""
import pytest
import sda_mcp.feishu as f
from sda_mcp.errors import ConfigError, ExternalAPIError


class _Resp:
    def __init__(self, body, status=200):
        self._b = body
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise f.httpx.HTTPStatusError("http err", request=None, response=self)

    def json(self):
        return self._b


# --- _get_tenant_token ---

def test_token_cached_and_reused(monkeypatch):
    f._reset_token_cache()
    calls = []

    def _post(url, json=None, **k):
        calls.append(json)
        return _Resp({"code": 0, "tenant_access_token": "T1", "expire": 7200})

    monkeypatch.setattr(f.httpx, "post", _post)
    monkeypatch.setattr(f, "get_env",
                        lambda *k: {"FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "b"})
    assert f._get_tenant_token() == "T1"
    assert f._get_tenant_token() == "T1"   # 命中缓存，不再请求
    assert len(calls) == 1


def test_token_refreshed_after_expiry(monkeypatch):
    import time as _time
    f._reset_token_cache()
    calls = []

    def _post(url, json=None, **k):
        calls.append(1)
        return _Resp({"code": 0, "tenant_access_token": "T%d" % len(calls), "expire": 7200})

    monkeypatch.setattr(f.httpx, "post", _post)
    monkeypatch.setattr(f, "get_env",
                        lambda *k: {"FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "b"})
    assert f._get_tenant_token() == "T1"
    # 强制让缓存过期
    f._token_cache["expires_at"] = _time.time() - 1
    assert f._get_tenant_token() == "T2"
    assert len(calls) == 2


def test_token_missing_creds_raises_config(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "get_env",
                        lambda *k: (_ for _ in ()).throw(ConfigError("缺 FEISHU_APP_ID")))
    with pytest.raises(ConfigError):
        f._get_tenant_token()


def test_token_api_error_raises_external(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f.httpx, "post",
                        lambda *a, **k: _Resp({"code": 99941001, "msg": "bad secret"}))
    monkeypatch.setattr(f, "get_env",
                        lambda *k: {"FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "b"})
    with pytest.raises(ExternalAPIError):
        f._get_tenant_token()


# --- _request + _check ---

def test_request_raises_on_nonzero_code(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")

    def _req(method, url, **k):
        return _Resp({"code": 99941002, "msg": "no permission"})

    monkeypatch.setattr(f.httpx, "request", _req)
    client = f.FeishuClient()
    with pytest.raises(ExternalAPIError):
        client._request("GET", "/open-apis/anything")


def test_request_returns_data_on_success(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")

    def _req(method, url, **k):
        assert method == "GET"
        assert k["headers"]["Authorization"] == "Bearer TOK"
        return _Resp({"code": 0, "data": {"ok": True}})

    monkeypatch.setattr(f.httpx, "request", _req)
    assert f.FeishuClient()._request("GET", "/x") == {"code": 0, "data": {"ok": True}}


# --- get_raw_content ---

def test_get_raw_content_returns_plain_text(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}

    def _req(method, url, **k):
        captured.update(method=method, url=url, headers=k["headers"])
        return _Resp({"code": 0, "data": {"content": "标题\nselect * from t"}})

    monkeypatch.setattr(f.httpx, "request", _req)
    text = f.FeishuClient().get_raw_content("DOC")
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/open-apis/docx/v1/documents/DOC/raw_content")
    assert captured["headers"]["Authorization"] == "Bearer TOK"
    assert text == "标题\nselect * from t"


def test_get_raw_content_business_error_raises(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request",
                        lambda *a, **k: _Resp({"code": 1770002, "msg": "doc not found"}))
    with pytest.raises(ExternalAPIError):
        f.FeishuClient().get_raw_content("NOPE")


def test_get_raw_content_missing_content_raises(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request",
                        lambda *a, **k: _Resp({"code": 0, "data": {}}))
    with pytest.raises(ExternalAPIError, match="content"):
        f.FeishuClient().get_raw_content("DOC")


# --- list_bitable_fields ---

def test_list_bitable_fields_returns_raw_items(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request", lambda *a, **k: _Resp({
        "code": 0, "data": {"items": [
            {"field_id": "fid1", "field_name": "名称", "type": 1, "ui_type": "Text"},
            {"field_id": "fid2", "field_name": "自增", "type": 1005, "ui_type": "AutoNumber"}],
            "has_more": False}}))
    items = f.FeishuClient().list_bitable_fields("APP", "tbl1")
    assert len(items) == 2                       # client 不过滤，原样返回
    assert items[0]["field_name"] == "名称"
    assert items[1]["type"] == 1005


# --- list_bitable_records ---

def test_list_bitable_records_single_page(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}

    def _req(method, url, json=None, **k):
        captured["method"] = method
        captured["url"] = url
        captured["body"] = json
        return _Resp({"code": 0, "data": {"items": [
            {"record_id": "r1", "fields": {"名称": [{"text": "A"}]}},
            {"record_id": "r2", "fields": {"名称": [{"text": "B"}]}}],
            "has_more": False}})

    monkeypatch.setattr(f.httpx, "request", _req)
    items = f.FeishuClient().list_bitable_records("APP", "tbl1")
    assert len(items) == 2
    assert items[0]["record_id"] == "r1"
    # 走官方推荐的 POST /records/search（旧 GET /records 已废弃）
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/records/search")
    assert captured["body"]["page_size"] == 500


def test_list_bitable_records_paginates_via_page_token(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    pages = [
        _Resp({"code": 0, "data": {"items": [{"record_id": "r1", "fields": {}}],
                                   "has_more": True, "page_token": "PT2"}}),
        _Resp({"code": 0, "data": {"items": [{"record_id": "r2", "fields": {}}],
                                   "has_more": False}}),
    ]
    calls = []

    def _req(method, url, json=None, **k):
        calls.append((json or {}).get("page_token"))   # search：page_token 在 body
        return pages.pop(0)

    monkeypatch.setattr(f.httpx, "request", _req)
    items = f.FeishuClient().list_bitable_records("APP", "tbl1")
    assert [i["record_id"] for i in items] == ["r1", "r2"]
    assert calls == [None, "PT2"]


# --- 健壮性：HTTP 错误 / 非 JSON 响应 / 翻页防御 ---

def test_request_http_500_raises_external(monkeypatch):
    """raise_for_status → ExternalAPIError（HTTP 状态码错误路径）。"""
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request",
                        lambda *a, **k: _Resp({"code": 0, "data": {}}, status=500))
    with pytest.raises(ExternalAPIError):
        f.FeishuClient()._request("GET", "/open-apis/x")


def test_request_non_json_body_raises_external(monkeypatch):
    """非 JSON 200 响应（网关 HTML 错误页）→ json.JSONDecodeError(ValueError) 归一为 ExternalAPIError。"""
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")

    class _BadResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(f.httpx, "request", lambda *a, **k: _BadResp())
    with pytest.raises(ExternalAPIError):
        f.FeishuClient()._request("GET", "/open-apis/x")


def test_token_non_json_body_raises_external(monkeypatch):
    """token 端点同样：非 JSON 200 响应归一为 ExternalAPIError（非裸 ValueError）。"""
    f._reset_token_cache()

    class _BadResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(f.httpx, "post", lambda *a, **k: _BadResp())
    monkeypatch.setattr(f, "get_env",
                        lambda *k: {"FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "b"})
    with pytest.raises(ExternalAPIError):
        f._get_tenant_token()


def test_list_bitable_records_breaks_when_has_more_but_no_token(monkeypatch):
    """has_more=True 但缺 page_token → 防御性 break，不无限循环。"""
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    calls = []

    def _req(method, url, json=None, **k):
        calls.append(1)
        return _Resp({"code": 0, "data": {"items": [
            {"record_id": "r1", "fields": {}}],
            "has_more": True}})  # 故意无 token

    monkeypatch.setattr(f.httpx, "request", _req)
    items = f.FeishuClient().list_bitable_records("APP", "tbl1")
    assert len(items) == 1 and items[0]["record_id"] == "r1"
    assert len(calls) == 1   # 只调一次即 break，未陷入死循环
