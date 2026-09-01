"""飞书开放平台 REST 客户端（httpx 直连，tenant_access_token 鉴权）。

只读客户端，仅覆盖语义层所需能力：docx 纯文本正文（raw_content）与 bitable
字段/记录。对齐 VercelBlobClient 模式：失败抛
ConfigError(缺凭证)/ExternalAPIError(HTTP/code!=0)。
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

# bitable 字段类型（开放平台用 int）
# 已用真实 base（BHINbLiOKa4rXDsLTlQcRwuSn9c）逐字段验证值结构（2026-08-10）：
#   Text(1)/SingleSelect(3) → 裸字符串；MultiSelect(4) → 字符串列表；
#   Formula(20)/Lookup(19) 文本结果 → [{text,type}] 片段数组（官方：查找引用本质=公式，value 同构）。
# 注意：这些常量被 sync 层（skills/retrieving_context_sync.py）import 做字段类型分派，
# 看似"未使用"实则跨模块契约，勿删。
_F_TEXT = 1
_F_NUMBER = 2
_F_SINGLE_SELECT = 3
_F_MULTI_SELECT = 4
_F_DATE = 5
_F_CHECKBOX = 7
_F_USER = 11
_F_PHONE = 13
_F_URL = 15
_F_ATTACHMENT = 17
_F_SINGLE_LINK = 18
_F_LOOKUP = 19
_F_FORMULA = 20
_F_DUPLEX_LINK = 21
_F_LOCATION = 22
_F_GROUP_CHAT = 23
_F_CREATED_TIME = 1001
_F_MODIFIED_TIME = 1002
_F_CREATED_USER = 1003
_F_MODIFIED_USER = 1004
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
    except (httpx.HTTPError, ValueError) as exc:
        # ValueError 覆盖 json.JSONDecodeError：网关返回非 JSON 200 响应（如 Caddy HTML 错误页）时，
        # resp.json() 抛 ValueError（非 httpx.HTTPError），需归一成 ExternalAPIError。
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


def _next_token(data: dict[str, Any]) -> str | None:
    """提取翻页 token（bitable 返回 page_token）。"""
    payload = data.get("data") or data
    return payload.get("next_page_token") or payload.get("page_token")


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
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # ValueError 覆盖 json.JSONDecodeError：非 JSON 200 响应（网关 HTML 错误页）归一为 ExternalAPIError。
            raise ExternalAPIError(f"飞书 API {method} {path} 失败: {exc}") from exc
        # 业务码校验在 _request 内统一做（_check 抛 ExternalAPIError，非 HTTPError，
        # 不会被上面的 except 捕获）。各端点方法的 _check 调用因此成为幂等无副作用的二次校验。
        self._check(data, path)
        return data

    @staticmethod
    def _check(data: dict[str, Any], path: str) -> None:
        if data.get("code") != 0:
            msg = data.get("msg") or data.get("message") or "未知错误"
            raise ExternalAPIError(f"飞书 API {path} 返回错误: {str(msg)[:300]}")

    # --- docx 纯文本正文（读）---
    def get_raw_content(self, doc_token: str) -> str:
        """读取 docx 纯文本正文。GET /open-apis/docx/v1/documents/{token}/raw_content。

        官方接口直出全文纯文本：标题、段落、代码块拍平为文本行，无分页。
        """
        path = f"/open-apis/docx/v1/documents/{doc_token}/raw_content"
        data = self._request("GET", path)
        content = (data.get("data") or {}).get("content")
        if not isinstance(content, str):
            raise ExternalAPIError(f"飞书文档 {doc_token} raw_content 响应缺 content")
        return content

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

    # --- bitable 记录（读，原始）---
    def list_bitable_records(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        """列多维表全部记录（原始 items，含 record_id + fields map；值简化由调用方做）。

        走官方推荐的 POST /records/search（无 filter 即全量）；旧 GET /records 已被
        飞书标记为历史接口、不推荐使用。响应仍是 data.items/has_more/page_token。
        """
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": 500}
            if page_token:
                body["page_token"] = page_token
            data = self._request("POST", path, json_body=body)
            self._check(data, path)
            payload = data.get("data") or {}
            items.extend(payload.get("items") or [])
            if not payload.get("has_more"):
                break
            page_token = _next_token(data)
            if not page_token:
                break
        return items

