"""锁死工具描述中的关键契约披露(QA P1-d / P2)。

裸接入 Agent 只凭 tool list + Skill 使用服务:waterfall 等复杂图型的字段契约、
MDE 语义、Power BI 解码行为必须出现在工具描述里,否则不可发现(QA 端到端组
两种直觉写法构造 waterfall 均失败)。
"""
import asyncio


def _tools():
    from mcp import Client
    from sda_mcp import server  # noqa: F401  注册工具
    from sda_mcp.tools._common import mcp

    async def _run():
        async with Client(mcp) as client:
            return {t.name: t for t in (await client.list_tools()).tools}
    return asyncio.run(_run())


def _call(name, args):
    from mcp import Client
    from sda_mcp.tools._common import mcp

    async def _run():
        async with Client(mcp) as client:
            r = await client.call_tool(name, args)
            return r.is_error, r.content
    return asyncio.run(_run())


def test_chart_description_documents_complex_type_contracts():
    desc = _tools()["chart"].input_schema["properties"]["spec"]["description"]
    assert "waterfall" in desc and "start_value" in desc
    assert "combo" in desc and "heatmap" in desc


def test_impact_description_discloses_mde_semantics():
    desc = _tools()["impact"].input_schema["properties"]["payload"]["description"]
    assert "绝对" in desc and "minimum_detectable_effect" in desc


def test_powerbi_description_mentions_decoded_content():
    tools = _tools()
    assert "解码" in tools["powerbi_query"].description
    assert "解码" in tools["powerbi_schema"].description


def test_chart_spec_error_names_field():
    """visualizing-data 承诺"报错指向具体字段"——锁死该行为。"""
    err, content = _call("chart", {"spec": {
        "type": "bar", "title": "t", "subtitle": "s",
        "data": [{"x": "a", "y": 1}], "encoding": {"x": "x"}}})
    assert err is True
    text = "".join(getattr(c, "text", "") for c in content)
    assert "encoding" in text and "y" in text
