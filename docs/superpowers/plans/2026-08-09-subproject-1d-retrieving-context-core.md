# 子项目 1.D 实现计划：retrieving_context 内核（Neo4j + fastembed ONNX）

> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development 或 executing-plans。`- [ ]` 复选框跟踪。

**Goal:** 把 `retrieving-context`（Node 壳 + Python embedding 子进程 + Neo4j）重写为**纯 Python 内核**：fastembed(ONNX) 做 embedding（in-process，不再 spawn Python 子进程）、neo4j Python 驱动做向量检索+图扩展+Cypher、lark-cli 子进程取飞书文档。去 CLI/三态/`{ok}` 信封，失败抛 `SkillError`。

**Architecture:** 原仓库树不动。新 `mcp/sda_mcp/skills/retrieving_context.py`。原 `retrieving-context/scripts/retrieve.js`（全文）是**忠实移植基准**——实现者读它，把每段 Cypher、属性清洗、图扩展逻辑等价搬到 Python。embedding 用 fastembed `BAAI/bge-small-zh-v1.5`（已确认 fastembed 支持，512 维，与 Neo4j 现存 PyTorch 向量同模型同空间，**无需重 embedding**）。复用 `mcp/sda_mcp/config.py`（graph-config 块 + NEO4J_*）。

**Tech Stack:** neo4j（Python 驱动）、fastembed（ONNX embedding）、onnxruntime（fastembed 依赖）。新增到 pyproject。lark-cli（外部 Node 工具，子进程调用）。

