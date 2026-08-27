"""P0-2 回归：SkillError/意外异常必须映射为带类型与原因的可操作 MCP 错误。

背景：mcp 2.1.0 起 SDK 把未捕获异常包成 ``UnexpectedToolError("Error executing tool <名>")``，
原始消息不再透出（pyproject 放开 ``>=2.0,<3`` 后线上构建抓到 2.1.1，错误语义静默回归，
2026-08-26 QA 全部裸错误即此因）。工具层必须显式映射，不依赖 SDK 版本行为。
"""
import asyncio

from sda_mcp import server  # noqa: F401  导入即完成工具注册
from sda_mcp.tools import analyze_tools, query_tools, report_tools


def _call(name, args):
    from mcp import Client
    from sda_mcp.tools._common import mcp

    async def _run():
        async with Client(mcp) as client:
            r = await client.call_tool(name, args)
            return r.structured_content, r.is_error, r.content
    return asyncio.run(_run())


def _text(content):
    return "".join(getattr(c, "text", "") for c in content)


def test_skill_error_maps_to_typed_actionable_message(monkeypatch):
    """内核 SkillError → is_error + 文本含错误类型名与原始消息。"""
    from sda_mcp.errors import DataSourceError

    def _boom(sql):
        raise DataSourceError("连不上 Hologres（检查 VPN）")
    monkeypatch.setattr(query_tools, "_sql_query", _boom)
    _, err, content = _call("sql_query", {"sql": "SELECT 1"})
    assert err is True
    text = _text(content)
    assert "DataSourceError" in text
    assert "Hologres" in text


def test_unexpected_error_maps_to_typed_actionable_message(monkeypatch):
    """非 SkillError 的意外异常 → is_error + 文本含异常类型名与消息（不裸奔）。"""

    def _boom(sql):
        raise RuntimeError("boom 细节")
    monkeypatch.setattr(query_tools, "_sql_query", _boom)
    _, err, content = _call("sql_query", {"sql": "SELECT 1"})
    assert err is True
    text = _text(content)
    assert "RuntimeError" in text
    assert "boom 细节" in text


def test_error_mapping_covers_analyze_module(monkeypatch):
    from sda_mcp.errors import ValidationError

    def _boom(method, payload):
        raise ValidationError("乘法分解要求全部因子 baseline>0")
    monkeypatch.setattr(analyze_tools, "_contribute", _boom)
    _, err, content = _call("contribute", {"method": "multiply", "payload": {"factors": []}})
    assert err is True
    text = _text(content)
    assert "ValidationError" in text
    assert "baseline>0" in text


def test_error_mapping_covers_report_module(monkeypatch):
    from sda_mcp.errors import ConfigError

    def _boom():
        raise ConfigError("BLOB_READ_WRITE_TOKEN 未配置")
    monkeypatch.setattr(report_tools, "_list", _boom)
    _, err, content = _call("report_html_list", {})
    assert err is True
    assert "ConfigError" in _text(content)
