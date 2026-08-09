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

from sda_mcp.config import load_config
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
    # VERCEL_REPORTS_URL 可选（仅用于拼可分享链接），不走 get_env（缺省会抛 ConfigError）。
    return (load_config().get("env", {}) or {}).get("VERCEL_REPORTS_URL", "").rstrip("/")


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
