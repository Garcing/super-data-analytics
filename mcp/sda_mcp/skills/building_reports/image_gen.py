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

from sda_mcp.config import get_env, load_config
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
        # APIMART_API_KEY 必填走 get_env；APIMART_BASE_URL 可选（缺省回退 DEFAULT_BASE_URL），
        # 不能塞进 get_env（缺省会抛 ConfigError，使 DEFAULT_BASE_URL 回退变成死代码）。
        env = get_env("APIMART_API_KEY")
        self._api_key = env["APIMART_API_KEY"]
        if not self._api_key:
            raise ConfigError("APIMART_API_KEY 未配置")
        cfg_env = load_config().get("env", {}) or {}
        self._base_url = (cfg_env.get("APIMART_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

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
