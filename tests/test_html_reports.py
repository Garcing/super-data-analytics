"""html_reports mock 单元测试（离线）。"""
import json
import pytest
from sda_mcp.errors import ExternalAPIError, ValidationError
from sda_mcp.skills.building_reports import html_reports as h
from sda_mcp.skills.building_reports.blob_store import BlobInfo


REPORT = {"meta": {"title": "周报", "generated_at": "2024-01-01T00:00:00Z", "tags": ["销售"]},
          "summary": {"overall": "总体向好"}}


class _FakeResp:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
    def json(self):
        return json.loads(self.text)


def _blob(url="https://u/i.json", etag='"e1"'):
    return BlobInfo(url=url, pathname="i.json", content_type="application/json",
                    size=1, uploaded_at="2024-01-01T00:00:00.000Z", etag=etag, download_url=None)


def _patch_frontend(monkeypatch, url="https://app.example.com"):
    # _frontend_url 走 load_config，patch h.load_config 注入 VERCEL_REPORTS_URL。
    monkeypatch.setattr(h, "load_config", lambda: {"env": {"VERCEL_REPORTS_URL": url}})


def test_publish_rejects_missing_title():
    with pytest.raises(ValidationError):
        h.publish_report({"meta": {}}, "r1")
    with pytest.raises(ValidationError):
        h.publish_report(REPORT, "")


def test_publish_writes_report_then_index(monkeypatch):
    calls = {"put": [], "head": [], "opt": 0}

    class FakeClient:
        def __init__(self): pass
        def put(self, pathname, data, **kw):
            calls["put"].append(pathname)
            return _blob(url=f"https://u/{pathname}")
        def head(self, path):
            calls["head"].append(path)
            return _blob(url=f"https://u/{path}", etag='"idx1"')
        def delete(self, urls): pass

    monkeypatch.setattr(h, "VercelBlobClient", FakeClient)
    _patch_frontend(monkeypatch)
    # 让 etag 一致性循环一次命中（公开读 etag == head etag）
    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(200, text='{"reports": []}', headers={"etag": '"idx1"'}))

    r = h.publish_report(REPORT, "r1")
    assert r.url == "https://app.example.com/report/r1"
    assert r.report_id == "r1"
    assert calls["put"][0] == "html-reports/r1.json"      # 先写报告
    assert calls["put"][1] == h.INDEX_PATH                # 再写索引


def test_publish_index_entry_has_fields(monkeypatch):
    """校验写入索引的 JSON 条目字段正确（created_at 取 generated_at）。"""
    written = {}
    class FakeClient:
        def put(self, pathname, data, **kw):
            written[pathname] = json.loads(data)
            return _blob(url=f"https://u/{pathname}")
        def head(self, path):
            return _blob(etag='"idx1"')
        def delete(self, urls): pass
    monkeypatch.setattr(h, "VercelBlobClient", FakeClient)
    _patch_frontend(monkeypatch, url="https://app")
    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(200, text='{"reports": []}', headers={"etag": '"idx1"'}))
    h.publish_report(REPORT, "r1")
    entry = written[h.INDEX_PATH]["reports"][0]
    assert entry["id"] == "r1"
    assert entry["title"] == "周报"
    assert entry["tags"] == ["销售"]
    assert entry["created_at"] == "2024-01-01T00:00:00Z"


def test_get_report_not_found(monkeypatch):
    class FakeClient:
        def head(self, path): return None
    monkeypatch.setattr(h, "VercelBlobClient", FakeClient)
    with pytest.raises(ExternalAPIError):
        h.get_report("missing")


def test_optimistic_lock_retries_on_412(monkeypatch):
    """索引写第一次 412（条件写失败）→ 退避 → 第二次成功。"""
    monkeypatch.setattr(h, "_LOCK_BASE_DELAY", 0)
    class FakeClient:
        def __init__(self):
            self._n = 0
        def put(self, pathname, data, if_match=None, **kw):
            if pathname == h.INDEX_PATH:
                self._n += 1
                if self._n == 1:
                    raise ExternalAPIError("Vercel Blob 条件写失败（ifMatch 不匹配，索引已被他人改写）")
            return _blob(url=f"https://u/{pathname}")
        def head(self, path): return _blob(etag='"idx1"')
        def delete(self, urls): pass
    monkeypatch.setattr(h, "VercelBlobClient", FakeClient)
    _patch_frontend(monkeypatch, url="https://app")
    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(200, text='{"reports": []}', headers={"etag": '"idx1"'}))
    h.publish_report(REPORT, "r1")   # 不抛即成功


def test_optimistic_lock_exhausts(monkeypatch):
    monkeypatch.setattr(h, "_LOCK_BASE_DELAY", 0)
    monkeypatch.setattr(h, "_LOCK_ATTEMPTS", 2)
    class FakeClient:
        def put(self, pathname, data, if_match=None, **kw):
            if pathname == h.INDEX_PATH:
                raise ExternalAPIError("Vercel Blob 条件写失败（ifMatch 不匹配，索引已被他人改写）")
            return _blob(url=f"https://u/{pathname}")
        def head(self, path): return _blob(etag='"idx1"')
        def delete(self, urls): pass
    monkeypatch.setattr(h, "VercelBlobClient", FakeClient)
    _patch_frontend(monkeypatch, url="https://app")
    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(200, text='{"reports": []}', headers={"etag": '"idx1"'}))
    with pytest.raises(ExternalAPIError):
        h.publish_report(REPORT, "r1")
