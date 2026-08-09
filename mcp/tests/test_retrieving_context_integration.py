"""retrieving_context 集成对照：连真 Neo4j 跑 Python 内核 vs 原 Node CLI。
默认跳过；SDA_INTEGRATION=1 启用（需 Neo4j 在跑 + config.json 凭证 + Node CLI）。"""
import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="集成测试默认跳过；设 SDA_INTEGRATION=1 启用")

REPO = Path(__file__).resolve().parent.parent.parent
RETRIEVE_JS = REPO / "retrieving-context" / "scripts" / "retrieve.js"


def _node(args):
    proc = subprocess.run(["node", str(RETRIEVE_JS), *args],
                          capture_output=True, text=True, timeout=90)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_schema_parity():
    from sda_mcp.skills.retrieving_context import schema as py_schema
    assert py_schema() == _node(["schema"])


def test_cypher_parity():
    from sda_mcp.skills.retrieving_context import cypher
    statement = "MATCH (n) RETURN count(n) AS c LIMIT 1"
    cli = _node(["cypher", "--statement", statement])
    core = cypher(statement)
    assert core == cli


def test_search_parity():
    """ONNX 向量与存量 PyTorch 向量兼容性验证：命中 label 集合一致 + top1 label 相同。"""
    from sda_mcp.skills.retrieving_context import search
    q = "GMV 是什么"
    cli = _node(["search", "--question", q, "--top-k", "5"])
    core = search(q, top_k=5)
    assert {h["label"] for h in core["results"]} == {h["label"] for h in cli["results"]}
    if core["results"] and cli["results"]:
        assert core["results"][0]["label"] == cli["results"][0]["label"]
