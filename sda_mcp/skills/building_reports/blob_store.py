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
