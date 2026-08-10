"""using_templates mock 单元测试（mock 子进程，不依赖真实 lark-cli）。"""
import json
import pytest
from sda_mcp.errors import ConfigError, ExternalAPIError, ValidationError
from sda_mcp.skills import using_templates as t


# --- _exec / _run 行为 ---

def test_lark_bin_missing_raises_config(monkeypatch):
    def _boom(*a, **k):
        raise FileNotFoundError("no such file")
    monkeypatch.setattr(t.subprocess, "run", _boom)
    client = t.LarkCliClient()
    with pytest.raises(ConfigError):
        client._run(["docs"], identity="user")


def test_lark_nonzero_raises_external(monkeypatch):
    class _P:
        returncode = 1
        stdout = ""
        stderr = "boom"
    monkeypatch.setattr(t.subprocess, "run", lambda *a, **k: _P())
    client = t.LarkCliClient()
    with pytest.raises(ExternalAPIError):
        client._run(["docs"], identity="user")


def _fake_run_factory(monkeypatch, outputs):
    """按 FIFO 吐 stdout；记每次调用的 args/cwd/identity。"""
    calls = []
    q = list(outputs)

    class _P:
        def __init__(self, stdout):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def _run(args, cwd=None, identity=None, **k):
        full = list(args) + (["--as", identity] if identity else [])
        calls.append({"args": full, "cwd": cwd})
        return _P(q.pop(0))
    monkeypatch.setattr(t.subprocess, "run", _run)
    return calls


def test_exec_caches_identity(monkeypatch):
    """user 成功 → 缓存 user，后续不再回退。"""
    calls = _fake_run_factory(monkeypatch, ["out1", "out2"])
    client = t.LarkCliClient()
    assert client._exec(["docs"]) == "out1"
    assert client._identity == "user"
    assert client._exec(["docs"]) == "out2"
    # 两次都带 --as user
    assert calls[0]["args"][-2:] == ["--as", "user"]
    assert calls[1]["args"][-2:] == ["--as", "user"]


def test_exec_falls_back_to_bot(monkeypatch):
    """user 失败 → 回退 bot，缓存 bot。"""
    calls = []
    class _P:
        def __init__(self, stdout, rc=0):
            self.returncode = rc; self.stdout = stdout; self.stderr = "e"
    def _run(args, cwd=None, **k):
        # identity 编码在 args 尾部（--as <identity>）
        identity = args[-1] if args[-2:] == ["--as", args[-1]] else None
        calls.append({"identity": identity})
        if identity == "user":
            return _P("", rc=1)          # user 失败
        return _P("bot-out")
    monkeypatch.setattr(t.subprocess, "run", _run)
    client = t.LarkCliClient()
    out = client._exec(["docs"])
    assert out == "bot-out"
    assert client._identity == "bot"
    assert [c["identity"] for c in calls] == ["user", "bot"]


# --- list_templates ---

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


# --- read ---

def test_read_parses_markdown(monkeypatch):
    monkeypatch.setattr(t.FeishuClient, "get_doc_markdown",
                        lambda self, doc_id: "# 标题\n正文")
    assert t.read_template("DOC") == "# 标题\n正文"


def test_read_empty_doc_id():
    with pytest.raises(t.ValidationError):
        t.read_template("")


# --- create ---

def test_create_requires_title():
    with pytest.raises(ValidationError):
        t.create_template("")


def test_create_success(monkeypatch, tmp_path):
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})
    captured = {}

    def _exec(self, args, cwd=None):
        captured["args"] = list(args)
        captured["cwd"] = cwd
        return json.dumps({"data": {"doc_id": "NEWDOC"}})
    monkeypatch.setattr(t.LarkCliClient, "_exec", _exec)
    r = t.create_template("播报", content="# 播报\n内容")
    assert r.document_id == "NEWDOC" and r.title == "播报"
    assert "@content.md" in captured["args"]
    assert "--parent-token" in captured["args"] and "F" in captured["args"]
    assert captured["cwd"] is not None          # 用了临时目录


def test_create_no_doc_id_raises(monkeypatch):
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})
    monkeypatch.setattr(t.LarkCliClient, "_exec", lambda self, a, cwd=None: json.dumps({"data": {}}))
    with pytest.raises(ExternalAPIError):
        t.create_template("t", content="x")


# --- update ---

def test_update_requires_content():
    with pytest.raises(ValidationError):
        t.update_template("DOC", "")


def test_update_success(monkeypatch):
    captured = {}
    def _exec(self, args, cwd=None):
        captured["args"] = list(args); captured["cwd"] = cwd; return ""
    monkeypatch.setattr(t.LarkCliClient, "_exec", _exec)
    r = t.update_template("DOC", "新内容")
    assert r.updated is True and r.document_id == "DOC"
    assert "--doc" in captured["args"] and "DOC" in captured["args"]
    assert "--command" in captured["args"] and "overwrite" in captured["args"]


# --- delete ---

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
