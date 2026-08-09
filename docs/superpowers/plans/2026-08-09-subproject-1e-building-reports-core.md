# 子项目 1.E 实现计划：building_reports 内核（HTML 报告 + 图片生成）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 `building-reports` 的两块能力从 Node CLI 移植成干净 Python 内核：(1) HTML 报告（Vercel Blob 直连 REST，替代 `@vercel/blob` SDK）；(2) 图片生成（apimart gpt-image-2 异步）。streamlit 已按用户要求砍掉。去 CLI/三态输入/落盘/`{ok}` 信封，供后续 MCP 工具直接调用。

**Architecture:** 子包 `building_reports/`，按"每个外部服务一个聚焦文件"拆分：`blob_store.py`（Vercel Blob REST 客户端）、`html_reports.py`（报告 CRUD + 索引乐观锁 + CDN etag 一致性）、`image_gen.py`（apimart 异步生成）。入口 `__init__.py` 导出公共函数。保留 html.js 的 CDN etag 一致性循环与 ifMatch 乐观锁（这是真并发/陈旧读的正确性保障，不是 CLI 冗余）。客户端在 `__init__` 读 `get_env`（同 1.C 模式），失败抛 `ConfigError`；外部 HTTP 失败抛 `ExternalAPIError`；输入非法抛 `ValidationError`。httpx `trust_env=True`（默认）天然走 `HTTPS_PROXY`，无需 Node 的 `ensureProxyEnv` 再执行。

**Tech Stack:** Python 3.10+；httpx（1.C 已引入）；无新依赖。

**Vercel Blob REST 契约（已核实 @vercel/blob SDK 源码，2026-08-09）：**
- API base：`https://vercel.com/api/blob`（`blob.vercel-storage.com` 是 CDN 内容域名，仅公开读）
- storeId：从 `BLOB_READ_WRITE_TOKEN` 解析 `token.split('_')[3]`
- 所有 API 请求：`Authorization: Bearer <token>` + `x-vercel-blob-store-id: <storeId>`
- `PUT {base}/{pathname}`：body=原始字节；选项经 `x-*` 头：`x-vercel-blob-access`(必发)、`x-add-random-suffix`、`x-allow-overwrite`、`x-cache-control-max-age`、`x-content-type`、`x-if-match`(条件写，设了则隐式开 allow-overwrite)
- `GET {base}/?url=<urlOrPathname>`：返回元数据（含 `etag`/`uploadedAt`）；找不到→null
- `POST {base}/delete`：body `{"urls":[...]}`；单 URL 可带 `x-if-match`
- 公开内容读：`GET <blob.url>`（CDN，带 cacheControl，最多 `cacheControlMaxAge` 陈旧）
- 响应字段：`url, downloadUrl, pathname, contentType, size, contentDisposition, cacheControl, uploadedAt, etag`

**范围：** 仅子项目 1.E。原 `building-reports/` 一律不动（铁律）。

---

## 文件结构

- Create: `mcp/sda_mcp/skills/building_reports/__init__.py` —— 公共 API 导出
- Create: `mcp/sda_mcp/skills/building_reports/blob_store.py` —— VercelBlobClient（put/head/delete）
- Create: `mcp/sda_mcp/skills/building_reports/html_reports.py` —— publish/list/get/delete + 索引乐观锁
- Create: `mcp/sda_mcp/skills/building_reports/image_gen.py` —— apimart submit/status/generate
- Modify: `mcp/sda_mcp/skills/__init__.py` —— 导出新函数
- Create: `mcp/tests/test_blob_store.py`
- Create: `mcp/tests/test_html_reports.py`
- Create: `mcp/tests/test_image_gen.py`

**不修改**：`building-reports/` 下任何文件。

---

## Task 1: blob_store.py —— Vercel Blob REST 客户端

**Files:**
- Create: `mcp/sda_mcp/skills/building_reports/blob_store.py`
- Test: `mcp/tests/test_blob_store.py`

- [ ] **Step 1: 写 `blob_store.py`**

