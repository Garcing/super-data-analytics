"""火山方舟 Seedream 图片生成 mock 单元测试（离线、不计费）。"""
import base64
import json

import httpx
import pytest

from sda_mcp.errors import ConfigError, ExternalAPIError, ValidationError
from sda_mcp.skills.building_reports import image_gen as ig


class _FakeResp:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = body if isinstance(body, str) else json.dumps(body or {})

    def json(self):
        return json.loads(self.text)


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        return self.response


def _client(monkeypatch, response=None, error=None):
    fake = _FakeClient(response=response, error=error)
    monkeypatch.setattr(ig.httpx, "Client", lambda *args, **kwargs: fake)
    monkeypatch.setattr(ig, "get_env", lambda *keys: {"VOLCENGINE_ARK_API_KEY": "ark-key"})
    monkeypatch.setattr(
        ig,
        "load_config",
        lambda: {"env": {"VOLCENGINE_ARK_BASE_URL": "https://ark.test/api/v3"}},
    )
    return fake, ig.ImageClient()


def test_build_body_defaults(monkeypatch):
    monkeypatch.setattr(
        ig,
        "load_config",
        lambda: {"env": {"VOLCENGINE_ARK_IMAGE_MODEL": "ep-new-model"}},
    )
    body = ig.build_request_body("  数据报告  ")
    assert body == {
        "model": "ep-new-model",
        "prompt": "数据报告",
        "size": "2K",
        "response_format": "url",
        "watermark": False,
    }


def test_build_body_overrides_and_validation(monkeypatch):
    monkeypatch.setattr(ig, "load_config", lambda: {"env": {}})
    body = ig.build_request_body(
        "报告", model="future-model", size="2048x2732",
        response_format="b64_json", seed=42, watermark=True,
    )
    assert body["model"] == "future-model"
    assert body["response_format"] == "b64_json"
    assert body["seed"] == 42 and body["watermark"] is True
    with pytest.raises(ValidationError):
        ig.build_request_body(" ")
    with pytest.raises(ValidationError):
        ig.build_request_body("报告", response_format="png")


def test_url_response(monkeypatch):
    response = _FakeResp(
        200,
        {
            "model": "doubao-seedream-5-0-pro-260628",
            "created": 1780000000,
            "data": [{"url": "https://img.test/a.jpeg", "size": "2048x2732"}],
            "usage": {"generated_images": 1, "total_tokens": 123},
        },
        {"x-request-id": "req-1"},
    )
    fake, client = _client(monkeypatch, response=response)
    result = client.generate(ig.build_request_body("报告"))
    assert fake.calls[0]["url"] == "https://ark.test/api/v3/images/generations"
    assert fake.calls[0]["json"]["response_format"] == "url"
    assert result.request_id == "req-1"
    assert result.images[0].url == "https://img.test/a.jpeg"
    assert result.images[0].data is None
    assert result.usage["generated_images"] == 1


def test_b64_response_becomes_bytes(monkeypatch):
    png = b"\x89PNG\r\n\x1a\nmock"
    response = _FakeResp(
        200,
        {"data": [{"b64_json": base64.b64encode(png).decode(), "size": "1024x1024"}]},
    )
    _, client = _client(monkeypatch, response=response)
    body = ig.build_request_body("报告", response_format="b64_json")
    result = client.generate(body)
    assert result.images[0].data == png
    assert result.images[0].format == "png"
    assert result.images[0].url is None


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_errors_include_actionable_message(monkeypatch, status):
    _, client = _client(
        monkeypatch,
        response=_FakeResp(status, {"error": {"message": "failed"}}, {"x-tt-logid": "log-1"}),
    )
    with pytest.raises(ExternalAPIError) as exc:
        client.generate(ig.build_request_body("报告"))
    assert "log-1" in str(exc.value)


def test_timeout_is_not_retried(monkeypatch):
    fake, client = _client(monkeypatch, error=httpx.ReadTimeout("slow"))
    with pytest.raises(ExternalAPIError) as exc:
        client.generate(ig.build_request_body("报告"))
    assert "不会自动重试" in str(exc.value)
    assert len(fake.calls) == 1


def test_missing_key(monkeypatch):
    monkeypatch.setattr(ig, "get_env", lambda *keys: (_ for _ in ()).throw(ConfigError("missing")))
    with pytest.raises(ConfigError):
        ig.ImageClient()
