"""using_templates mock 单元测试（mock FeishuClient，不依赖真实 lark-cli）。"""
import pytest
from sda_mcp.errors import ValidationError
from sda_mcp.skills import using_templates as t


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

def test_create_with_content_calls_feishu(monkeypatch):
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})
    calls = []
    monkeypatch.setattr(t.FeishuClient, "create_doc",
                        lambda self, f, ti: (calls.append(("create_doc", f, ti)), "NEWDOC")[1])
    monkeypatch.setattr(t.FeishuClient, "convert_markdown_to_blocks",
                        lambda self, md: ([{"block_type": 2}], ["b1"]))
    monkeypatch.setattr(t.FeishuClient, "insert_descendants",
                        lambda self, did, bl, cid: calls.append(("insert", did, bl, cid)))
    r = t.create_template("播报", content="# 播报\n内容")
    assert r.document_id == "NEWDOC" and r.title == "播报"
    assert calls[0][0] == "create_doc" and calls[0][1] == "F"
    assert calls[1][0] == "insert" and calls[1][1] == "NEWDOC"


def test_create_no_content_skips_insert(monkeypatch):
    monkeypatch.setattr(t, "get_env", lambda *k: {"FEISHU_TEMPLATE_FOLDER_TOKEN": "F"})
    calls = []
    monkeypatch.setattr(t.FeishuClient, "create_doc", lambda self, f, ti: "NEWDOC")
    monkeypatch.setattr(t.FeishuClient, "convert_markdown_to_blocks",
                        lambda self, md: (calls.append(("convert", md)), ([], []))[1])
    r = t.create_template("空模板")
    assert r.document_id == "NEWDOC"
    assert calls == []  # 无 content 不 convert / 不 insert


def test_create_requires_title():
    with pytest.raises(t.ValidationError):
        t.create_template("")


# --- update ---

def test_update_overwrite_calls_feishu(monkeypatch):
    calls = []
    monkeypatch.setattr(t.FeishuClient, "delete_all_children",
                        lambda self, did: calls.append(("del", did)))
    monkeypatch.setattr(t.FeishuClient, "convert_markdown_to_blocks",
                        lambda self, md: ([{"block_type": 2}], ["b1"]))
    monkeypatch.setattr(t.FeishuClient, "insert_descendants",
                        lambda self, did, bl, cid: calls.append(("insert", did)))
    r = t.update_template("DOC", "新内容")
    assert r.updated is True and r.document_id == "DOC"
    assert calls[0] == ("del", "DOC")
    assert calls[1] == ("insert", "DOC")


def test_update_requires_content():
    with pytest.raises(t.ValidationError):
        t.update_template("DOC", "")


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