```python
"""Vercel Blob REST 客户端（httpx 直连，移植 @vercel/blob SDK 的 put/head/del）。

契约源自 @vercel/blob SDK 源码（已核实，2026-08）：
- API base: https://vercel.com/api/blob（blob.vercel-storage.com 是 CDN 内容域名）
- storeId 从 BLOB_READ_WRITE_TOKEN 解析: token.split('_')[3]
- API 请求带 Authorization: Bearer + x-vercel-blob-store-id
- PUT {base}/{pathname}: 原始字节 body + x-* 选项头
- GET {base}/?url=<...>: 元数据；404→None
- POST {base}/delete: body {"urls":[...]}
- 公开内容读: GET <blob.url>（CDN，无鉴权）

去 CLI/三态/{ok}；失败抛 ConfigError(缺凭证)/ExternalAPIError(HTTP)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from sda_mcp.config import get_env
from sda_mcp.errors import ConfigError, ExternalAPIError

BLOB_API_BASE = "https://vercel.com/api/blob"
_TIMEOUT = httpx.Timeout(30.0)


@dataclass
class BlobInfo:
    url: str
    pathname: str
    content_type: str | None
    size: int | None
    uploaded_at: str | None          # ISO8601 字符串，原样保留
    etag: str | None
    download_url: str | None


def _parse_blob(data: dict[str, Any]) -> BlobInfo:
    return BlobInfo(
        url=data.get("url", ""),
        pathname=data.get("pathname", ""),
        content_type=data.get("contentType"),
        size=data.get("size"),
        uploaded_at=_iso(data.get("uploadedAt")),
        etag=data.get("etag"),
        download_url=data.get("downloadUrl"),
    )


def _iso(value: Any) -> str | None:
    """uploadedAt 可能是 '2024-01-15T10:30:00.000Z' 或对象；统一成字符串。"""
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


class VercelBlobClient:
    """put/head/delete 直连 Vercel Blob REST。"""

    def __init__(self) -> None:
        env = get_env("BLOB_READ_WRITE_TOKEN")
        token = env["BLOB_READ_WRITE_TOKEN"]
        if not token:
            raise ConfigError("BLOB_READ_WRITE_TOKEN 未配置")
        self._token = token
        # storeId 解析同 @vercel/blob：token.split('_')[3]
        parts = token.split("_")
        self._store_id = parts[3] if len(parts) > 3 else ""

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "x-vercel-blob-store-id": self._store_id,
        }
        if extra:
            headers.update(extra)
        return headers

    def put(
        self,
        pathname: str,
        data: bytes,
        *,
        content_type: str = "application/json",
        add_random_suffix: bool = False,
        allow_overwrite: bool = True,
        cache_control_max_age: int = 60,
        if_match: str | None = None,
    ) -> BlobInfo:
        headers = self._headers({
            "x-vercel-blob-access": "public",
            "x-add-random-suffix": "1" if add_random_suffix else "0",
            "x-allow-overwrite": "1" if (allow_overwrite or if_match) else "0",
            "x-cache-control-max-age": str(cache_control_max_age),
            "x-content-type": content_type,
        })
        if if_match:
            headers["x-if-match"] = if_match
        url = f"{BLOB_API_BASE}/{pathname}"
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.put(url, headers=headers, content=data)
        if resp.status_code == 412:
            raise ExternalAPIError("Vercel Blob 条件写失败（ifMatch 不匹配，索引已被他人改写）")
        if resp.status_code >= 400:
            raise ExternalAPIError(f"Vercel Blob PUT 失败 ({resp.status_code}): {resp.text[:500]}")
        return _parse_blob(resp.json())

    def head(self, pathname_or_url: str) -> BlobInfo | None:
        """取元数据。找不到返回 None（兼容 'does not exist' / 404）。"""
        url = f"{BLOB_API_BASE}/"
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers=self._headers(),
                              params={"url": pathname_or_url})
        if resp.status_code == 404:
            return None
        text = resp.text
        if resp.status_code >= 400:
            low = text.lower()
            if "does not exist" in low or "not found" in low:
                return None
            raise ExternalAPIError(f"Vercel Blob HEAD 失败 ({resp.status_code}): {text[:500]}")
        if not text or text == "null":
            return None
        return _parse_blob(resp.json())

    def delete(self, urls: str | list[str]) -> None:
        if isinstance(urls, str):
            urls = [urls]
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(f"{BLOB_API_BASE}/delete",
                               headers=self._headers({"Content-Type": "application/json"}),
                               json={"urls": urls})
        if resp.status_code >= 400:
            raise ExternalAPIError(f"Vercel Blob DELETE 失败 ({resp.status_code}): {resp.text[:500]}")
```

- [ ] **Step 2: 写 `mcp/tests/test_blob_store.py`**

