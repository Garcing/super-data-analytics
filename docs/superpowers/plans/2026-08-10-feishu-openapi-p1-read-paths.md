# 飞书开放平台 API 替换 lark-cli — P1（读/删路径）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 `FeishuClient`（httpx + tenant_access_token），替换三个内核里所有 lark-cli 的**读/删**调用（docx→markdown 读、drive 列表/删除、bitable 字段/记录），读路径已用真实文档验证。

**Architecture:** 单一共享 `FeishuClient` 类（`mcp/sda_mcp/feishu.py`），对齐现有 `VercelBlobClient` 模式（httpx + `_headers` + 抛 `ConfigError`/`ExternalAPIError` + dataclass）。token 用模块级缓存（FastMCP stateless，跨调用复用必须模块级）。三个内核（`using_templates`/`retrieving_context`/`retrieving_context_sync`）改为 import 它。P1 只动读/删；create/update 仍暂留 `LarkCliClient`（P2 再迁）。lark-cli 仍在镜像里（P3 才物理删）。

**Tech Stack:** Python 3.12、httpx（已是依赖）、pytest（mock `_request`/httpx）、飞书开放平台 REST（`docs/v1/content`、`drive/v1/files`、`bitable/v1/.../fields|records`、`auth/v3/tenant_access_token/internal`）。

**设计依据：** `docs/superpowers/specs/2026-08-10-feishu-openapi-replace-lark-cli-design.md`

**铁律：** 原skill 目录树零改动；所有新代码只放 `mcp/`。`cd mcp && python -m pytest -q` 必须全绿。

---

## 文件结构

| 文件 | 责任 | 本计划动作 |
|---|---|---|
| `mcp/sda_mcp/feishu.py` | 飞书开放平台 REST 客户端（token + 5 个读/删端点） | **新建** |
| `mcp/tests/test_feishu.py` | FeishuClient 单元测试 | **新建** |
| `mcp/sda_mcp/skills/retrieving_context.py` | `doc()` 改用 `get_doc_markdown` | 修改（删 lark-cli 子进程段） |
| `mcp/tests/test_retrieving_context.py` | `doc()` 测试改 mock `FeishuClient` | 修改 |
| `mcp/sda_mcp/skills/retrieving_context_sync.py` | `fetch_table_fields/records` 改用 `FeishuClient`，删 `_lark_cli`/`_extract_cell` | 修改 |
| `mcp/tests/test_retrieving_context_sync.py` | fetch 测试改 mock `FeishuClient`，用开放平台数据结构 | 修改 |
| `mcp/sda_mcp/skills/using_templates.py` | `list/read/delete_template` 改用 `FeishuClient`（create/update 暂留 `LarkCliClient`） | 修改 |
| `mcp/tests/test_using_templates.py` | list/read/delete 测试改 mock `FeishuClient` | 修改 |

**FeishuClient 接口契约（本计划最终形态）：**
```python
class FeishuClient:
    def get_doc_markdown(self, doc_token: str) -> str            # docs/v1/content
    def list_folder_files(self, folder_token: str) -> list[dict] # drive/v1/files（翻页）
    def delete_file(self, file_token: str, file_type: str = "docx") -> None  # drive/v1/files DELETE
    def list_bitable_fields(self, app_token: str, table_id: str) -> list[dict]   # bitable fields（原始）
    def list_bitable_records(self, app_token: str, table_id: str) -> list[dict]  # bitable records（原始，翻页）
```
模块级：`_get_tenant_token() -> str`（缓存）、`_reset_token_cache()`（测试用）、bitable 字段类型常量。

---

## Task 1: FeishuClient 骨架 — token 缓存 + _request + _check

**Files:**
- Create: `mcp/sda_mcp/feishu.py`
- Test: `mcp/tests/test_feishu.py`

- [ ] **Step 1: 写失败测试（token 缓存 + 刷新 + 失败）**

