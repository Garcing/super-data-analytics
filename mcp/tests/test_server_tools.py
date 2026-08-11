"""MCP 工具 in-memory 单测（Client(mcp)，mock 内核，不走 HTTP）。

入参约定（实测 mcp 2.0.0 FastMCP v2）：当工具函数形参为单个 Pydantic BaseModel
（形参名 `params`）时，in-memory client 调 call_tool 必须用 {"params": {...}} 包一层；
平铺字段（如 {"sql": "..."}）会触发校验失败 → is_error。
zero-arg 工具传空 dict {}。
"""
import asyncio

from sda_mcp import server
from sda_mcp.tools import (
    query_tools, retrieve_tools, analyze_tools, visualize_tools, report_tools, template_tools,
)


def test_server_uses_stateless_json_http(monkeypatch):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))

    server.main()

    assert calls == [{
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 3100,
        "stateless_http": True,
        "json_response": True,
    }]


def _call(name, args):
    """同步包装：用 in-memory Client 调工具，返回 (structured_content, is_error, content)。"""
    from mcp import Client
    from sda_mcp.tools._common import mcp

    async def _run():
        async with Client(mcp) as client:
            r = await client.call_tool(name, args)
            return r.structured_content, r.is_error, r.content
    return asyncio.run(_run())


def test_sql_query_tool(monkeypatch):
    from sda_mcp.skills.querying_data import SqlResult
    monkeypatch.setattr(query_tools, "_sql_query",
                        lambda sql: SqlResult(columns=[{"name": "a"}], rows=[{"a": 1}], row_count=1))
    sc, err, _ = _call("sql_query", {"params": {"sql": "SELECT 1"}})
    assert not err
    assert sc["row_count"] == 1 and sc["columns"][0]["name"] == "a"


def test_skill_error_becomes_is_error(monkeypatch):
    from sda_mcp.errors import DataSourceError

    def _boom(sql):
        raise DataSourceError("连不上 Hologres（检查 VPN）")
    monkeypatch.setattr(query_tools, "_sql_query", _boom)
    sc, err, content = _call("sql_query", {"params": {"sql": "SELECT 1"}})
    assert err is True
    # 可操作 message 进了 text content
    joined = "".join(getattr(c, "text", "") for c in content)
    assert "Hologres" in joined or "VPN" in joined


def test_retrieve_search(monkeypatch):
    monkeypatch.setattr(retrieve_tools, "_search",
                        lambda question, top_k=5, targets=None: {"question": question, "results": []})
    sc, err, _ = _call("retrieve_search", {"params": {"question": "Q"}})
    assert sc["results"] == []


def test_contribute(monkeypatch):
    monkeypatch.setattr(analyze_tools, "_contribute",
                        lambda method, payload: {"summary": "s", "rows": [], "checks": []})
    sc, err, _ = _call("contribute", {"params": {"method": "add", "payload": {"a": [1, 2]}}})
    assert sc["summary"] == "s"


def test_chart_returns_image_block(monkeypatch):
    from sda_mcp.skills.visualizing import ChartResult
    monkeypatch.setattr(visualize_tools, "_render",
                        lambda spec, format="png", dpi=144: ChartResult(
                            format="png", dpi=144, width=10, height=20,
                            data=b"\x89PNG\r\n\x1a\n", warnings=[]))
    sc, err, content = _call("chart", {"params": {"spec": {"type": "bar", "title": "T"}, "format": "png"}})
    assert not err
    # 至少有一个 image 内容块（Blob 上传会失败因无凭证，不影响图片块）
    types = [getattr(c, "type", "") for c in content]
    assert "image" in types


def test_report_publish(monkeypatch):
    from sda_mcp.skills.building_reports.html_reports import PublishResult
    monkeypatch.setattr(report_tools, "_publish",
                        lambda report, rid: PublishResult(url=f"https://app/report/{rid}",
                                                          report_id=rid, blob_url="b"))
    sc, err, _ = _call("report_html_publish", {"params": {"id": "r1", "report": {"meta": {"title": "t"}}}})
    assert sc["url"].endswith("/report/r1")


def test_template_list(monkeypatch):
    monkeypatch.setattr(template_tools, "_list", lambda: [{"id": "d1", "name": "日报"}])
    sc, err, _ = _call("template_list", {})
    assert sc["templates"][0]["id"] == "d1"


def test_validation_error_is_error():
    # Pydantic 校验失败（缺必填）→ is_error
    sc, err, _ = _call("sql_query", {"params": {}})
    assert err