```python
"""blob_store mock 单元测试（离线）。"""
import json
import pytest
from sda_mcp.errors import ConfigError, ExternalAPIError
from sda_mcp.skills.building_reports import blob_store as bs


class _FakeResp:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        if body is None:
            self.text = ""
        elif isinstance(body, str):
            self.text = body
        else:
            self.text = json.dumps(body)
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


class _FakeHttpxClient:
    """记录调用，按 FIFO 吐响应；记请求 url/headers/params/content/json。"""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def _pop(self, method, url, **kw):
        self.calls.append({"method": method, "url": url, **kw})
        return self._responses.pop(0)
    def put(self, url, headers=None, content=None, **k):
        return self._pop("PUT", url, headers=headers, content=content)
    def get(self, url, headers=None, params=None, **k):
        return self._pop("GET", url, headers=headers, params=params)
    def post(self, url, headers=None, json=None, **k):
        return self._pop("POST", url, headers=headers, json=json)


def _wire(monkeypatch, responses):
    holder = {}
    def _factory(*a, **k):
        holder["client"] = _FakeHttpxClient(responses)
        return holder["client"]
    monkeypatch.setattr(bs.httpx, "Client", _factory)
    return holder


def _client(monkeypatch):
    monkeypatch.setattr(bs.VercelBlobClient, "__init__",
                        lambda self: (setattr(self, "_token", "t"), setattr(self, "_store_id", "s"))[1])
    return bs.VercelBlobClient()


def test_missing_token_raises_config_error(monkeypatch):
    import sda_mcp.config as cfg
    monkeypatch.setattr(cfg, "load_config", lambda: {"env": {}})
    with pytest.raises(ConfigError):
        bs.VercelBlobClient()


def test_put_sends_x_headers_and_parses(monkeypatch):
    blob = {"url": "https://s.public.blob.vercel-storage.com/a.json",
            "pathname": "a.json", "contentType": "application/json",
            "size": 3, "uploadedAt": "2024-01-01T00:00:00.000Z", "etag": '"e1"'}
    holder = _wire(monkeypatch, [_FakeResp(200, body=blob)])
    c = _client(monkeypatch)
    info = c.put("a.json", b"{}")
    call = holder["client"].calls[0]
    assert call["url"] == f"{bs.BLOB_API_BASE}/a.json"
    h = call["headers"]
    assert h["x-vercel-blob-access"] == "public"
    assert h["x-add-random-suffix"] == "0"
    assert h["x-allow-overwrite"] == "1"
    assert h["x-cache-control-max-age"] == "60"
    assert h["x-content-type"] == "application/json"
    assert h["x-vercel-blob-store-id"] == "s"
    assert call["content"] == b"{}"
    assert info.url.endswith("a.json") and info.etag == '"e1"'


def test_put_if_match_implies_allow_overwrite(monkeypatch):
    holder = _wire(monkeypatch, [_FakeResp(200, body={"url": "u", "pathname": "p"})])
    c = _client(monkeypatch)
    c.put("p", b"x", allow_overwrite=False, if_match='"e"')
    h = holder["client"].calls[0]["headers"]
    assert h["x-if-match"] == '"e"'
    assert h["x-allow-overwrite"] == "1"   # ifMatch 隐式开


def test_put_412_precondition(monkeypatch):
    _wire(monkeypatch, [_FakeResp(412, body="precondition")])
    c = _client(monkeypatch)
    with pytest.raises(ExternalAPIError):
        c.put("p", b"x", if_match='"old"')


def test_put_5xx_raises(monkeypatch):
    _wire(monkeypatch, [_FakeResp(500, body="boom")])
    c = _client(monkeypatch)
    with pytest.raises(ExternalAPIError):
        c.put("p", b"x")


def test_head_found(monkeypatch):
    holder = _wire(monkeypatch, [_FakeResp(200, body={"url": "u", "pathname": "i.json", "etag": '"e"'})])
    c = _client(monkeypatch)
    info = c.head("i.json")
    call = holder["client"].calls[0]
    assert call["params"] == {"url": "i.json"}
    assert info is not None and info.etag == '"e"'


def test_head_not_found_variants(monkeypatch):
    for body, code in [("null", 200), ("not found", 404), ('{"error":"does not exist"}', 400)]:
        _wire(monkeypatch, [_FakeResp(code, body=body)])
        c = _client(monkeypatch)
        assert c.head("x.json") is None


def test_delete_posts_urls(monkeypatch):
    holder = _wire(monkeypatch, [_FakeResp(200)])
    c = _client(monkeypatch)
    c.delete(["u1", "u2"])
    call = holder["client"].calls[0]
    assert call["url"] == f"{bs.BLOB_API_BASE}/delete"
    assert call["json"] == {"urls": ["u1", "u2"]}
```

- [ ] **Step 3: 运行**

