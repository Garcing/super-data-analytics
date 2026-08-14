"""MCP 工具 in-memory 单测（Client(mcp)，mock 内核，不走 HTTP）。

入参约定（实测 mcp 2.0.0 FastMCP v2）：当工具函数形参为单个 Pydantic BaseModel
（形参名 `params`）时，in-memory client 调 call_tool 必须用 {"params": {...}} 包一层；
平铺字段（如 {"sql": "..."}）会触发校验失败 → is_error。
zero-arg 工具传空 dict {}。
"""
import asyncio

from sda_mcp import server
from sda_mcp.tools import (
    query_tools, retrieve_tools, analyze_tools, visualize_tools, report_tools,
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
                        lambda question, top_k=5, targets=None, strategy="vector":
                        {"question": question, "strategy": strategy, "results": []})
    sc, err, _ = _call("retrieve_search", {"params": {"question": "Q"}})
    assert sc["results"] == []
    assert sc["strategy"] == "hybrid"


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


def test_report_image_url_returns_structured_content(monkeypatch):
    from sda_mcp.skills.building_reports.image_gen import (
        GeneratedImage, ImageGenerationResult,
    )
    monkeypatch.setattr(
        report_tools,
        "_gen",
        lambda prompt, **opts: ImageGenerationResult(
            provider="volcengine",
            model="future-seedream",
            response_format="url",
            created=1780000000,
            request_id="req-1",
            usage={"generated_images": 1},
            images=[GeneratedImage(url="https://img/a.jpeg", size="2048x2732")],
        ),
    )
    sc, err, content = _call(
        "report_image_generate",
        {"params": {"prompt": "报告", "response_format": "url"}},
    )
    assert not err
    assert sc["provider"] == "volcengine"
    assert sc["images"][0]["url"] == "https://img/a.jpeg"
    assert [getattr(block, "type", "") for block in content] == ["text"]


def test_report_image_b64_returns_image_block(monkeypatch):
    from sda_mcp.skills.building_reports.image_gen import (
        GeneratedImage, ImageGenerationResult,
    )
    monkeypatch.setattr(
        report_tools,
        "_gen",
        lambda prompt, **opts: ImageGenerationResult(
            provider="volcengine",
            model="future-seedream",
            response_format="b64_json",
            images=[GeneratedImage(data=b"\x89PNG\r\n\x1a\n", format="png")],
        ),
    )
    sc, err, content = _call(
        "report_image_generate",
        {"params": {"prompt": "报告", "response_format": "b64_json"}},
    )
    assert not err
    assert sc["images"][0]["url"] is None
    assert [getattr(block, "type", "") for block in content] == ["image", "text"]


def test_retrieve_doc_update(monkeypatch):
    monkeypatch.setattr(retrieve_tools, "_update_doc",
                        lambda doc, content: {"updated": True, "document_id": doc})
    sc, err, _ = _call("retrieve_doc_update", {"params": {"doc": "DOC1", "content": "# 新"}})
    assert not err
    assert sc == {"updated": True, "document_id": "DOC1"}


def test_retrieve_schema_tool(monkeypatch):
    monkeypatch.setattr(
        retrieve_tools,
        "_schema",
        lambda: {"nodes": {"指标": {"properties": {"指标ID": "STRING"}}}, "relationships": []},
    )
    sc, err, _ = _call("retrieve_schema", {})
    assert not err
    assert sc["nodes"]["指标"]["properties"]["指标ID"] == "STRING"


def test_sync_tool_only_accepts_dry_run(monkeypatch):
    from sda_mcp.skills import retrieving_context_sync

    monkeypatch.setattr(
        retrieving_context_sync,
        "sync_graph",
        lambda dry_run=False: {"dry_run": dry_run, "validated": True},
    )
    sc, err, _ = _call("sync", {"params": {"dry_run": True}})
    assert not err
    assert sc == {"dry_run": True, "validated": True}

    _, err, _ = _call("sync", {"params": {"only": "fetch"}})
    assert err


def test_validation_error_is_error():
    # Pydantic 校验失败（缺必填）→ is_error
    sc, err, _ = _call("sql_query", {"params": {}})
    assert err
