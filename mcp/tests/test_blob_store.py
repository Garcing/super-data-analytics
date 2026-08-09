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