**关键行为（对齐 retrieve.js）：**
- INTERNAL_PROPS 剥离（retrieve.js:68-74, 572-580）：search_text/embedding/embedding_model/embedding_dimensions/embedding_updated_at 不出现在输出。
- schema（buildSchema, 531-566）：从 graph-config 构建 entities/relationships，不连库。
- 向量检索：`SHOW VECTOR INDEXES YIELD name, labelsOrTypes` 找索引名（318-333）；`db.index.vector.queryNodes($index, $topK, $embedding)` + label 过滤（335-364）。
- 图扩展（fetchGraphContext, 402-485）：沿 graph-config.relationships 的边扩邻居，LIMIT 20；`表关系` 命中再走 fetchTableRelationshipChain（370-400）。
- cypher（runCypher, 491-525）：裸 Cypher，node/rel 取 properties，剥内部属性；Python neo4j 驱动返回的整数已是 Python int（无需 JS 的 toNumber）。
- doc（fetchLarkDoc, 211-269）：调 lark-cli `docs +fetch --doc <doc> --doc-format markdown --as user`，解析 envelope，取 data.document。
- credentials: NEO4J_URI(默认 bolt://localhost:7687)/NEO4J_DATABASE(neo4j)/NEO4J_USER(neo4j)/NEO4J_PASSWORD(必填，缺→ConfigError)。

---

## 文件结构

- Create: `mcp/sda_mcp/skills/retrieving_context.py`
- Modify: `mcp/pyproject.toml`（加 neo4j、fastembed）
- Modify: `mcp/sda_mcp/skills/__init__.py`（导出）
- Test: `mcp/tests/test_retrieving_context.py`（mock）
- Test: `mcp/tests/test_retrieving_context_integration.py`（env 门控）

**不修改**：`retrieving-context/` 下任何文件。

---

## Task 1: retrieving_context.py + 依赖

- [ ] **Step 1: 写 `mcp/sda_mcp/skills/retrieving_context.py`**

实现者参照 `retrieving-context/scripts/retrieve.js` 全文移植。骨架与契约如下：

```python
"""retrieving_context 内核：GraphRAG 向量检索 + 图扩展 + Cypher + 飞书文档，
从原 retrieve.js 移植为纯 Python。embedding 用 fastembed(ONNX) in-process。
去 CLI/三态/{ok} 信封；失败抛 SkillError。行为对齐 retrieving-context/scripts/retrieve.js。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
from typing import Any

from neo4j import GraphDatabase

from sda_mcp.config import load_config
from sda_mcp.errors import ConfigError, DataSourceError, ExternalAPIError, ValidationError

_INTERNAL_PROPS = {
    "search_text", "embedding", "embedding_model", "embedding_dimensions", "embedding_updated_at",
}


def _clean_properties(raw: dict[str, Any]) -> dict[str, Any]:
    # 对齐 retrieve.js cleanProperties (572-580)
    return {k: v for k, v in (raw or {}).items() if k not in _INTERNAL_PROPS}


def _build_schema(gc: dict[str, Any]) -> dict[str, Any]:
    # 对齐 retrieve.js buildSchema (531-566)
    entities = []
    for label, cfg in (gc.get("entities") or {}).items():
        entities.append({
            "label": label,
            "key_field": cfg.get("key_field"),
            "table_id": cfg.get("table_id"),
            "vector_index": cfg.get("vector_index", True),
        })
    relationships = []
    for rel in (gc.get("relationships") or []):
        out = {"type": rel.get("type"), "from": rel.get("from"), "to": rel.get("to")}
        if rel.get("match"):
            out["match"] = {
                "source_field": rel["match"].get("source_field"),
                "target_field": rel["match"].get("target_field"),
            }
        if rel.get("via"):
            out["via"] = {
                "table_id": rel["via"].get("table_id"),
                "from_field": rel["via"].get("from_field"),
                "to_field": rel["via"].get("to_field"),
                "properties": rel["via"].get("properties", []),
            }
        relationships.append(out)
    return {"embedding": gc.get("embedding", {}), "entities": entities, "relationships": relationships}


def schema() -> dict[str, Any]:
    """返回 graph-config 的 schema 视图。不连库。"""
    gc = load_config().get("graph-config", {})
    return _build_schema(gc)


# ---------- embedding (fastembed ONNX, 懒加载单例) ----------

@lru_cache(maxsize=1)
def _embedder():
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise ConfigError("fastembed 未安装") from exc
    gc = load_config().get("graph-config", {})
    model = gc.get("embedding", {}).get("model", "BAAI/bge-small-zh-v1.5")
    return TextEmbedding(model_name=model)


def embed(text: str) -> list[float]:
    if not isinstance(text, str) or not text.strip():
        raise ValidationError("question 不能为空")
    return list(next(_embedder().embed([text])))


# ---------- Neo4j ----------

class Neo4jClient:
    def __init__(self) -> None:
        env = load_config().get("env", {})
        uri = env.get("NEO4J_URI", "bolt://localhost:7687")
        database = env.get("NEO4J_DATABASE", "neo4j")
        user = env.get("NEO4J_USER", "neo4j")
        password = env.get("NEO4J_PASSWORD")
        if not password:
            raise ConfigError("NEO4J_PASSWORD 未在 config.json 的 env 块中找到")
        self._database = database
        try:
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
        except Exception as exc:
            raise DataSourceError(f"Neo4j 驱动初始化失败: {exc}") from exc

    def close(self) -> None:
        self._driver.close()

    def _session(self):
        return self._driver.session(database=self._database)

    # 对齐 retrieve.js findVectorIndexName (318-333)
    def find_vector_index_name(self, label: str) -> str | None:
        with self._session() as s:
            try:
                result = s.run("SHOW VECTOR INDEXES YIELD name, labelsOrTypes")
                for rec in result:
                    labels = rec["labelsOrTypes"]
                    if labels and label in labels:
                        return rec["name"]
            except Exception:
                return None
        return None

    # 对齐 searchVectorIndex (335-364)：Cypher 原样移植（label 反引号转义）
    def search_vector_index(self, index_name: str, label: str, embedding: list[float], top_k: int) -> list[dict]:
        esc = label.replace("`", "``")
        cypher = (
            "CALL db.index.vector.queryNodes($indexName, $topK, $embedding) "
            "YIELD node, score "
            f"WHERE node:`{esc}` "
            "RETURN elementId(node) AS id, score, properties(node) AS properties "
            "ORDER BY score DESC"
        )
        try:
            result = self._session().run(cypher, indexName=index_name, topK=top_k, embedding=embedding)
            return [{"id": r["id"], "score": r["score"], "properties": r["properties"]} for r in result]
        except Exception:
            return []

    # 对齐 fetchTableRelationshipChain (370-400)：Cypher 原样移植
    def fetch_table_relationship_chain(self, relationship_id) -> list[dict]:
        cypher = (
            "MATCH (current:`表关系` {`表关系ID`: $relationshipId}) "
            "MATCH path = (current)-[:`基于`*0..10]->(step:`表关系`) "
            "OPTIONAL MATCH (step)-[tableRel]->(table:`表`) "
            "WHERE type(tableRel) IN ['起始于', '加入'] "
            "RETURN length(path) AS depth, properties(step) AS relationship, "
            "collect(DISTINCT {role: type(tableRel), properties: properties(table)}) AS tables "
            "ORDER BY depth DESC"
        )
        with self._session() as s:
            rows = []
            for rec in s.run(cypher, relationshipId=relationship_id):
                tables = [
                    {"role": t["role"], "properties": _clean_properties(dict(t["properties"]))}
                    for t in (rec["tables"] or []) if t and t.get("role") and t.get("properties")
                ]
                rows.append({"depth": rec["depth"], "relationship": _clean_properties(dict(rec["relationship"])), "tables": tables})
            return rows

    # 对齐 fetchGraphContext (402-485)：实现者按 retrieve.js:402-485 移植
    def fetch_graph_context(self, label: str, node_id: str, relationships: list[dict]) -> dict:
        ...  # 见 Step 1 末尾的执行注意

    # 对齐 runCypher (491-525)
    def run_cypher(self, statement: str) -> list[dict]:
        with self._session() as s:
            result = s.run(statement)
            rows = []
            for rec in result:
                obj = {}
                for key in rec.keys:
                    val = rec[key]
                    if hasattr(val, "properties"):           # node/relationship
                        val = _clean_properties(dict(val.properties))
                    elif isinstance(val, list):
                        val = [
                            _clean_properties(dict(v.properties)) if hasattr(v, "properties") else v
                            for v in val
                        ]
                    obj[key] = val
                rows.append(obj)
            return rows


def search(question: str, top_k: int = 5, targets: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        raise ValidationError("question 不能为空")
    gc = load_config().get("graph-config", {})
    entities = gc.get("entities") or {}
    relationships = gc.get("relationships") or []
    target_labels = [
        label for label, cfg in entities.items()
        if cfg.get("vector_index", True) and (not targets or label in targets)
    ]
    embedding_vec = embed(question)
    client = Neo4jClient()
    try:
        all_results = []
        for label in target_labels:
            index_name = client.find_vector_index_name(label)
            if not index_name:
                continue
            for hit in client.search_vector_index(index_name, label, embedding_vec, top_k):
                context = client.fetch_graph_context(label, hit["id"], relationships) if relationships else {}
                all_results.append({
                    "label": label,
                    "score": hit["score"],
                    "properties": _clean_properties(dict(hit["properties"])),
                    "context": context,
                })
        all_results.sort(key=lambda r: r["score"], reverse=True)
        return {"question": question, "results": all_results}
    finally:
        client.close()


def cypher(statement: str) -> dict[str, Any]:
    if not isinstance(statement, str) or not statement.strip():
        raise ValidationError("statement 不能为空")
    client = Neo4jClient()
    try:
        return {"cypher": statement, "rows": client.run_cypher(statement)}
    finally:
        client.close()


# ---------- 飞书文档（lark-cli 子进程） ----------

def doc(doc: str) -> dict[str, Any]:
    if not isinstance(doc, str) or not doc.strip():
        raise ValidationError("doc 不能为空")
    args = ["docs", "+fetch", "--doc", doc, "--doc-format", "markdown", "--as", "user"]
    env = {**__import__("os").environ,
           "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1", "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1"}
    lark = shutil.which("lark-cli")
    try:
        if lark:
            proc = subprocess.run([lark, *args], capture_output=True, text=True, timeout=60, env=env)
        else:
            proc = subprocess.run(["lark-cli", *args], capture_output=True, text=True, timeout=60, env=env)
    except FileNotFoundError as exc:
        raise ExternalAPIError("未找到 lark-cli，请先 npm install -g @larksuite/cli 并 lark-cli auth login") from exc
    if proc.returncode != 0:
        raise ExternalAPIError(f"读取飞书文档失败: {(proc.stderr or proc.stdout).strip()[:300]}")
    try:
        envelope = json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ExternalAPIError("lark-cli 返回了无法解析的 JSON") from exc
    if envelope.get("ok") is not True:
        msg = (envelope.get("error") or {}).get("message") or (envelope.get("error") or {}).get("hint") or "未知错误"
        raise ExternalAPIError(f"读取飞书文档失败: {msg}")
    document = (envelope.get("data") or {}).get("document")
    if not document:
        raise ExternalAPIError("lark-cli 返回成功，但结果中缺少 document")
    return document
```

> **执行注意（不是占位符）：** `fetch_graph_context` 的 `...` 处，实现者按 `retrieving-context/scripts/retrieve.js:402-485` 完整移植：遍历 `relationships` 中 from/to 命中 label 的关系；按自环(from===to, 无向 `-[:T]-`) / from(有向 `-[:T]->`) / to(有向 `<-[:T]-`) 构造 relPattern；反引号转义 label 与 relType；`MATCH (n){relPattern}(other:\`{escOther}\`) WHERE elementId(n)=$nodeId{selfExclude} RETURN properties(other) AS props LIMIT 20`（selfExclude 仅自环时 `AND elementId(other) <> $nodeId`）；把邻居清洗后按 otherLabel 分组塞进 context；若 otherLabel 是 `表关系` 且 props 有 `表关系ID`，调 `fetch_table_relationship_chain` 挂到该邻居的 `关系链`；最后若 label 本身是 `表关系`，再查起点的 `表关系ID` 并挂 `context["关系链"]`。逐行对齐 retrieve.js，异常时记 stderr 继续。

- [ ] **Step 2: 加依赖到 `mcp/pyproject.toml`**

```toml
    "neo4j>=5.20",
    "fastembed>=0.3",
```

- [ ] **Step 3: 验证 import（不连库、不触发模型下载）**

```bash
cd mcp && python -c "from sda_mcp.skills import retrieving_context as r; print('ok', hasattr(r,'search'), hasattr(r,'schema'))"
```
Expected: `ok True True`（仅 import；fastembed 懒加载，此时不下载模型）。若 neo4j/fastembed 未装，`pip install neo4j fastembed`。

- [ ] **Step 4: 提交**

```bash
git add mcp/sda_mcp/skills/retrieving_context.py mcp/pyproject.toml
git commit -m "feat(mcp): retrieving_context core (Neo4j + fastembed ONNX, pure Python)"
```

---

## Task 2: mock 单元测试

**Files:** Test `mcp/tests/test_retrieving_context.py`

- [ ] **Step 1: 写测试（离线 mock）**

覆盖（实现者补全，用 monkeypatch mock `Neo4jClient` 的方法与 `embed`）：
- `_clean_properties` 剥 INTERNAL_PROPS。
- `_build_schema` / `schema()`：构造 graph-config → 正确 entities/relationships；不连库（mock load_config）。
- `embed`：空 question → ValidationError；mock fastembed 返回固定向量。
- `search`：mock `embed` 返回向量 + mock `Neo4jClient`（find_vector_index_name 返回索引名、search_vector_index 返回 2 条命中、fetch_graph_context 返回 {}），断言结果按 score 降序、properties 已清洗、无 INTERNAL_PROPS、无 `ok`。
- `cypher`：空 statement → ValidationError；mock `run_cypher` 返回含 node properties 的行 → 清洗后输出。
- `doc`：空 doc → ValidationError；mock `subprocess.run` 返回 ok envelope → 返回 document；mock 返回 `ok:false` → ExternalAPIError；lark-cli 不存在（monkeypatch shutil.which → None 且 subprocess FileNotFoundError）→ ExternalAPIError。

骨架（实现者展开）：

```python
"""retrieving_context 内核 mock 单元测试（离线）。"""
import json
import pytest
import sda_mcp.config as cfg
from sda_mcp.errors import ConfigError, ValidationError, ExternalAPIError
from sda_mcp.skills import retrieving_context as r


GC = {
    "embedding": {"model": "BAAI/bge-small-zh-v1.5", "dimensions": 512},
    "entities": {"指标": {"key_field": "指标ID", "table_id": "tbl1", "vector_index": True},
                 "表": {"key_field": "表ID", "table_id": "tbl2", "vector_index": False}},
    "relationships": [{"type": "属于", "from": "指标", "to": "表"}],
}


def test_clean_properties_strips_internal():
    out = r._clean_properties({"name": "GMV", "embedding": [1, 2], "search_text": "x"})
    assert out == {"name": "GMV"}


def test_schema_builds_from_graph_config(monkeypatch):
    monkeypatch.setattr(cfg, "load_config", lambda: {"graph-config": GC})
    s = r.schema()
    labels = [e["label"] for e in s["entities"]]
    assert "指标" in labels and "表" in labels
    assert s["relationships"][0]["type"] == "属于"
    assert not hasattr(s, "ok")


def test_search_sorts_and_cleans(monkeypatch):
    monkeypatch.setattr(cfg, "load_config", lambda: {"graph-config": GC, "env": {"NEO4J_PASSWORD": "p"}})
    monkeypatch.setattr(r, "embed", lambda text: [0.1] * 512)

    class FakeClient:
        def __init__(self): pass
        def close(self): pass
        def find_vector_index_name(self, label): return "idx" if label == "指标" else None
        def search_vector_index(self, idx, label, emb, top_k):
            return [{"id": "a", "score": 0.9, "properties": {"name": "A", "embedding": [0]}},
                    {"id": "b", "score": 0.5, "properties": {"name": "B"}}]
        def fetch_graph_context(self, label, nid, rels): return {}
    monkeypatch.setattr(r, "Neo4jClient", FakeClient)
    out = r.search("GMV", top_k=5)
    assert out["results"][0]["score"] == 0.9
    assert out["results"][0]["properties"] == {"name": "A"}  # embedding 已剥
    assert not hasattr(out, "ok")


def test_search_empty_question(monkeypatch):
    monkeypatch.setattr(cfg, "load_config", lambda: {"graph-config": GC, "env": {"NEO4J_PASSWORD": "p"}})
    with pytest.raises(ValidationError):
        r.search("   ")


def test_cypher_empty():
    with pytest.raises(ValidationError):
        r.cypher("  ")


def test_doc_ok(monkeypatch):
    class P:
        returncode = 0
        stdout = json.dumps({"ok": True, "data": {"document": {"document_id": "d1", "content": "# t"}}})
        stderr = ""
    monkeypatch.setattr(r.shutil, "which", lambda name: "/fake/lark-cli")
    monkeypatch.setattr(r.subprocess, "run", lambda *a, **k: P())
    d = r.doc("someurl")
    assert d["document_id"] == "d1"


def test_doc_failure_envelope(monkeypatch):
    class P:
        returncode = 0
        stdout = json.dumps({"ok": False, "error": {"message": "no perm"}})
        stderr = ""
    monkeypatch.setattr(r.shutil, "which", lambda name: "/fake/lark-cli")
    monkeypatch.setattr(r.subprocess, "run", lambda *a, **k: P())
    with pytest.raises(ExternalAPIError):
        r.doc("someurl")


def test_doc_empty():
    with pytest.raises(ValidationError):
        r.doc("  ")
```

- [ ] **Step 2: 运行**

```bash
cd mcp && python -m pytest tests/test_retrieving_context.py -v
```
Expected: 全绿。

- [ ] **Step 3: 提交**

```bash
git add mcp/tests/test_retrieving_context.py
git commit -m "test(mcp): retrieving_context mock unit tests (schema, search, cypher, doc)"
```

---

## Task 3: 集成对照（env 门控）+ 导出 + 全量

- [ ] **Step 1: 写 `mcp/tests/test_retrieving_context_integration.py`（默认 skip）**

```python
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
    """ONNX 向量与存量 PyTorch 向量兼容性验证：同一问题，Python(fastembed) vs Node(sentence-transformers)
    返回的命中 label 集合与 top1 score 应高度一致。"""
    from sda_mcp.skills.retrieving_context import search
    q = "GMV 是什么"
    cli = _node(["search", "--question", q, "--top-k", "5"])
    core = search(q, top_k=5)
    # 命中的 label 集合一致；首条命中 label 相同（向量空间兼容的间接证据）
    assert {h["label"] for h in core["results"]} == {h["label"] for h in cli["results"]}
    if core["results"] and cli["results"]:
        assert core["results"][0]["label"] == cli["results"][0]["label"]
```

- [ ] **Step 2: 确认默认 skip**

```bash
cd mcp && python -m pytest tests/test_retrieving_context_integration.py -q -rs
```
Expected: 3 skipped。

- [ ] **Step 3: 导出 + 全量**

`mcp/sda_mcp/skills/__init__.py` 追加：
```python
from sda_mcp.skills.retrieving_context import search as retrieve_search, cypher as retrieve_cypher, schema as retrieve_schema, doc as retrieve_doc
```
加入 `__all__`：`"retrieve_search"`, `"retrieve_cypher"`, `"retrieve_schema"`, `"retrieve_doc"`。

```bash
cd mcp && python -m pytest -q
```
Expected: 无失败（集成 skip）。

- [ ] **Step 4: 提交**

```bash
git add mcp/tests/test_retrieving_context_integration.py mcp/sda_mcp/skills/__init__.py
git commit -m "test(mcp): retrieving_context env-gated integration parity + export"
```

---

## 完成标准

- [ ] `search`/`cypher`/`schema`/`doc` 四个入口，去 CLI/`{ok}` 信封，失败抛 SkillError 子类。
- [ ] embedding 用 fastembed ONNX in-process（不 spawn Python 子进程）。
- [ ] 图扩展、向量检索、Cypher、属性清洗行为对齐 retrieve.js。
- [ ] mock 单元测试离线全绿。
- [ ] 集成对照默认 skip；`SDA_INTEGRATION=1` 时验证 ONNX 向量与原 Node(sentence-transformers) 命中一致。
- [ ] 原 `retrieving-context/` 零改动。
- [ ] pyproject 含 neo4j、fastembed。

## 待实测（开集成测试时确认）

- fastembed `BAAI/bge-small-zh-v1.5` 向量与 Neo4j 现存（PyTorch 生成）向量的检索命中一致性（search_parity）。若 top1 命中偏差大 → 说明 ONNX 量化引入偏差，需评估是否全量重 embedding（但同模型权重，预期一致）。
```