```bash
cd mcp && python -m pytest tests/test_blob_store.py -v
```
Expected: 8 passed。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/building_reports/blob_store.py mcp/tests/test_blob_store.py
git commit -m "feat(mcp): building_reports Vercel Blob REST client (put/head/delete)"
```

---

## Task 2: html_reports.py —— HTML 报告 CRUD + 索引乐观锁

**Files:**
- Create: `mcp/sda_mcp/skills/building_reports/html_reports.py`
- Test: `mcp/tests/test_html_reports.py`

- [ ] **Step 1: 写 `html_reports.py`**

```python
"""HTML 报告内核：直连 Vercel Blob 管理 html-reports/<id>.json + html-reports-index.json。

移植 building-reports/scripts/html/html.js（144-176）+ lib/shared.js 的乐观锁/CDN etag 一致性。

关键正确性逻辑（非冗余，必须保留）：
- read_index_with_etag: head() 强一致 etag vs 公开读(CDN) etag 对比，不一致退避重读，
  覆盖 60s CDN 缓存窗口（cacheControlMaxAge=60）。最多 12 次。
- 写索引用 ifMatch 乐观锁：并发改写触发 412 → 重试（最多 5 次，退避 300ms）。

去 CLI/三态/{ok}/落盘；publish 返回可分享前端链接。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from sda_mcp.config import get_env
from sda_mcp.errors import ExternalAPIError, ValidationError
from sda_mcp.skills.building_reports.blob_store import BlobInfo, VercelBlobClient

INDEX_PATH = "html-reports-index.json"
REPORT_PREFIX = "html-reports"
CACHE_MAX_AGE = 60           # CDN 缓存 60s，新报告 ~1min 内可见
_ETAG_MAX_RETRIES = 12       # 覆盖 60s 刷新窗口
_LOCK_ATTEMPTS = 5
_LOCK_BASE_DELAY = 0.300


@dataclass
class PublishResult:
    url: str                  # 可分享前端链接 ${frontend}/report/<id>
    report_id: str
    blob_url: str


def _frontend_url() -> str:
    return get_env("VERCEL_REPORTS_URL")["VERCEL_REPORTS_URL"].rstrip("/")


def _report_path(report_id: str) -> str:
    return f"{REPORT_PREFIX}/{report_id}.json"


def _put_json(client: VercelBlobClient, pathname: str, obj: Any, if_match: str | None = None) -> BlobInfo:
    return client.put(pathname, json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"),
                      content_type="application/json", cache_control_max_age=CACHE_MAX_AGE,
                      if_match=if_match)


def _read_index_with_etag(client: VercelBlobClient) -> tuple[dict[str, Any], str | None]:
    """head() 强一致 etag vs 公开读(CDN) etag 对比，一致才用。移植 html.js readIndexWithEtag。"""
    for i in range(_ETAG_MAX_RETRIES):
        blob = client.head(INDEX_PATH)
        if not blob or not blob.url:
            return {"reports": []}, None
        head_etag = (blob.etag or "").removeprefix("W/")
        resp = httpx.get(blob.url, timeout=httpx.Timeout(15.0))
        if resp.status_code >= 400:
            return {"reports": []}, None
        fetch_etag = resp.headers.get("etag", "").removeprefix("W/")
        if fetch_etag == head_etag:
            data: dict[str, Any] = {"reports": []}
            text = resp.text
            if text:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = {"reports": []}
            return data, head_etag
        if i < _ETAG_MAX_RETRIES - 1:
            time.sleep(i + 1)
    raise ExternalAPIError("索引读取一直陈旧（CDN 缓存未刷新）。请稍后重试——新报告约 1 分钟可见。")


def _build_index_entry(report_id: str, body: dict[str, Any], uploaded_at: str | None) -> dict[str, Any]:
    meta = body.get("meta") or {}
    return {
        "id": report_id,
        "title": meta.get("title") or report_id,
        "created_at": meta.get("generated_at") or uploaded_at or None,
        "updated_at": uploaded_at or None,
        "summary": (body.get("summary") or {}).get("overall", ""),
        "tags": meta.get("tags") if isinstance(meta.get("tags"), list) else [],
    }


def _upsert_entry(index: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    reports = list(index.get("reports") or [])
    for i, r in enumerate(reports):
        if r.get("id") == entry["id"]:
            reports[i] = {**entry, "created_at": r.get("created_at") or entry.get("created_at")}
            return {"reports": reports}
    reports.insert(0, entry)
    return {"reports": reports}


def _optimistic_update(client: VercelBlobClient, modify, read=_read_index_with_etag) -> None:
    """移植 shared.js withOptimisticLock：read→modify→write(ifMatch)；412 退避重试。"""
    last_err: Exception | None = None
    for attempt in range(_LOCK_ATTEMPTS):
        index, etag = read(client)
        next_index = modify(index)
        try:
            _put_json(client, INDEX_PATH, next_index, if_match=etag)
            return
        except ExternalAPIError as exc:
            last_err = exc
            if "条件写失败" not in str(exc):
                raise
            time.sleep(_LOCK_BASE_DELAY * (attempt + 1))
    raise ExternalAPIError(f"索引乐观锁重试 {_LOCK_ATTEMPTS} 次仍失败: {last_err}")


def publish_report(report: Mapping[str, Any], report_id: str) -> PublishResult:
    if not report_id:
        raise ValidationError("report_id 不能为空")
    if not isinstance(report, Mapping) or not (report.get("meta") or {}).get("title"):
        raise ValidationError("缺少必要字段: report.meta.title")
    client = VercelBlobClient()
    body = {**dict(report), "id": report_id}
    blob = _put_json(client, _report_path(report_id), body)
    # put 不返回 uploadedAt，补 head 拿时间戳（同 html.js 152）
    info = client.head(_report_path(report_id))
    uploaded_at = (info.uploaded_at if info else None) or blob.uploaded_at
    _optimistic_update(client, lambda idx: _upsert_entry(idx, _build_index_entry(report_id, body, uploaded_at)))
    return PublishResult(url=f"{_frontend_url()}/report/{report_id}",
                         report_id=report_id, blob_url=blob.url)


def list_reports() -> list[dict[str, Any]]:
    client = VercelBlobClient()
    data, _ = _read_index_with_etag(client)
    return data.get("reports") or []


def get_report(report_id: str) -> dict[str, Any]:
    if not report_id:
        raise ValidationError("report_id 不能为空")
    client = VercelBlobClient()
    blob = client.head(_report_path(report_id))
    if not blob or not blob.url:
        raise ExternalAPIError(f"找不到报告: {report_id}")
    resp = httpx.get(blob.url, timeout=httpx.Timeout(15.0))
    if resp.status_code >= 400:
        raise ExternalAPIError(f"读取报告失败 ({resp.status_code}): {report_id}")
    return resp.json()


def delete_report(report_id: str) -> dict[str, Any]:
    if not report_id:
        raise ValidationError("report_id 不能为空")
    client = VercelBlobClient()
    blob = client.head(_report_path(report_id))
    if blob and blob.url:
        client.delete(blob.url)
    _optimistic_update(client, lambda idx: {"reports": [r for r in (idx.get("reports") or []) if r.get("id") != report_id]})
    return {"success": True, "report_id": report_id}
```

- [ ] **Step 2: 写 `mcp/tests/test_html_reports.py`**

```python
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
    monkeypatch.setattr(h, "get_env", lambda *k: {"VERCEL_REPORTS_URL": "https://app.example.com"})
    # 让 etag 一致性循环一次命中（公开读 etag == head etag）
    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(200, text='{"reports": []}', headers={"etag": '"idx1"'}))

    r = h.publish_report(REPORT, "r1")
    assert r.url == "https://app.example.com/report/r1"
    assert r.report_id == "r1"
    assert calls["put"][0] == "html-reports/r1.json"      # 先写报告
    assert calls["put"][1] == h.INDEX_PATH                # 再写索引
    # 索引条目含 title/tags/created_at
    assert "r1" in json.loads(open  # noqa  (占位，真实断言见下)


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
    monkeypatch.setattr(h, "get_env", lambda *k: {"VERCEL_REPORTS_URL": "https://app"})
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
    monkeypatch.setattr(h, "get_env", lambda *k: {"VERCEL_REPORTS_URL": "https://app"})
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
    monkeypatch.setattr(h, "get_env", lambda *k: {"VERCEL_REPORTS_URL": "https://app"})
    monkeypatch.setattr(h.httpx, "get", lambda url, timeout=None: _FakeResp(200, text='{"reports": []}', headers={"etag": '"idx1"'}))
    with pytest.raises(ExternalAPIError):
        h.publish_report(REPORT, "r1")
```

> 注：Step 2 的 `test_publish_writes_report_then_index` 末尾有一行错误占位（`assert ... open  # noqa`），实现时**删掉那行占位**，断言以 `test_publish_index_entry_has_fields` 为准（它已精确校验条目字段）。两个用例都保留。

- [ ] **Step 3: 运行**

```bash
cd mcp && python -m pytest tests/test_html_reports.py -v
```
Expected: 6 passed。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/building_reports/html_reports.py mcp/tests/test_html_reports.py
git commit -m "feat(mcp): building_reports html reports (publish/list/get/delete + optimistic-lock index)"
```

---

## Task 3: image_gen.py —— apimart gpt-image-2 异步图片生成

**Files:**
- Create: `mcp/sda_mcp/skills/building_reports/image_gen.py`
- Test: `mcp/tests/test_image_gen.py`

- [ ] **Step 1: 写 `image_gen.py`**

```python
"""图片生成内核：apimart gpt-image-2 异步生成，移植 building-reports/scripts/image/image.js。

