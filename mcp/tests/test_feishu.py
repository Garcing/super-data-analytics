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


# --- get_doc_markdown ---

def test_get_doc_markdown_returns_content(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}

    def _req(method, url, params=None, **k):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        return _Resp({"code": 0, "data": {"content": "# 标题\n正文"}, "msg": "success"})

    monkeypatch.setattr(f.httpx, "request", _req)
    assert f.FeishuClient().get_doc_markdown("DOCTOKEN") == "# 标题\n正文"
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/open-apis/docs/v1/content")
    assert captured["params"] == {"doc_token": "DOCTOKEN", "doc_type": "docx",
                                  "content_type": "markdown"}


def test_get_doc_markdown_missing_content_raises(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    monkeypatch.setattr(f.httpx, "request",
                        lambda *a, **k: _Resp({"code": 0, "data": {}}))
    with pytest.raises(ExternalAPIError):
        f.FeishuClient().get_doc_markdown("DOC")


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
    monkeypatch.setattr(f.httpx, "request", lambda *a, **k: _Resp({
        "code": 0, "data": {"items": [
            {"record_id": "r1", "fields": {"名称": [{"text": "A"}]}},
            {"record_id": "r2", "fields": {"名称": [{"text": "B"}]}}],
            "has_more": False}}))
    items = f.FeishuClient().list_bitable_records("APP", "tbl1")
    assert len(items) == 2
    assert items[0]["record_id"] == "r1"


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

    def _req(method, url, params=None, **k):
        calls.append(params.get("page_token"))
        return pages.pop(0)

    monkeypatch.setattr(f.httpx, "request", _req)
    items = f.FeishuClient().list_bitable_records("APP", "tbl1")
    assert [i["record_id"] for i in items] == ["r1", "r2"]
    assert calls == [None, "PT2"]
