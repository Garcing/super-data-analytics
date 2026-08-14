"""火山方舟 Seedream 图片生成内核。

方舟图片生成是单次 HTTP 请求：请求直接返回最终图片 URL 或 Base64，
没有后台 task_id/status 轮询接口。首版不发送组图/流式字段，不自动重试 POST。
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from sda_mcp.config import get_env, load_config
from sda_mcp.errors import ExternalAPIError, ValidationError

ImageResponseFormat = Literal["url", "b64_json"]
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedream-5-0-pro-260628"
IMAGES_PATH = "/images/generations"
VALID_RESPONSE_FORMATS = {"url", "b64_json"}
_TIMEOUT = httpx.Timeout(300.0, connect=20.0)


@dataclass
class GeneratedImage:
    url: str | None = None
    data: bytes | None = None
    size: str | None = None
    format: str = "jpeg"
    error: str | None = None


@dataclass
class ImageGenerationResult:
    provider: str
    model: str
    response_format: ImageResponseFormat
    status: str = "completed"
    created: int | None = None
    request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    images: list[GeneratedImage] = field(default_factory=list)


def _env() -> dict[str, Any]:
    return load_config().get("env", {}) or {}


def build_request_body(prompt: str, **opts: Any) -> dict[str, Any]:
    """构造方舟请求体；模型 ID 配置化，不使用硬编码枚举。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValidationError("prompt 必填且为非空字符串")

    env = _env()
    model = str(opts.get("model") or env.get("VOLCENGINE_ARK_IMAGE_MODEL") or DEFAULT_MODEL).strip()
    if not model:
        raise ValidationError("model 不能为空")

    response_format = str(opts.get("response_format") or "url").strip().lower()
    if response_format not in VALID_RESPONSE_FORMATS:
        raise ValidationError("response_format 仅支持 url 或 b64_json")

    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt.strip(),
        "size": opts.get("size") or "2K",
        "response_format": response_format,
        "watermark": bool(opts.get("watermark", False)),
    }
    if opts.get("seed") is not None:
        body["seed"] = opts["seed"]
    return body


def _request_id(resp: httpx.Response) -> str | None:
    return resp.headers.get("x-request-id") or resp.headers.get("x-tt-logid")


def _decode_image(value: str) -> bytes:
    raw = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ExternalAPIError("方舟返回了无效的 b64_json 图片数据") from exc


def _image_format(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return "jpeg"


class ImageClient:
    def __init__(self) -> None:
        self._api_key = get_env("VOLCENGINE_ARK_API_KEY")["VOLCENGINE_ARK_API_KEY"]
        env = _env()
        self._base_url = str(env.get("VOLCENGINE_ARK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

    def generate(self, body: dict[str, Any]) -> ImageGenerationResult:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.post(f"{self._base_url}{IMAGES_PATH}", headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ExternalAPIError(
                "火山方舟图片生成请求超时；该 POST 不会自动重试，以免重复生成和计费"
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalAPIError(f"火山方舟连接失败: {exc}") from exc

        request_id = _request_id(resp)
        suffix = f" (request_id={request_id})" if request_id else ""
        if resp.status_code in {401, 403}:
            raise ExternalAPIError(
                f"VOLCENGINE_ARK_API_KEY 无效或无模型权限 ({resp.status_code}){suffix}"
            )
        if resp.status_code == 429:
            raise ExternalAPIError(f"火山方舟请求限流 (429)，请稍后重试{suffix}")
        if resp.status_code >= 400:
            raise ExternalAPIError(
                f"火山方舟图片生成失败 ({resp.status_code}): {resp.text[:500]}{suffix}"
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ExternalAPIError(
                f"火山方舟返回非 JSON 响应 ({resp.status_code}): {resp.text[:500]}{suffix}"
            ) from exc

        response_format: ImageResponseFormat = body["response_format"]
        images: list[GeneratedImage] = []
        for item in payload.get("data") or []:
            if response_format == "url":
                url = item.get("url")
                if url:
                    images.append(GeneratedImage(
                        url=str(url),
                        size=item.get("size"),
                        format=str(item.get("output_format") or "jpeg").lower(),
                    ))
            else:
                encoded = item.get("b64_json")
                if encoded:
                    data = _decode_image(str(encoded))
                    images.append(
                        GeneratedImage(data=data, size=item.get("size"), format=_image_format(data))
                    )
        if not images:
            raise ExternalAPIError(f"火山方舟请求成功但未返回图片: {str(payload)[:500]}{suffix}")

        return ImageGenerationResult(
            provider="volcengine",
            model=str(payload.get("model") or body["model"]),
            response_format=response_format,
            created=payload.get("created"),
            request_id=request_id,
            usage=payload.get("usage") or {},
            images=images,
        )


def generate_image(prompt: str, **opts: Any) -> ImageGenerationResult:
    return ImageClient().generate(build_request_body(prompt, **opts))