异步三步：submit（拿 task_id）→ poll 到终态（completed/failed/cancelled）→ download 字节。
generate 一键到底；submit/get_image_status 提供断点续跑。

去 CLI/三态/{ok}/落盘（MCP 无共享磁盘，图片字节回内存）；返回 dataclass。
失败抛 ConfigError(缺凭证)/ExternalAPIError(HTTP)/ValidationError(参数)。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from sda_mcp.config import get_env
from sda_mcp.errors import ConfigError, ExternalAPIError, SkillTimeoutError, ValidationError

DEFAULT_BASE_URL = "https://api.apimart.ai/v1"
IMAGES_PATH = "/images/generations"
POLL_INITIAL_DELAY_S = 12.0
POLL_INTERVAL_S = 4.0
POLL_TIMEOUT_S = 180.0
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
MODEL_DEFAULT = "gpt-image-2"
VALID_MODELS = {"gpt-image-2", "gpt-image-2-official"}
PARAM_MATRIX = {
    "gpt-image-2": ["prompt", "model", "size", "resolution", "n", "image_urls", "official_fallback"],
    "gpt-image-2-official": ["prompt", "model", "size", "resolution", "quality", "background",
                             "moderation", "output_format", "output_compression", "n", "image_urls", "mask_url"],
}
_TIMEOUT = httpx.Timeout(60.0)


@dataclass
class SubmitResult:
    task_id: str
    cost: float | None


@dataclass
class ImageResult:
    url: str
    data: bytes | None = None        # 下载后的字节（失败为 None）
    error: str | None = None


@dataclass
class ImageStatusResult:
    task_id: str
    status: str
    cost: float | None = None
    images: list[str] = field(default_factory=list)   # 图片 URL
    error: str | None = None


@dataclass
class ImageGenResult:
    task_id: str
    cost: float | None
    status: str
    images: list[ImageResult]


