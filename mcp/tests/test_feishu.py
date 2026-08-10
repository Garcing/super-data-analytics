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


# --- 写端点 ---

def test_convert_strips_table_merge_info(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    captured = {}
    table_block = {"block_id": "b1", "block_type": 31, "children": ["c1"],
                   "table": {"cells": ["c1"], "property": {"row_size": 1, "column_size": 1,
                                                            "merge_info": [{"col_span": 1, "row_span": 1}]}}}
    def _req(method, url, json=None, **k):
        captured["body"] = json
        return _Resp({"code": 0, "data": {"blocks": [table_block], "first_level_block_ids": ["b1"]}})
    monkeypatch.setattr(f.httpx, "request", _req)
    blocks, fl = f.FeishuClient().convert_markdown_to_blocks("# x\n")
    assert fl == ["b1"]
    assert captured["body"] == {"content_type": "markdown", "content": "# x\n"}
    # merge_info 已被剥
    assert "merge_info" not in blocks[0]["table"]["property"]


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


def test_delete_all_children_uses_root_child_count(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    calls = []
    def _req(method, url, params=None, json=None, **k):
        calls.append((method, url, json))
        if url.endswith("/blocks"):
            return _Resp({"code": 0, "data": {"items": [
                {"block_id": "DOC", "block_type": 1, "children": ["a", "b", "c"]}]}})
        return _Resp({"code": 0})
    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().delete_all_children("DOC")
    # 第二次调用应是 batch_delete，end_index=3
    assert calls[1][0] == "DELETE"
    assert "batch_delete" in calls[1][1]
    assert calls[1][2] == {"start_index": 0, "end_index": 3}


def test_delete_all_children_noop_when_empty(monkeypatch):
    f._reset_token_cache()
    monkeypatch.setattr(f, "_get_tenant_token", lambda: "TOK")
    calls = []
    def _req(method, url, params=None, json_body=None, **k):
        calls.append(url)
        if url.endswith("/blocks"):
            return _Resp({"code": 0, "data": {"items": [
                {"block_id": "DOC", "block_type": 1, "children": []}]}})
        return _Resp({"code": 0})
    monkeypatch.setattr(f.httpx, "request", _req)
    f.FeishuClient().delete_all_children("DOC")
    assert len(calls) == 1  # 根无子块 → 不调 batch_delete