`mcp/tests/test_feishu.py`:
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_feishu.py -v`
Expected: FAIL（`ModuleNotFoundError: sda_mcp.feishu`）

- [ ] **Step 3: 写最小实现**

`mcp/sda_mcp/feishu.py`:
```python
"""飞书开放平台 REST 客户端（httpx 直连，tenant_access_token 鉴权）。

替代 lark-cli 子进程的读/删调用：docx→markdown、drive 文件列表/删除、bitable 字段/记录。
对齐 VercelBlobClient 模式：失败抛 ConfigError(缺凭证)/ExternalAPIError(HTTP/code!=0)。

接口契约见 docs/superpowers/specs/2026-08-10-feishu-openapi-replace-lark-cli-design.md。
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from sda_mcp.config import get_env
from sda_mcp.errors import ConfigError, ExternalAPIError

_FEISHU_BASE = "https://open.feishu.cn"
_TIMEOUT = httpx.Timeout(30.0)
_TOKEN_REFRESH_MARGIN = 300  # 过期前 5 分钟刷新

# bitable 字段类型（开放平台用 int；lark-cli 用字符串名）
_F_TEXT = 1
_F_NUMBER = 2
_F_SINGLE_SELECT = 3
_F_MULTI_SELECT = 4
_F_DATE = 5
_F_CHECKBOX = 7
_F_AUTO_NUMBER = 1005

# 模块级 token 缓存：FastMCP stateless 每次调用新建 client 实例，
# 跨调用复用 token 必须模块级。冗余并发刷新无害，不加锁。
_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def _reset_token_cache() -> None:
    """仅供测试：清 token 缓存。"""
    _token_cache["token"] = None
    _token_cache["expires_at"] = 0.0


def _get_tenant_token() -> str:
    """返回 tenant_access_token；模块级缓存，剩 ≤5min 刷新。"""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]
    env = get_env("FEISHU_APP_ID", "FEISHU_APP_SECRET")
    try:
        resp = httpx.post(
            f"{_FEISHU_BASE}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise ExternalAPIError(f"获取 tenant_access_token 失败: {exc}") from exc
    if data.get("code") != 0:
        raise ExternalAPIError(f"获取 tenant_access_token 失败: {data.get('msg')}")
    token = data.get("tenant_access_token")
    if not token:
        raise ExternalAPIError("tenant_access_token 响应缺 token 字段")
    expire = int(data.get("expire", 7200))
    _token_cache["token"] = token
    _token_cache["expires_at"] = time.time() + expire - _TOKEN_REFRESH_MARGIN
    return token


class FeishuClient:
    """飞书开放平台 REST 客户端。"""

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                 json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        token = _get_tenant_token()
        try:
            resp = httpx.request(
                method, f"{_FEISHU_BASE}{path}", params=params, json=json_body,
                headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise ExternalAPIError(f"飞书 API {method} {path} 失败: {exc}") from exc

    @staticmethod
    def _check(data: dict[str, Any], path: str) -> None:
        if data.get("code") != 0:
            msg = data.get("msg") or data.get("message") or "未知错误"
            raise ExternalAPIError(f"飞书 API {path} 返回错误: {str(msg)[:300]}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_feishu.py -v`
Expected: PASS（6 个测试）

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/feishu.py mcp/tests/test_feishu.py
git commit -m "feat(mcp): FeishuClient 骨架 — tenant token 缓存 + _request/_check"
```

---

## Task 2: get_doc_markdown（docx → markdown 读）

**Files:**
- Modify: `mcp/sda_mcp/feishu.py`（加方法）
- Test: `mcp/tests/test_feishu.py`（加测试）

- [ ] **Step 1: 写失败测试**

追加到 `mcp/tests/test_feishu.py`：
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k get_doc_markdown -v`
Expected: FAIL（`AttributeError: get_doc_markdown`）

- [ ] **Step 3: 加实现**

在 `FeishuClient` 类内（`_check` 之后）追加：
```python
    # --- docx → markdown（读）---
    def get_doc_markdown(self, doc_token: str) -> str:
        """读 docx 文档为 markdown。GET /open-apis/docs/v1/content。"""
        path = "/open-apis/docs/v1/content"
        data = self._request("GET", path, params={
            "doc_token": doc_token, "doc_type": "docx", "content_type": "markdown"})
        self._check(data, path)
        content = (data.get("data") or {}).get("content")
        if content is None:
            raise ExternalAPIError(f"飞书文档 {doc_token} 返回缺 content")
        return content
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k get_doc_markdown -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/feishu.py mcp/tests/test_feishu.py
git commit -m "feat(mcp): FeishuClient.get_doc_markdown — docx→markdown 读路径"
```

---

## Task 3: list_folder_files（drive 文件列表，翻页）

**Files:**
- Modify: `mcp/sda_mcp/feishu.py`
- Test: `mcp/tests/test_feishu.py`

> 说明：开放平台 drive/v1/files 返回 `data.files[]`、`data.has_more`、`data.next_page_token`；bitable 用 `data.page_token`。用 `_next_token` helper 兼容两种命名。

- [ ] **Step 1: 写失败测试**

追加：
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k list_folder_files -v`
Expected: FAIL（`AttributeError`）

- [ ] **Step 3: 加实现**

在模块级（`FeishuClient` 类之前）追加 helper：
```python
def _next_token(data: dict[str, Any]) -> str | None:
    """drive 返回 next_page_token，bitable 返回 page_token；兼容两者。"""
    payload = data.get("data") or data
    return payload.get("next_page_token") or payload.get("page_token")
```

在 `FeishuClient` 类内追加：
```python
    # --- drive 文件列表（读）---
    def list_folder_files(self, folder_token: str) -> list[dict[str, Any]]:
        """列出文件夹下文件（含子文件夹）。GET /open-apis/drive/v1/files，自动翻页。"""
        path = "/open-apis/drive/v1/files"
        files: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"folder_token": folder_token, "page_size": 200}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", path, params=params)
            self._check(data, path)
            payload = data.get("data") or {}
            files.extend(payload.get("files") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return files
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k list_folder_files -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/feishu.py mcp/tests/test_feishu.py
git commit -m "feat(mcp): FeishuClient.list_folder_files — drive 文件列表翻页"
```

---

## Task 4: delete_file（drive 删除）

**Files:**
- Modify: `mcp/sda_mcp/feishu.py`
- Test: `mcp/tests/test_feishu.py`

- [ ] **Step 1: 写失败测试**

追加：
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k delete_file -v`
Expected: FAIL（`AttributeError`）

- [ ] **Step 3: 加实现**

在 `FeishuClient` 类内追加：
```python
    # --- drive 删除 ---
    def delete_file(self, file_token: str, file_type: str = "docx") -> None:
        """删除文件。DELETE /open-apis/drive/v1/files/{file_token}?type=。"""
        path = f"/open-apis/drive/v1/files/{file_token}"
        data = self._request("DELETE", path, params={"type": file_type})
        self._check(data, path)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k delete_file -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/feishu.py mcp/tests/test_feishu.py
git commit -m "feat(mcp): FeishuClient.delete_file — drive 文件删除"
```

---

## Task 5: list_bitable_fields（多维表字段，原始）

**Files:**
- Modify: `mcp/sda_mcp/feishu.py`
- Test: `mcp/tests/test_feishu.py`

> 说明：开放平台返回 `data.items[]`，字段为 `field_id`/`field_name`/`type`(int)/`ui_type`。client 返回**原始**列表（不做 domain 过滤），过滤 auto_number 等域逻辑留给 sync 层。

- [ ] **Step 1: 写失败测试**

追加：
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k list_bitable_fields -v`
Expected: FAIL（`AttributeError`）

- [ ] **Step 3: 加实现**

在 `FeishuClient` 类内追加：
```python
    # --- bitable 字段（读，原始）---
    def list_bitable_fields(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        """列出多维表字段（原始，含 auto_number；domain 过滤由调用方做）。"""
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", path, params=params)
            self._check(data, path)
            payload = data.get("data") or {}
            items.extend(payload.get("items") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return items
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k list_bitable_fields -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/feishu.py mcp/tests/test_feishu.py
git commit -m "feat(mcp): FeishuClient.list_bitable_fields — 多维表字段（原始）"
```

---

## Task 6: list_bitable_records（多维表记录，原始 + 翻页）

**Files:**
- Modify: `mcp/sda_mcp/feishu.py`
- Test: `mcp/tests/test_feishu.py`

> 说明：开放平台返回 `data.items[]`，每条 `{record_id, fields:{字段名: 值}}`；值结构因字段类型而异（text=`[{text:..}]`、select=字符串或对象、multi=list）。client 返回**原始** items；值简化（`_simplify_value`）留给 sync 层（Task 8）。

- [ ] **Step 1: 写失败测试**

追加：
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_feishu.py -k list_bitable_records -v`
Expected: FAIL（`AttributeError`）

- [ ] **Step 3: 加实现**

在 `FeishuClient` 类内追加：
```python
    # --- bitable 记录（读，原始）---
    def list_bitable_records(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        """列多维表记录（原始 items，含 record_id + fields map；值简化由调用方做）。"""
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", path, params=params)
            self._check(data, path)
            payload = data.get("data") or {}
            items.extend(payload.get("items") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return items
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_feishu.py -v`
Expected: PASS（全部 test_feishu.py）

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/feishu.py mcp/tests/test_feishu.py
git commit -m "feat(mcp): FeishuClient.list_bitable_records — 多维表记录翻页"
```

---

## Task 7: 改 retrieving_context.doc() 用 FeishuClient

**Files:**
- Modify: `mcp/sda_mcp/skills/retrieving_context.py`（`doc()` 函数，约 L277-302）
- Test: `mcp/tests/test_retrieving_context.py`

> 现状：`doc()` 子进程调 `lark-cli docs +fetch`，解析 `{data:{document}}`。改为 `FeishuClient().get_doc_markdown(doc_id)`，返回 `{content: markdown}`（保持 `doc()` 出参契约为 dict）。先看现有 doc 测试。

- [ ] **Step 1: 读现有 doc 测试，确定要保留的断言**

Run: `cd mcp && grep -n "def test.*doc\|\.doc(\|retrieve_doc" tests/test_retrieving_context.py`
查看现有 doc 相关测试（若 mock 了 subprocess，需改成 mock FeishuClient）。

- [ ] **Step 2: 写/改失败测试**

在 `mcp/tests/test_retrieving_context.py` 找到 doc 的测试（或新增），改为 mock `FeishuClient`：
```python
import sda_mcp.skills.retrieving_context as rc


def test_doc_returns_markdown(monkeypatch):
    monkeypatch.setattr(rc.FeishuClient, "get_doc_markdown",
                        lambda self, tok: "# 标题\n正文")
    out = rc.doc("DOCTOKEN")
    assert out["content"] == "# 标题\n正文"
    # 出参契约仍是 dict（retrieve_doc 工具直接返回）


def test_doc_empty_id_raises():
    from sda_mcp.errors import ValidationError
    with pytest.raises(ValidationError):
        rc.doc("")
```
> 若文件顶部已有 `import pytest` 和 `from sda_mcp.errors import ...`，勿重复 import。

- [ ] **Step 3: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_retrieving_context.py -k doc -v`
Expected: FAIL（`doc()` 仍走 subprocess，或 `rc.FeishuClient` 不存在）

- [ ] **Step 4: 改实现**

在 `mcp/sda_mcp/skills/retrieving_context.py`：
1. 顶部 import 改：删 `import os`、`import shutil`、`import subprocess`（若仅 doc 用；grep 确认无其他用途），加 `from sda_mcp.feishu import FeishuClient`。
2. 替换整个 `doc()` 函数为：
```python
def doc(doc_id: str) -> dict[str, Any]:
    """读取飞书 docx 文档为 markdown。"""
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValidationError("doc 不能为空")
    content = FeishuClient().get_doc_markdown(doc_id)
    return {"content": content, "document_id": doc_id}
```
> 若 `import json` 仅 doc 用且别处不用，一并删（grep 确认）。`Any` 已在文件顶部 import。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_retrieving_context.py -v`
Expected: PASS（含改写后的 doc 测试，其余 retrieve 测试不受影响）

- [ ] **Step 6: 提交**

```bash
git add mcp/sda_mcp/skills/retrieving_context.py mcp/tests/test_retrieving_context.py
git commit -m "refactor(mcp): retrieving_context.doc 改用 FeishuClient（去 lark-cli 子进程）"
```

---

## Task 8: 改 retrieving_context_sync 用 FeishuClient（fetch_table_fields/records + 简化器）

**Files:**
- Modify: `mcp/sda_mcp/skills/retrieving_context_sync.py`（删 `_lark_cli`、`_extract_cell`；改 `fetch_table_fields`、`fetch_table_records`）
- Test: `mcp/tests/test_retrieving_context_sync.py`

> 关键差异：开放平台用 int 字段类型（text=1/select=3/multi=4/auto_number=1005），记录值结构不同（text=`[{text:..}]`、select=字符串或 `{text}`、multi=list）。新增 `_simplify_value` 替代旧 `_extract_cell`，契约（`{字段名:简化值}`）不变 → 下游 graph_builder/embedding 不动。

- [ ] **Step 1: 写失败测试（新数据结构）**

替换 `mcp/tests/test_retrieving_context_sync.py` 里 Phase 1 的两个 fetch 测试为：
```python
import sda_mcp.skills.retrieving_context_sync as s
from sda_mcp.feishu import _F_TEXT, _F_SINGLE_SELECT, _F_MULTI_SELECT, _F_AUTO_NUMBER


def test_fetch_fields_maps_and_filters_auto_number(monkeypatch):
    """开放平台 raw fields → {name,type,id}，过滤 auto_number(1005)。"""
    monkeypatch.setattr(s.FeishuClient, "list_bitable_fields",
                        lambda self, app, tbl: [
                            {"field_id": "fid1", "field_name": "名称", "type": _F_TEXT},
                            {"field_id": "fid2", "field_name": "自增", "type": _F_AUTO_NUMBER},
                        ])
    fields = s.fetch_table_fields("APP", "tbl1")
    assert fields == [{"name": "名称", "type": _F_TEXT, "id": "fid1"}]


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
```
> 删除旧 `test_fetch_extracts_records`、`test_fetch_paginates_until_has_more_false`（它们 mock 旧 `_lark_cli` 矩阵结构）。保留文件里编排测试（`_stub_phases`/`test_sync_graph_orchestration` 等）不动。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_retrieving_context_sync.py -k "fetch_fields or fetch_records" -v`
Expected: FAIL（`FeishuClient` 未 import / 旧 `_lark_cli` 被 mock 失败）

- [ ] **Step 3: 改实现**

在 `mcp/sda_mcp/skills/retrieving_context_sync.py`：
1. 顶部 import：删 `import json`、`import shutil`、`import subprocess`（grep 确认仅 Phase1 用）。改为：
```python
from sda_mcp.config import get_env, load_config
from sda_mcp.errors import ConfigError, ExternalAPIError, ValidationError
from sda_mcp.feishu import FeishuClient
from sda_mcp.feishu import _F_AUTO_NUMBER, _F_TEXT, _F_SINGLE_SELECT, _F_MULTI_SELECT
from sda_mcp.skills.retrieving_context import Neo4jClient
```
2. 删除 `_lark_cli` 函数和 `_extract_cell` 函数（整段）。
3. 替换 `fetch_table_fields` 为：
```python
def fetch_table_fields(app_token: str, table_id: str) -> list[dict]:
    """开放平台字段 → {name,type,id}，过滤 auto_number。"""
    raw = FeishuClient().list_bitable_fields(app_token, table_id)
    return [{"name": f.get("field_name"), "type": f.get("type"), "id": f.get("field_id")}
            for f in raw if f.get("type") != _F_AUTO_NUMBER]
```
4. 在 `fetch_table_records` 之前新增值简化器：
```python
def _join_text(runs: Any) -> Any:
    """text 字段值（[{text:..}] 或字符串）→ 拼接字符串；空→None。"""
    if isinstance(runs, str):
        return runs.strip() or None
    if isinstance(runs, list):
        parts = [r.get("text", "") if isinstance(r, dict) else str(r) for r in runs]
        return "".join(parts).strip() or None
    return runs


def _opt_to_str(v: Any) -> Any:
    """单选项（字符串 或 {text:'x'}）→ 字符串；空→None。"""
    if isinstance(v, dict):
        return (v.get("text") or v.get("name") or "").strip() or None
    if isinstance(v, str):
        return v.strip() or None
    return v


def _simplify_value(field_type: int, value: Any) -> Any:
    """开放平台记录值 → graph 用的简化形式。对齐旧 _extract_cell 的输出契约。"""
    if value is None:
        return None
    if field_type == _F_TEXT:
        return _join_text(value)
    if field_type == _F_SINGLE_SELECT:
        return _opt_to_str(value)
    if field_type == _F_MULTI_SELECT:
        if isinstance(value, list):
            return [_opt_to_str(v) for v in value if _opt_to_str(v) is not None]
        v = _opt_to_str(value)
        return [v] if v is not None else None
    if isinstance(value, str):
        return value.strip() or None
    return value
```
5. 替换 `fetch_table_records` 为：
```python
def fetch_table_records(app_token: str, table_id: str, fields: list[dict] | None = None) -> list[dict]:
    """开放平台记录 → [{字段名: 简化值}, ...]，过滤 None/空字符串。"""
    if fields is None:
        fields = fetch_table_fields(app_token, table_id)
    field_types = {f["name"]: f["type"] for f in fields}
    items = FeishuClient().list_bitable_records(app_token, table_id)
    records: list[dict] = []
    for item in items:
        raw_fields = item.get("fields") or {}
        rec: dict = {}
        for name, ftype in field_types.items():
            if name in raw_fields:
                val = _simplify_value(ftype, raw_fields[name])
                if val is not None and val != "":
                    rec[name] = val
        records.append(rec)
    return records
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_retrieving_context_sync.py -v`
Expected: PASS（新 fetch 测试 + 原编排测试）

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/skills/retrieving_context_sync.py mcp/tests/test_retrieving_context_sync.py
git commit -m "refactor(mcp): sync fetch 改用 FeishuClient + 值简化器（去 lark-cli）"
```

---

## Task 9: 改 using_templates 的 list/read/delete 用 FeishuClient（create/update 暂留 LarkCliClient）

**Files:**
- Modify: `mcp/sda_mcp/skills/using_templates.py`（`list_templates`、`read_template`、`delete_template`）
- Test: `mcp/tests/test_using_templates.py`

> P1 过渡态：`list/read/delete` 走 `FeishuClient`；`create/update` 仍走 `LarkCliClient`（P2 再迁）。drive/v1/files 返回的 `token/name/type/url/modified_time` 字段名与旧 `_entry` 映射一致，entry 结构不变。

- [ ] **Step 1: 改测试（list/read/delete 改 mock FeishuClient）**

在 `mcp/tests/test_using_templates.py`：
1. 删除 `test_lark_bin_missing_raises_config`、`test_lark_nonzero_raises_external`、`test_exec_caches_identity`、`test_exec_falls_back_to_bot`（身份回退逻辑随 lark-cli 一起在 P2 删；这些测 LarkCliClient 内部，create/update 仍依赖它——**保留这 4 个**直到 P2，不删）。
   > 修正：P1 不删 LarkCliClient，这 4 个测试仍有效，**保留不动**。
2. 把 `test_list_flat_and_subfolder`、`test_list_missing_folder_token`、`test_read_parses_markdown`、`test_read_empty_doc_id`、`test_delete_*` 三个 改为 mock `FeishuClient`：
```python
import sda_mcp.skills.using_templates as t


def test_list_flat_and_subfolder(monkeypatch):
    root = [
        {"type": "docx", "token": "d1", "name": "日报", "url": "u1", "modified_time": "1"},
        {"type": "folder", "token": "f1", "name": "销售"},
    ]
    sub = [{"type": "docx", "token": "d2", "name": "周报", "url": "u2", "modified_time": "2"}]
    # 根目录 + 子目录各一次调用
    monkeypatch.setattr(t.FeishuClient, "list_folder_files",
                        lambda self, ft: root if ft == "ROOT" else sub)
    monkeypatch.setattr(t, "get_env",
                        lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "ROOT"})
    res = t.list_templates()
    assert len(res) == 2
    assert res[0] == {"id": "d1", "name": "日报", "category": "", "type": "docx",
                      "url": "u1", "modified_time": "1"}
    assert res[1]["category"] == "销售" and res[1]["id"] == "d2"


def test_list_missing_folder_token(monkeypatch):
    import sda_mcp.config as cfg
    monkeypatch.setattr(cfg, "load_config", lambda: {"env": {}})
    with pytest.raises(t.ConfigError):
        t.list_templates()


def test_read_parses_markdown(monkeypatch):
    monkeypatch.setattr(t.FeishuClient, "get_doc_markdown",
                        lambda self, doc_id: "# 标题\n正文")
    assert t.read_template("DOC") == "# 标题\n正文"


def test_read_empty_doc_id():
    with pytest.raises(t.ValidationError):
        t.read_template("")


def test_delete_password_gate_enforced(monkeypatch):
    monkeypatch.setattr(t, "load_config",
                        lambda: {"env": {"FEISHU_TEMPLATE_DELETE_PASSWORD": "secret"}})
    with pytest.raises(t.ValidationError):
        t.delete_template("DOC")
    with pytest.raises(t.ValidationError):
        t.delete_template("DOC", password="wrong")


def test_delete_calls_feishu(monkeypatch):
    monkeypatch.setattr(t, "load_config", lambda: {"env": {}})
    captured = {}
    monkeypatch.setattr(t.FeishuClient, "delete_file",
                        lambda self, tok, ft="docx": captured.update(tok=tok, ft=ft))
    r = t.delete_template("DOC")
    assert r.deleted is True and r.document_id == "DOC"
    assert captured == {"tok": "DOC", "ft": "docx"}
```
> 顶部若没有 `import pytest` 和 `from sda_mcp.errors import ...`，按需补；测试里直接用 `t.ConfigError`/`t.ValidationError`（已在 using_templates import）。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd mcp && python -m pytest tests/test_using_templates.py -k "list_flat or list_missing or read_parses or read_empty or delete" -v`
Expected: FAIL（`t.FeishuClient` 不存在 / 旧 mock 失败）

- [ ] **Step 3: 改实现**

在 `mcp/sda_mcp/skills/using_templates.py`：
1. 顶部加 `from sda_mcp.feishu import FeishuClient`。
2. 替换 `list_templates` 里 `client._list_folder(folder_token)` → `FeishuClient().list_folder_files(folder_token)`，子目录同理 `_sub` 里 `client._list_folder(...)` → `FeishuClient().list_folder_files(...)`。其余 `_entry`/分类逻辑不变。新 `list_templates`：
```python
def list_templates() -> list[dict[str, Any]]:
    """列出文件夹下文档：根目录（category 为空）+ 每个子文件夹一层。"""
    folder_token = get_env("FEISHU_TEMPLATE_FOLDER_TOKEN")["FEISHU_TEMPLATE_FOLDER_TOKEN"]
    client = FeishuClient()
    root_files = client.list_folder_files(folder_token)

    def _entry(f: dict[str, Any], category: str) -> dict[str, Any]:
        return {
            "id": f.get("token") or f.get("id"),
            "name": f.get("name"),
            "category": category,
            "type": f.get("type"),
            "url": f.get("url"),
            "modified_time": f.get("modified_time"),
        }

    results = [_entry(f, "") for f in root_files if f.get("type") in ("docx", "doc")]
    sub_folders = [f for f in root_files if f.get("type") == "folder"]

    def _sub(folder: dict[str, Any]) -> list[dict[str, Any]]:
        files = client.list_folder_files(folder.get("token") or folder.get("id"))
        return [_entry(f, folder.get("name", "")) for f in files if f.get("type") in ("docx", "doc")]

    if sub_folders:
        with ThreadPoolExecutor(max_workers=min(8, len(sub_folders))) as ex:
            for sub in ex.map(_sub, sub_folders):
                results.extend(sub)
    return results
```
3. 替换 `read_template`：
```python
def read_template(doc_id: str) -> str:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    return FeishuClient().get_doc_markdown(doc_id)
```
4. 替换 `delete_template` 末尾的 `client._exec(["drive", "+delete", ...])` 为 `FeishuClient().delete_file(doc_id, "docx")`：
```python
def delete_template(doc_id: str, password: str | None = None) -> DeleteResult:
    if not doc_id:
        raise ValidationError("doc_id 不能为空")
    env_password = (load_config().get("env", {}) or {}).get("FEISHU_TEMPLATE_DELETE_PASSWORD")
    if env_password:
        if not password:
            raise ValidationError("需要密码（已设置 FEISHU_TEMPLATE_DELETE_PASSWORD）")
        if password != env_password:
            raise ValidationError("密码错误")
    FeishuClient().delete_file(doc_id, "docx")
    return DeleteResult(deleted=True, document_id=doc_id)
```
> `LarkCliClient` 类及 `create_template`/`update_template` **保持不动**（P2 处理）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd mcp && python -m pytest tests/test_using_templates.py -v`
Expected: PASS（含保留的 LarkCliClient 4 测试 + 改写的 list/read/delete 测试 + create/update 测试）

- [ ] **Step 5: 提交**

```bash
git add mcp/sda_mcp/skills/using_templates.py mcp/tests/test_using_templates.py
git commit -m "refactor(mcp): using_templates list/read/delete 改用 FeishuClient（create/update 暂留）"
```

---

## Task 10: 全量回归 + config.json 凭证 + 集成冒烟

**Files:**
- Modify: 宿主 `~/.super-data-analytics/config.json`（加 `FEISHU_APP_ID`/`FEISHU_APP_SECRET`，**手动**，不进 git）

- [ ] **Step 1: 全量单元测试**

Run: `cd mcp && python -m pytest -q`
Expected: 全绿。用例数应 ≥ 原 110（新增 test_feishu.py，改写部分等价）。

- [ ] **Step 2: 写入飞书凭证到 config.json**

手动编辑 `~/.super-data-analytics/config.json`，在 `env` 块加：
```json
"FEISHU_APP_ID": "cli_a61c7f2cca7e900d",
"FEISHU_APP_SECRET": "<用户提供>"
```
> secret 由用户持有，不写进本仓库。CLAUDE.md 已说明凭证唯一来源是 config.json。

- [ ] **Step 3: 集成冒烟（可选，真实 token）**

Run（需服务器/本机有真实 config.json 且应用已授权）:
```bash
cd mcp && SDA_INTEGRATION=1 python -m pytest tests/test_retrieving_context_integration.py tests/test_querying_data_integration.py -q
```
> 若没有 P1 专属集成测试，临时手验：
```bash
cd mcp && python -c "
from sda_mcp.feishu import FeishuClient
c = FeishuClient()
print('token ok')
print(c.get_doc_markdown('<一个真实 docx token>')[:80])
print(len(c.list_folder_files('<FEISHU_TEMPLATE_FOLDER_TOKEN>')), 'files')
"
```
Expected: 打印 token、文档 markdown 前 80 字（应与 lark-cli 输出一致）、模板文件数。
> 若 token 获取失败 → 检查 config.json 的 APP_ID/SECRET；若 `code!=0` 权限错 → 确认文档/多维表已共享给应用。

- [ ] **Step 4: 提交（测试/文档若有微调）**

```bash
git add -A
git commit -m "test(mcp): P1 全量回归通过（FeishuClient 替换 lark-cli 读/删路径）"
```

---

## 完成标准（P1）

- `cd mcp && python -m pytest -q` 全绿。
- `retrieve_doc`、`template_read/list/delete`、`sync` 的 fetch 阶段走 `FeishuClient`，不再调 lark-cli 子进程。
- `template_create/update` 仍走 lark-cli（P2 处理，属预期）。
- 集成冒烟：真实 token 读文档 / 列模板 / 拉多维表成功。
- `feishu.py` 单文件、单一职责，测试覆盖 token 缓存/刷新/错误 + 5 端点。

## 后续（独立计划）

- **P2**：写端点（`convert_markdown_to_blocks`/`create_doc`/`insert_children`/`delete_all_children`）→ 迁 `template_create/update` → 删 `LarkCliClient`。
- **P3**：Dockerfile 删 Node/npm/lark-cli + compose 删密钥挂载卷 + 更新 README/CLAUDE.md/踩坑表（**部署简化在此落地**）。