def build_request_body(prompt: str, **opts: Any) -> dict[str, Any]:
    """按模型白名单构造请求体。移植 image.js buildRequestBody（纯函数）。"""
    model = opts.get("model", MODEL_DEFAULT)
    if model not in VALID_MODELS:
        raise ValidationError(f"不支持的 model: {model}，可选: {' / '.join(sorted(VALID_MODELS))}")
    if not isinstance(prompt, str) or not prompt:
        raise ValidationError("prompt 必填且为字符串")
    candidates = {
        "prompt": prompt, "model": model,
        "size": opts.get("size", "1:1"), "resolution": opts.get("resolution", "1k"),
        "quality": opts.get("quality", "auto"), "background": opts.get("background", "auto"),
        "moderation": opts.get("moderation", "auto"), "output_format": opts.get("output_format", "png"),
        "output_compression": opts.get("output_compression"), "n": opts.get("n", 1),
        "image_urls": opts.get("image_urls"), "mask_url": opts.get("mask_url"),
        "official_fallback": opts.get("official_fallback"),
    }
    if model == "gpt-image-2" and candidates["n"] != 1:
        raise ValidationError("gpt-image-2 模型只支持 n=1；如需多张请用 model='gpt-image-2-official'")
    return {k: v for k in PARAM_MATRIX[model] if (v := candidates.get(k)) is not None}


