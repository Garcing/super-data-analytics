"""image_gen mock 单元测试（离线）。"""
import json
import pytest
from sda_mcp.errors import ConfigError, ExternalAPIError, SkillTimeoutError, ValidationError
from sda_mcp.skills.building_reports import image_gen as ig


class _FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        if body is None:
            self.text = ""
        elif isinstance(body, (str, bytes)):
            self.text = body                       # bytes 透传（download 路径只读 .content）
        else:
            self.text = json.dumps(body)
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
    # image_gen 每个 submit/get_status/download 各开一个 httpx.Client()；
    # 若每次 factory 吐新实例会重置响应队列导致死循环。共享同一个 fake client。
    client = _FakeHttpxClient(responses)
    holder = {"client": client}
    monkeypatch.setattr(ig.httpx, "Client", lambda *a, **k: client)
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
    # 负超时 → deadline 严格在过去，第一次状态检查后即抛 SkillTimeoutError。
    monkeypatch.setattr(ig, "POLL_TIMEOUT_S", -1)
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
