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


def test_get_document_returns_metadata(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request", lambda *a, **k: _Resp({
        "code": 0, "data": {"document": {
            "document_id": "DOC", "title": "标题", "revision_id": 23,
        }},
    }))
    assert f.FeishuClient().get_document("DOC")["revision_id"] == 23


# --- list_folder_files ---

def test_list_folder_files_single_page(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request", lambda *a, **k: _Resp({
        "code": 0, "data": {"files": [
            {"token": "d1", "name": "日报", "type": "docx", "url": "u1"},
            {"token": "f1", "name": "销售", "type": "folder"}],
            "has_more": False}}))
    files = f.FeishuClient().list_folder_files("ROOT")
    assert len(files) == 2
    assert files[0]["token"] == "d1"


def test_list_folder_files_paginates(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    pages = [
        _Resp({"code": 0, "data": {"files": [{"token": "d1", "name": "a", "type": "docx"}],
                                   "has_more": True, "next_page_token": "PG2"}}),
        _Resp({"code": 0, "data": {"files": [{"token": "d2", "name": "b", "type": "docx"}],
                                   "has_more": False}}),
    ]
    calls = []

    def _req(method, url, params=None, **k):
        calls.append(params.get("page_token"))
        return pages.pop(0)

    monkeypatch.setattr(f.httpx, "request", _req)
    files = f.FeishuClient().list_folder_files("ROOT")
    assert [x["token"] for x in files] == ["d1", "d2"]
    assert calls == [None, "PG2"]   # 第二页带上 page_token


# --- delete_file ---

def test_delete_file_calls_delete_endpoint(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}

    def _req(method, url, params=None, **k):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        return _Resp({"code": 0, "msg": "success"})

    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().delete_file("DOCTOK", "docx")
    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/open-apis/drive/v1/files/DOCTOK")
    assert captured["params"] == {"type": "docx"}


def test_delete_file_error_raises(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request",
                        lambda *a, **k: _Resp({"code": 99941002, "msg": "no perm"}))
    with pytest.raises(ExternalAPIError):
        f.FeishuClient().delete_file("DOC")


# --- list_bitable_fields ---

def test_list_tables_returns_items(monkeypatch):
    """GET /apps/{app}/tables → [{table_id, name}]，自动翻页。"""
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}

    def _req(method, url, params=None, **k):
        captured["url"] = url
        captured["method"] = method
        return _Resp({"code": 0, "data": {"items": [
            {"table_id": "tbl1", "name": "指标", "revision": 1},
            {"table_id": "tbl2", "name": "维度", "revision": 2}],
            "has_more": False}})

    monkeypatch.setattr(f.httpx, "request", _req)
    tables = f.FeishuClient().list_tables("APP")
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/open-apis/bitable/v1/apps/APP/tables")
    assert [t["table_id"] for t in tables] == ["tbl1", "tbl2"]


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


def test_list_folder_files_breaks_when_has_more_but_no_token(monkeypatch):
    """has_more=True 但缺 next_page_token/page_token → 防御性 break，不无限循环。"""
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    calls = []

    def _req(method, url, params=None, **k):
        calls.append(1)
        return _Resp({"code": 0, "data": {"files": [
            {"token": "d1", "name": "a", "type": "docx"}],
            "has_more": True}})  # 故意无 token

    monkeypatch.setattr(f.httpx, "request", _req)
    files = f.FeishuClient().list_folder_files("ROOT")
    assert len(files) == 1 and files[0]["token"] == "d1"
    assert len(calls) == 1   # 只调一次即 break，未陷入死循环


def test_create_doc_returns_document_id(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request",
                        lambda *a, **k: _Resp({"code": 0, "data": {"document": {"document_id": "DOCNEW"}}}))
    assert f.FeishuClient().create_doc("FOLDER", "标题") == "DOCNEW"


def test_insert_descendants_payload(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}
    def _req(method, url, json=None, **k):
        captured["url"] = url
        captured["body"] = json
        return _Resp({"code": 0, "data": {"document_revision_id": 2}})
    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().insert_descendants("DOC", [{"block_type": 2}], ["b1"])
    assert captured["url"].endswith("/blocks/DOC/descendant")
    assert captured["body"] == {"children_id": ["b1"], "descendants": [{"block_type": 2}]}


def test_list_blocks_returns_items(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request", lambda *a, **k: _Resp({
        "code": 0, "data": {"items": [{"block_id": "P", "block_type": 1, "children": ["a", "b", "c"]},
                                      {"block_id": "a", "block_type": 2}]}}))
    items = f.FeishuClient().list_blocks("DOC")
    assert len(items) == 2
    assert items[0]["block_type"] == 1


def test_list_blocks_pins_every_page_to_revision(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    pages = [
        _Resp({"code": 0, "data": {"items": [{"block_id": "P", "block_type": 1}],
                                        "has_more": True, "page_token": "NEXT"}}),
        _Resp({"code": 0, "data": {"items": [{"block_id": "T", "block_type": 2}],
                                        "has_more": False}}),
    ]
    params_seen = []

    def _req(method, url, params=None, **kwargs):
        params_seen.append(params)
        return pages.pop(0)

    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().list_blocks("DOC", document_revision_id=23)
    assert [params["document_revision_id"] for params in params_seen] == [23, 23]


def test_batch_update_blocks_uses_revision_and_native_requests(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}

    def _req(method, url, params=None, json=None, **kwargs):
        captured.update(method=method, url=url, params=params, body=json)
        return _Resp({"code": 0, "data": {"document_revision_id": 24, "blocks": []}})

    monkeypatch.setattr(f.httpx, "request", _req)
    requests = [{"block_id": "B", "update_text_elements": {"elements": []}}]
    out = f.FeishuClient().batch_update_blocks("DOC", 23, requests)
    assert captured["method"] == "PATCH"
    assert captured["url"].endswith("/documents/DOC/blocks/batch_update")
    assert captured["params"]["document_revision_id"] == 23
    assert captured["params"]["client_token"]
    assert captured["body"] == {"requests": requests}
    assert out["data"]["document_revision_id"] == 24


def test_delete_children_uses_revision_and_half_open_range(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}

    def _req(method, url, params=None, json=None, **kwargs):
        captured.update(method=method, url=url, params=params, body=json)
        return _Resp({"code": 0, "data": {"document_revision_id": 25}})

    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().delete_children("DOC", "PARENT", 24, 1, 3)
    assert captured["method"] == "DELETE"
    assert "/blocks/PARENT/children/batch_delete" in captured["url"]
    assert captured["params"]["document_revision_id"] == 24
    assert captured["body"] == {"start_index": 1, "end_index": 3}