class ImageClient:
    def __init__(self) -> None:
        env = get_env("APIMART_API_KEY", "APIMART_BASE_URL")
        self._api_key = env["APIMART_API_KEY"]
        if not self._api_key:
            raise ConfigError("APIMART_API_KEY 未配置")
        self._base_url = (env.get("APIMART_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

    def _headers(self, json_body: bool = False) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self._api_key}"}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def submit(self, body: dict[str, Any]) -> tuple[str, Any]:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(f"{self._base_url}{IMAGES_PATH}",
                               headers=self._headers(json_body=True), json=body)
        if resp.status_code == 401:
            raise ExternalAPIError("APIMART_API_KEY 无效")
        text = resp.text
        if resp.status_code >= 400:
            raise ExternalAPIError(f"提交失败 ({resp.status_code}): {text[:500]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ExternalAPIError(f"提交失败：响应非 JSON ({resp.status_code}): {text[:500]}") from exc
        d = data.get("data")
        task_id = d[0].get("task_id") if isinstance(d, list) else (d.get("task_id") if isinstance(d, dict) else None)
        if not task_id:
            raise ExternalAPIError(f"未返回 task_id: {str(data)[:500]}")
        return task_id, data

    def get_status(self, task_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(f"{self._base_url}/tasks/{task_id}",
                              headers=self._headers(), params={"language": "zh"})
        if resp.status_code >= 400:
            raise ExternalAPIError(f"查询任务失败 ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        return data.get("data") or data

    def poll(self, task_id: str) -> tuple[str, dict[str, Any]]:
        """轮询到终态或超时。移植 image.js pollUntilTerminal。"""
        time.sleep(POLL_INITIAL_DELAY_S)
        deadline = time.monotonic() + POLL_TIMEOUT_S
        while True:
            task_data = self.get_status(task_id)
            status = task_data.get("status")
            if status in TERMINAL_STATUSES:
                return status, task_data
            if time.monotonic() > deadline:
                raise SkillTimeoutError(
                    f"轮询超时 ({POLL_TIMEOUT_S:.0f}s)，task_id={task_id}，可手动复查: GET /v1/tasks/{task_id}")
            time.sleep(POLL_INTERVAL_S)

    @staticmethod
    def _image_urls(task_data: dict[str, Any]) -> list[str]:
        out = []
        for im in (task_data.get("result") or {}).get("images") or []:
            u = im.get("url")
            if isinstance(u, list):
                u = u[0] if u else None
            if u:
                out.append(u)
        return out

    def download(self, url: str) -> bytes:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url)
        if resp.status_code >= 400:
            raise ExternalAPIError(f"下载失败 ({resp.status_code}): {url}")
        return resp.content


def submit_image(prompt: str, **opts: Any) -> SubmitResult:
    body = build_request_body(prompt, **opts)
    task_id, raw = ImageClient().submit(body)
    d = raw.get("data")
    cost = d[0].get("cost") if isinstance(d, list) else (d.get("cost") if isinstance(d, dict) else None)
    return SubmitResult(task_id=task_id, cost=cost)


def get_image_status(task_id: str) -> ImageStatusResult:
    if not task_id:
        raise ValidationError("task_id 不能为空")
    client = ImageClient()
    status, task_data = client.poll(task_id)
    result = ImageStatusResult(task_id=task_id, status=status, cost=task_data.get("cost"))
    if status == "completed":
        result.images = client._image_urls(task_data)
    else:
        result.error = ((task_data.get("error") or {}).get("message")) or f"任务未完成: {status}"
    return result


def generate_image(prompt: str, **opts: Any) -> ImageGenResult:
    body = build_request_body(prompt, **opts)
    client = ImageClient()
    task_id, _ = client.submit(body)
    status, task_data = client.poll(task_id)
    if status != "completed":
        err = ((task_data.get("error") or {}).get("message")) or f"任务状态 {status}"
        raise ExternalAPIError(f"图片生成失败: {err} (task_id={task_id})")
    urls = client._image_urls(task_data)
    if not urls:
        raise ExternalAPIError(f"任务完成但无图片: {str(task_data)[:300]}")
    images: list[ImageResult] = []
    for u in urls:
        entry = ImageResult(url=u)
        try:
            entry.data = client.download(u)
        except ExternalAPIError as exc:
            entry.error = str(exc)
        images.append(entry)
    return ImageGenResult(task_id=task_id, cost=task_data.get("cost"), status=status, images=images)
```

- [ ] **Step 2: 写 `mcp/tests/test_image_gen.py`**

```python
"""image_gen mock 单元测试（离线）。"""
import json
import pytest
from sda_mcp.errors import ConfigError, ExternalAPIError, SkillTimeoutError, ValidationError
from sda_mcp.skills.building_reports import image_gen as ig


class _FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.text = "" if body is None else (body if isinstance(body, str) else json.dumps(body))
        self.content = self.text.encode() if isinstance(self.text, str) else self.text
    def json(self):
        return json.loads(self.text)


class _FakeHttpxClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def _pop(self, method, url, **kw):
        self.calls.append({"method": method, "url": url, **kw})
        return self._responses.pop(0)
    def post(self, url, headers=None, json=None, **k):
        return self._pop("POST", url, headers=headers, json=json)
    def get(self, url, headers=None, params=None, **k):
        return self._pop("GET", url, headers=headers, params=params)


def _wire(monkeypatch, responses):
    holder = {}
    def _factory(*a, **k):
        holder["client"] = _FakeHttpxClient(responses)
        return holder["client"]
    monkeypatch.setattr(ig.httpx, "Client", _factory)
    return holder


def _client(monkeypatch):
    monkeypatch.setattr(ig.ImageClient, "__init__",
                        lambda self: (setattr(self, "_api_key", "k"), setattr(self, "_base_url", "https://api"))[1])
    return ig.ImageClient()


def test_missing_api_key_raises(monkeypatch):
    import sda_mcp.config as cfg
    monkeypatch.setattr(cfg, "load_config", lambda: {"env": {"APIMART_BASE_URL": "x"}})
    with pytest.raises(ConfigError):
        ig.ImageClient()


def test_build_body_whitelist_and_n_constraint():
    body = ig.build_request_body("海报", model="gpt-image-2", size="16:9")
    assert body["model"] == "gpt-image-2" and body["size"] == "16:9"
    assert "quality" not in body                      # gpt-image-2 白名单不含 quality
    with pytest.raises(ValidationError):
        ig.build_request_body("海报", model="gpt-image-2", n=2)
    with pytest.raises(ValidationError):
        ig.build_request_body("海报", model="bad")
    with pytest.raises(ValidationError):
        ig.build_request_body("")


def test_build_body_official_allows_quality():
    body = ig.build_request_body("海报", model="gpt-image-2-official", quality="high", n=3)
    assert body["quality"] == "high" and body["n"] == 3


def test_submit_extracts_task_id(monkeypatch):
    holder = _wire(monkeypatch, [_FakeResp(200, body={"data": [{"task_id": "tk1", "cost": 0.1}]})])
    c = _client(monkeypatch)
    task_id, raw = c.submit({"prompt": "x"})
    assert task_id == "tk1"
    assert holder["client"].calls[0]["url"] == "https://api" + ig.IMAGES_PATH


def test_submit_401(monkeypatch):
    _wire(monkeypatch, [_FakeResp(401, body="nope")])
    c = _client(monkeypatch)
    with pytest.raises(ExternalAPIError):
        c.submit({"prompt": "x"})


def test_poll_loops_until_terminal(monkeypatch):
    monkeypatch.setattr(ig, "POLL_INITIAL_DELAY_S", 0)
    monkeypatch.setattr(ig, "POLL_INTERVAL_S", 0)
    responses = [_FakeResp(200, body={"data": {"status": "running"}}),
                 _FakeResp(200, body={"data": {"status": "completed", "cost": 0.2,
                              "result": {"images": [{"url": ["https://img/a.png"]}]}}})]
    _wire(monkeypatch, responses)
    c = _client(monkeypatch)
    status, data = c.poll("tk")
    assert status == "completed"


def test_poll_timeout(monkeypatch):
    monkeypatch.setattr(ig, "POLL_INITIAL_DELAY_S", 0)
    monkeypatch.setattr(ig, "POLL_INTERVAL_S", 0)
    monkeypatch.setattr(ig, "POLL_TIMEOUT_S", 0)
    _wire(monkeypatch, [_FakeResp(200, body={"data": {"status": "running"}})])
    c = _client(monkeypatch)
    with pytest.raises(SkillTimeoutError):
        c.poll("tk")


def test_generate_end_to_end(monkeypatch):
    monkeypatch.setattr(ig, "POLL_INITIAL_DELAY_S", 0)
    monkeypatch.setattr(ig, "POLL_INTERVAL_S", 0)
    responses = [
        _FakeResp(200, body={"data": [{"task_id": "tk1"}]}),                          # submit
        _FakeResp(200, body={"data": {"status": "completed", "cost": 0.3,
                     "result": {"images": [{"url": "https://img/a.png"}]}}}),         # poll
        _FakeResp(200, body=b"\x89PNG\r\n\x1a\n"),                                    # download
    ]
    _wire(monkeypatch, responses)
    monkeypatch.setattr(ig.ImageClient, "__init__",
                        lambda self: (setattr(self, "_api_key", "k"), setattr(self, "_base_url", "https://api"))[1])
    r = ig.generate_image("海报", size="16:9")
    assert r.task_id == "tk1" and r.cost == 0.3 and r.status == "completed"
    assert r.images[0].url == "https://img/a.png"
    assert r.images[0].data == b"\x89PNG\r\n\x1a\n"
    assert r.images[0].error is None


def test_generate_failed_task_raises(monkeypatch):
    monkeypatch.setattr(ig, "POLL_INITIAL_DELAY_S", 0)
    monkeypatch.setattr(ig, "POLL_INTERVAL_S", 0)
    responses = [_FakeResp(200, body={"data": [{"task_id": "tk1"}]}),
                 _FakeResp(200, body={"data": {"status": "failed",
                     "error": {"message": "内容违规"}}})]
    _wire(monkeypatch, responses)
    monkeypatch.setattr(ig.ImageClient, "__init__",
                        lambda self: (setattr(self, "_api_key", "k"), setattr(self, "_base_url", "https://api"))[1])
    with pytest.raises(ExternalAPIError) as ei:
        ig.generate_image("海报")
    assert "内容违规" in str(ei.value)
```

> 注：`_FakeResp.content` 在 `body` 为 bytes 时直接取该 bytes（`_FakeResp(200, body=b"\x89PNG...")` → text 为 bytes，content 即该 bytes）。实现时确认 `_FakeResp` 对 bytes body 的处理：上面构造 `self.content = ... if isinstance(self.text,str) else self.text` 已兼容（body 为 bytes 时 json() 不会被调用，仅 download 路径读 `.content`）。

- [ ] **Step 3: 运行**

```bash
cd mcp && python -m pytest tests/test_image_gen.py -v
```
Expected: 9 passed。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/building_reports/image_gen.py mcp/tests/test_image_gen.py
git commit -m "feat(mcp): building_reports image generation (apimart gpt-image-2 async)"
```

---

## Task 4: 导出 + 全量测试

- [ ] **Step 1: 写 `mcp/sda_mcp/skills/building_reports/__init__.py`**

```python
"""building_reports 内核：HTML 报告（Vercel Blob）+ 图片生成（apimart）。streamlit 已砍。"""
from sda_mcp.skills.building_reports.html_reports import (
    PublishResult, publish_report, list_reports, get_report, delete_report,
)
from sda_mcp.skills.building_reports.image_gen import (
    SubmitResult, ImageResult, ImageStatusResult, ImageGenResult,
    submit_image, get_image_status, generate_image,
)

__all__ = [
    "PublishResult", "publish_report", "list_reports", "get_report", "delete_report",
    "SubmitResult", "ImageResult", "ImageStatusResult", "ImageGenResult",
    "submit_image", "get_image_status", "generate_image",
]
```

- [ ] **Step 2: 更新 `mcp/sda_mcp/skills/__init__.py` 导出**

在现有 import 之后追加：

```python
from sda_mcp.skills.building_reports import (
    publish_report, list_reports, get_report, delete_report,
    submit_image, get_image_status, generate_image,
)
```

并把 `publish_report, list_reports, get_report, delete_report, submit_image, get_image_status, generate_image` 加入 `__all__`。

- [ ] **Step 3: 全量测试**

```bash
cd mcp && python -m pytest -q
```
Expected: 全绿（原 51 + building_reports 8+6+9 = 74）。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/building_reports/__init__.py mcp/sda_mcp/skills/__init__.py
git commit -m "feat(mcp): export building_reports core APIs"
```

- [ ] **Step 5: 铁律校验**

```bash
git diff -- building-reports/ | head
```
Expected: 无输出（原目录零改动）。

---

## 可选集成对照（env-gated，默认跳过）

仅当 `SDA_INTEGRATION=1` 且凭证齐全时手动运行，验证 Python 内核与原 Node CLI 行为一致。

**HTML 报告对照**（`mcp/tests/test_building_reports_integration.py`，`pytest.mark.skipif` 门控）：
- 用唯一 id（如 `sda-mcp-parity-<时间戳>`）分别经 Python `publish_report` 与 Node `report.js html publish` 各发布一份 → `get_report` 双方取回比对 title/tags → 最后 `delete_report` 清理。
- 受 CDN 60s 缓存影响，list 一致性需在发布后等待/重试。

**图片生成对照**（会产生真实 apimart 计费，谨慎运行）：
- `submit_image` 拿 task_id → `get_image_status` 轮询到 completed → 校验返回 images URL，与 Node `image.js submit/status` 一致。

> 这些集成测试默认 `skip`，不计入全量。需要时单独 `SDA_INTEGRATION=1 python -m pytest tests/test_building_reports_integration.py`。

---

## 完成标准

- [ ] `building_reports/` 子包：blob_store（put/head/delete）、html_reports（publish/list/get/delete + etag 一致性 + ifMatch 乐观锁）、image_gen（submit/status/generate）。
- [ ] 去 CLI/三态/落盘/`{ok}`；失败抛 SkillError 子类。
- [ ] Vercel Blob REST 契约与 @vercel/blob SDK 一致（base/storeId/头/方法已核实）。
- [ ] mock 单元测试：blob_store 8、html_reports 6、image_gen 9，全绿。
- [ ] 全量测试通过（74）。
- [ ] 原 `building-reports/` 零改动（`git diff -- building-reports` 无输出）。
