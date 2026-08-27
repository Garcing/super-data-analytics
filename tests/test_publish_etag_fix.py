"""P0-1 回归：publish 三缺陷（2026-08-26 QA 发现，自 2026-07-11 起全挂）。

1. summary 为字符串 → _build_index_entry AttributeError（schema 未约束 summary 结构）。
2. 索引 CDN etag 为弱 etag ``W/"..."``，Vercel ``x-if-match`` 拒绝 → 乐观锁永久 412。
   API head 响应实测无 etag 字段，必须从 CDN 响应取并剥 ``W/`` 转强形式。
3. 索引更新最终失败时，已上传的报告 JSON 成为孤儿 Blob → 需补偿删除。
4. 乐观锁耗尽后兜底一次无条件写（单写者场景可用性优先），仍失败才抛错。
"""
import json

import pytest

from sda_mcp.errors import ExternalAPIError
from sda_mcp.skills.building_reports import html_reports as h
from sda_mcp.skills.building_reports.blob_store import BlobInfo

REPORT_DICT = {"meta": {"title": "周报", "tags": ["销售"]}, "summary": {"overall": "总体向好"}}
REPORT_STR = {"meta": {"title": "周报"}, "summary": "纯文字总结"}


class _FakeResp:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


def _blob(url="https://u/i.json", etag=None, uploaded_at="2026-07-11T09:01:04.000Z"):
    return BlobInfo(url=url, pathname="i.json", content_type="application/json",
                    size=1, uploaded_at=uploaded_at, etag=etag, download_url=None)


def _patch_frontend(monkeypatch, url="https://app.example.com"):
    monkeypatch.setattr(h, "load_config", lambda: {"env": {"VERCEL_REPORTS_URL": url}})


def test_build_index_entry_accepts_string_summary():
    """summary 允许字符串或 {overall: ...} 对象，两者都进索引条目。"""
    entry = h._build_index_entry("r1", REPORT_STR, None)
    assert entry["summary"] == "纯文字总结"
    entry2 = h._build_index_entry("r1", REPORT_DICT, None)
    assert entry2["summary"] == "总体向好"


def test_read_index_normalizes_weak_etag(monkeypatch):
    """CDN 返回弱 etag W/"idx1" 时，ifMatch 必须用强形式 "idx1"。"""
    captured = {}

    class FakeClient:
        def put(self, pathname, data, if_match=None, **kw):
            captured["if_match"] = if_match
            return _blob(url=f"https://u/{pathname}")
        def head(self, path):
            return _blob(etag=None)  # 实测 Vercel API head 响应无 etag 字段
        def delete(self, urls):
            pass

    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(
        200, text='{"reports": []}', headers={"etag": 'W/"idx1"'}))

    h._optimistic_update(FakeClient(), lambda idx: idx)
    assert captured["if_match"] == '"idx1"'


def test_publish_with_string_summary_succeeds(monkeypatch):
    """端到端：字符串 summary 的报告发布成功（QA 中 8/8 失败的最小载荷形态）。"""

    class FakeClient:
        def put(self, pathname, data, if_match=None, **kw):
            return _blob(url=f"https://u/{pathname}")
        def head(self, path):
            return _blob(etag=None)
        def delete(self, urls):
            pass

    monkeypatch.setattr(h, "VercelBlobClient", FakeClient)
    _patch_frontend(monkeypatch)
    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(
        200, text='{"reports": []}', headers={"etag": '"idx1"'}))
    r = h.publish_report(REPORT_STR, "r1")
    assert r.report_id == "r1"


def test_optimistic_update_falls_back_to_unconditional_write(monkeypatch):
    """条件写 412 耗尽 → 兜底一次无条件写成功 → 不抛错。"""
    monkeypatch.setattr(h, "_LOCK_BASE_DELAY", 0)
    monkeypatch.setattr(h, "_LOCK_ATTEMPTS", 2)
    writes = []

    class FakeClient:
        def put(self, pathname, data, if_match=None, **kw):
            writes.append(if_match)
            if if_match is not None:
                raise ExternalAPIError("Vercel Blob 条件写失败（ifMatch 不匹配，索引已被他人改写）")
            return _blob(url=f"https://u/{pathname}")
        def head(self, path):
            return _blob(etag=None)
        def delete(self, urls):
            pass

    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(
        200, text='{"reports": []}', headers={"etag": 'W/"idx1"'}))
    h._optimistic_update(FakeClient(), lambda idx: idx)  # 不抛即成功
    assert None in writes  # 存在一次无条件兜底写


def test_publish_deletes_report_blob_when_index_write_exhausts(monkeypatch):
    """索引更新彻底失败 → 抛错且补偿删除已上传报告（不留孤儿 Blob）。"""
    monkeypatch.setattr(h, "_LOCK_BASE_DELAY", 0)
    monkeypatch.setattr(h, "_LOCK_ATTEMPTS", 2)
    deleted = []

    class FakeClient:
        def put(self, pathname, data, if_match=None, **kw):
            if pathname == h.INDEX_PATH:
                raise ExternalAPIError("Vercel Blob PUT 失败 (500): down")
            return _blob(url=f"https://u/{pathname}")
        def head(self, path):
            return _blob(url=f"https://u/{path}", etag=None)
        def delete(self, urls):
            deleted.extend(urls if isinstance(urls, list) else [urls])

    monkeypatch.setattr(h, "VercelBlobClient", FakeClient)
    _patch_frontend(monkeypatch)
    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(
        200, text='{"reports": []}', headers={"etag": '"idx1"'}))
    with pytest.raises(ExternalAPIError):
        h.publish_report(REPORT_DICT, "r1")
    assert deleted == ["https://u/html-reports/r1.json"]
