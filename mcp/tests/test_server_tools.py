"""MCP 工具 in-memory 单测（Client(mcp)，mock 内核，不走 HTTP）。

入参约定（实测 mcp 2.0.0 MCPServer/FastMCP v2）：工具函数签名平铺
（每个字段是独立关键字参数，约束走 Annotated[..., Field(...)]），
call_tool 直接传平铺字段（如 {"sql": "..."}）。

注意：平铺签名下 SDK 的动态参数模型默认 extra="ignore"——
未知键被静默丢弃（不报错），详见 test_sync_tool_schema。
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


def _tools():
    """同步包装：list_tools → {name: Tool}。"""
    from mcp import Client
    from sda_mcp.tools._common import mcp

    async def _run():
        async with Client(mcp) as client:
            tools = (await client.list_tools()).tools
            return {t.name: t for t in tools}
    return asyncio.run(_run())


def test_tool_schemas_are_flat():
    """所有工具 input_schema 平铺：properties 不含 params 包装，字段直接展开。"""
    tools = _tools()
    assert len(tools) == 19
    for name, tool in tools.items():
        props = tool.input_schema.get("properties", {})
        assert "params" not in props, f"{name} 仍有 params 包装"

    rs = tools["retrieve_search"].input_schema["properties"]
    assert set(rs) == {"question", "top_k", "targets", "strategy"}
    # Annotated Field 约束保留（ge=1/le=20 → minimum/maximum）
    assert rs["top_k"]["maximum"] == 20
    assert rs["top_k"]["minimum"] == 1
    assert rs["top_k"]["default"] == 5
    assert rs["question"]["minLength"] == 1
    # description 保留
    assert "Hybrid" in rs["strategy"]["description"] or "hybrid" in rs["strategy"]["description"]

    chart = tools["chart"].input_schema["properties"]
    assert chart["dpi"]["minimum"] == 72 and chart["dpi"]["maximum"] == 300
    assert chart["dpi"]["default"] == 144

    # sql_query 不再广告无效的 max_rows；大结果由 SQL 自己 LIMIT。
    assert set(tools["sql_query"].input_schema["properties"]) == {"sql"}


def test_tool_metadata_is_complete_and_safety_accurate():
    """tools/list 应给模型完整的显示名、行为提示与简洁返回契约。"""
    tools = _tools()
    for name, tool in tools.items():
        assert tool.annotations is not None, f"{name} 缺 annotations"
        assert tool.annotations.title, f"{name} 缺 title"
        assert tool.annotations.read_only_hint is not None
        assert tool.annotations.destructive_hint is not None
        assert tool.annotations.idempotent_hint is not None
        assert tool.annotations.open_world_hint is not None
        assert tool.description and "返回" in tool.description, f"{name} 未说明返回内容"

    for name in ("sql_query", "sql_schema", "powerbi_schema", "powerbi_query",
                 "retrieve_search", "retrieve_schema", "retrieve_doc_read",
                 "contribute", "forecast", "report_html_list", "report_html_get"):
        assert tools[name].annotations.read_only_hint is True
        assert tools[name].annotations.destructive_hint is False

    for name in ("retrieve_cypher", "retrieve_doc_update", "sync",
                 "report_html_publish", "report_html_delete"):
        assert tools[name].annotations.destructive_hint is True

    for name in ("contribute", "forecast", "impact"):
        assert tools[name].annotations.open_world_hint is False


def test_stable_tools_advertise_structured_output_schema():
    tools = _tools()
    assert set(tools["sql_query"].output_schema["properties"]) == {
        "columns", "rows", "row_count",
    }
    assert set(tools["retrieve_schema"].output_schema["properties"]) == {
        "nodes", "relationships",
    }
    assert set(tools["forecast"].output_schema["properties"]) == {
        "metric", "model", "model_reason", "forecast", "summary", "backtest",
        "confidence", "assumptions", "warnings",
    }


def test_sql_query_tool(monkeypatch):
    from sda_mcp.skills.querying_data import SqlResult
    monkeypatch.setattr(query_tools, "_sql_query",
                        lambda sql: SqlResult(columns=[{"name": "a", "dataTypeID": 23}],
                                              rows=[{"a": 1}], row_count=1))
    sc, err, _ = _call("sql_query", {"sql": "SELECT 1"})
    assert not err
    assert sc["row_count"] == 1 and sc["columns"][0]["name"] == "a"


def test_sql_schema_tool_has_no_result_wrapper(monkeypatch):
    expected = [{"schema": "public", "table": "orders", "columns": []}]
    monkeypatch.setattr(query_tools, "_sql_schema", lambda tables: expected)
    sc, err, _ = _call("sql_schema", {"tables": ["public.orders"]})
    assert not err
    assert sc == {"tables": expected}


def test_skill_error_becomes_is_error(monkeypatch):
    from sda_mcp.errors import DataSourceError

    def _boom(sql):
        raise DataSourceError("连不上 Hologres（检查 VPN）")
    monkeypatch.setattr(query_tools, "_sql_query", _boom)
    sc, err, content = _call("sql_query", {"sql": "SELECT 1"})
    assert err is True
    # 可操作 message 进了 text content
    joined = "".join(getattr(c, "text", "") for c in content)
    assert "Hologres" in joined or "VPN" in joined


def test_retrieve_search(monkeypatch):
    monkeypatch.setattr(retrieve_tools, "_search",
                        lambda question, top_k=5, targets=None, strategy="vector":
                        {"question": question, "strategy": strategy, "results": []})
    sc, err, _ = _call("retrieve_search", {"question": "Q"})
    assert sc["results"] == []
    assert sc["strategy"] == "hybrid"


def test_contribute(monkeypatch):
    monkeypatch.setattr(analyze_tools, "_contribute",
                        lambda method, payload: {
                            "method": method,
                            "summary": {},
                            "rows": [],
                            "checks": {},
                        })
    sc, err, _ = _call("contribute", {"method": "add", "payload": {"a": [1, 2]}})
    assert sc["method"] == "add"


def test_chart_returns_image_block(monkeypatch):
    from sda_mcp.skills.visualizing import ChartResult
    monkeypatch.setattr(visualize_tools, "_render",
                        lambda spec, format="png", dpi=144: ChartResult(
                            format="png", dpi=144, width=10, height=20,
                            data=b"\x89PNG\r\n\x1a\n", warnings=[]))
    sc, err, content = _call("chart", {"spec": {"type": "bar", "title": "T"}, "format": "png"})
    assert not err
    # 至少有一个 image 内容块（Blob 上传会失败因无凭证，不影响图片块）
    types = [getattr(c, "type", "") for c in content]
    assert "image" in types


def test_report_publish(monkeypatch):
    from sda_mcp.skills.building_reports.html_reports import PublishResult
    monkeypatch.setattr(report_tools, "_publish",
                        lambda report, rid: PublishResult(url=f"https://app/report/{rid}",
                                                          report_id=rid, blob_url="b"))
    sc, err, _ = _call("report_html_publish", {"id": "r1", "report": {"meta": {"title": "t"}}})
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
        {"prompt": "报告", "response_format": "url"},
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
        {"prompt": "报告", "response_format": "b64_json"},
    )
    assert not err
    assert sc["images"][0]["url"] is None
    assert [getattr(block, "type", "") for block in content] == ["image", "text"]


def test_retrieve_doc_update(monkeypatch):
    monkeypatch.setattr(retrieve_tools, "_update_doc",
                        lambda doc, content: {"updated": True, "document_id": doc})
    sc, err, _ = _call("retrieve_doc_update", {"doc": "DOC1", "content": "# 新"})
    assert not err
    assert sc == {"updated": True, "document_id": "DOC1"}


def test_retrieve_doc_inputs_only_advertise_docx_token():
    tools = _tools()
    for name in ("retrieve_doc_read", "retrieve_doc_update"):
        description = tools[name].input_schema["properties"]["doc"]["description"]
        assert "docx 文档 token" in description
        assert "不支持完整 URL" in description
        assert "URL 或 token" not in description


def test_retrieve_schema_tool(monkeypatch):
    monkeypatch.setattr(
        retrieve_tools,
        "_schema",
        lambda: {"nodes": {"指标": {
            "properties": {"指标ID": "STRING"},
            "unique": ["指标ID"],
        }}, "relationships": []},
    )
    sc, err, _ = _call("retrieve_schema", {})
    assert not err
    assert sc["nodes"]["指标"]["properties"]["指标ID"] == "STRING"


def test_sync_tool_schema(monkeypatch):
    """sync 只暴露 dry_run 一个字段（平铺 schema）。

    平铺签名下 SDK 动态参数模型 extra="ignore"：未知键（如旧的 only）被静默
    丢弃、不报错——与 Pydantic 模型入参 + extra="forbid" 时的行为不同，
    客户端只应按广告出的 schema 传参。
    """
    from sda_mcp.skills import retrieving_context_sync

    monkeypatch.setattr(
        retrieving_context_sync,
        "sync_graph",
        lambda dry_run=False: {"dry_run": dry_run, "validated": True},
    )
    tools = _tools()
    assert set(tools["sync"].input_schema["properties"]) == {"dry_run"}

    sc, err, _ = _call("sync", {"dry_run": True})
    assert not err
    assert sc == {"dry_run": True, "validated": True}

    # 未知键被忽略（extra=ignore），dry_run 缺省 False
    sc, err, _ = _call("sync", {"only": "fetch"})
    assert not err
    assert sc == {"dry_run": False, "validated": True}


def test_validation_error_is_error():
    # Pydantic 校验失败（缺必填）→ is_error
    sc, err, _ = _call("sql_query", {})
    assert err
