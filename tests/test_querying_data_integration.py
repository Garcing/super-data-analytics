"""querying_data 集成对照：连真服务跑 Python 内核 vs 原 Node CLI。
默认跳过；SDA_INTEGRATION=1 时启用（需 VPN + config.json 真凭证 + 原 Node CLI 可跑）。"""
import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="集成测试默认跳过；设 SDA_INTEGRATION=1 启用（需 VPN+凭证+Node CLI）")

REPO = Path(__file__).resolve().parent.parent.parent
QUERY_JS = REPO / "querying-data" / "scripts" / "query.js"


def _node(args: list[str], stdin: str | None = None) -> dict:
    proc = subprocess.run(
        ["node", str(QUERY_JS), *args],
        capture_output=True, text=True, timeout=90, input=stdin)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_sql_select_parity():
    from sda_mcp.skills.querying_data import sql_query
    sql = "SELECT 1 AS one, 'x' AS two"
    cli = _node(["sql", "query", "--sql", sql])
    core = sql_query(sql)
    # dataTypeID 可能因驱动不同有差异，只比对列名与行数据
    assert [c["name"] for c in core.columns] == [c["name"] for c in cli["columns"]]
    assert core.rows == cli["rows"]


def test_powerbi_list_tools_parity():
    from sda_mcp.skills.querying_data import powerbi_list_tools
    cli = _node(["powerbi", "list-tools"])
    core = powerbi_list_tools()
    assert len(core) == len(cli)


def test_powerbi_query_parity():
    """跑一条简单 DAX 对照 Node 与 Python。artifactId 走环境变量（语义模型已移出 config.json）。"""
    artifact_id = os.environ.get("SDA_POWERBI_ARTIFACT_ID")
    if not artifact_id:
        pytest.skip("设 SDA_POWERBI_ARTIFACT_ID 为某语义模型 GUID 以跑此对照")
    from sda_mcp.skills.querying_data import powerbi_query
    payload = {"artifactId": artifact_id, "daxQueries": ["EVALUATE ROW(1)"], "maxRows": 10}
    cli = _node(["powerbi", "query", "--payload", json.dumps(payload)])
    core = powerbi_query(artifact_id, payload["daxQueries"], 10)
    assert core == cli
