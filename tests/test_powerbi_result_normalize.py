"""P2 回归:Power BI 结果解码双重编码并统一错误信封。

QA 实测(2026-08-26):
- JSON-RPC 信封内 content[].text 再包一层 JSON 字符串(中文全 \\uXXXX 转义,费 token);
- 错误信封三态不一致:协议级 error 对象 / isError+Answer / 纯文本无 isError。
修复:text 块可解析 JSON 则解码为对象;Answer.Status=error 或 DAX 错误文本统一抛
DataSourceError(经工具层映射为 [DataSourceError] …)。
"""
import json

import pytest

from sda_mcp.errors import DataSourceError
from sda_mcp.skills import querying_data as q

GUID = "12345678-1234-1234-1234-123456789012"


def _client(monkeypatch, raw):
    monkeypatch.setattr(q.PowerBIClient, "__init__", lambda self: None)
    monkeypatch.setattr(q.PowerBIClient, "_mcp_call", lambda self, m, p=None: json.loads(json.dumps(raw)))
    return q.PowerBIClient()


def test_double_encoded_text_is_decoded(monkeypatch):
    inner = json.dumps({"Answer": {"Status": "ok", "rows": [["行", 1]]}}, ensure_ascii=False)
    raw = {"result": {"content": [{"type": "text", "text": inner}]}}
    r = _client(monkeypatch, raw).query(GUID, ["EVALUATE 1"])
    block = r["result"]["content"][0]
    assert block["text"] == {"Answer": {"Status": "ok", "rows": [["行", 1]]}}


def test_answer_error_raises_datasource(monkeypatch):
    inner = json.dumps({"Answer": {"Status": "error",
                                   "Error": {"Code": "PowerBIEntityNotFound",
                                             "Message": "Power BI couldn't find the artifact."}}})
    raw = {"result": {"content": [{"type": "text", "text": inner}]}}
    with pytest.raises(DataSourceError) as ei:
        _client(monkeypatch, raw).query(GUID, ["EVALUATE 1"])
    assert "couldn't find" in str(ei.value)


def test_dax_syntax_error_text_raises(monkeypatch):
    raw = {"result": {"content": [{"type": "text",
                                   "text": "DAX query syntax error: Query (1, 16) The syntax for '1' is incorrect."}]}}
    with pytest.raises(DataSourceError) as ei:
        _client(monkeypatch, raw).query(GUID, ["EVALUATE SELCT 1"])
    assert "syntax" in str(ei.value)


def test_protocol_error_object_raises(monkeypatch):
    raw = {"error": {"code": -32004, "message": "Power BI couldn't find the artifact."}}
    with pytest.raises(DataSourceError):
        _client(monkeypatch, raw).get_schema(GUID)


def test_plain_data_text_left_untouched(monkeypatch):
    raw = {"result": {"content": [{"type": "text", "text": "1\t2\n3\t4"}]}}
    r = _client(monkeypatch, raw).query(GUID, ["EVALUATE 1"])
    assert r["result"]["content"][0]["text"] == "1\t2\n3\t4"
