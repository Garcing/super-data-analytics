# 子项目 1.G 实现计划：sync pipeline 内核（ONNX 一致）+ sync 工具

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 `retrieving-context/scripts/pipeline/` 的 GraphRAG 同步流程移植成干净 Python 内核，让服务器 Neo4j（当前为空）能一条命令灌入飞书多维表数据。**关键：embedding 统一用 fastembed(ONNX)**（替代原 sentence-transformers/PyTorch），与查询侧 `retrieving_context.embed()` 同源 → 向量自洽、parity 零风险。并加 `sync` MCP 工具。

**Architecture:** 单文件 `retrieving_context_sync.py`。三阶段（fetch 飞书 → 构图 → embed），逻辑忠实复刻原 pipeline，但去 CLI/argparse/print，用 fastembed 批量 embed，失败抛 SkillError。复用已有 `Neo4jClient`（retrieving_context）与 `embed()`。`sync()` 公共函数；MCP 工具 `sync` 包装它。

**Tech Stack:** neo4j（已依赖）、fastembed（已依赖）、subprocess（lark-cli，同 using_templates）。无新依赖。

**源文件（必读，逐行对齐逻辑）：**
- `retrieving-context/scripts/pipeline/feishu_reader.py` —— `fetch_table_fields` / `fetch_table_records`（lark-cli `base +field-list`/`+record-list --as bot`，分页、select/multi_select 取值）
- `retrieving-context/scripts/pipeline/graph_builder.py` —— `build_nodes` / `build_relationships` / `clear_graph`（Cypher 构图，含 via 中间表）—— **你实现前先完整读此文件**
- `retrieving-context/scripts/pipeline/embedding.py` —— `generate_search_text` / `create_vector_indexes` / `embed_nodes`（**embed_nodes 的 SentenceTransformer 部分换成 fastembed**，其余照搬）
- `retrieving-context/scripts/pipeline/sync.py` —— 编排（fetch_all_feishu_data / 三阶段）—— 照搬编排逻辑

**Config：** `FEISHU_GRAPH_BITABLE_APP_TOKEN`（必填，取数）、`NEO4J_*`（Neo4jClient 已读）、`graph-config`（entities/relationships/embedding）。`FEISHU_GRAPH_BITABLE_APP_TOKEN` 走 `get_env`（必填）。

**范围：** 仅 1.G。原 `retrieving-context/` 一律不动（铁律）。新代码只放 `mcp/sda_mcp/skills/retrieving_context_sync.py` + 改 `tools/retrieve_tools.py` 加 `sync` 工具 + 测试。

---

## 文件结构

- Create: `mcp/sda_mcp/skills/retrieving_context_sync.py` —— sync 内核
- Modify: `mcp/sda_mcp/skills/__init__.py` —— 导出 `sync_graph`
- Modify: `mcp/sda_mcp/tools/retrieve_tools.py` —— 加 `sync` 工具
- Create: `mcp/tests/test_retrieving_context_sync.py`

**不修改**：`retrieving-context/` 下任何文件。

---

## Task 1: retrieving_context_sync.py 内核

**Files:** `mcp/sda_mcp/skills/retrieving_context_sync.py`

- [ ] **Step 1: 先读源文件**（graph_builder.py 全文 + feishu_reader.py + embedding.py + sync.py），把 Cypher 与数据结构对齐。**embed 之外逻辑逐行忠实移植。**

- [ ] **Step 2: 写 `retrieving_context_sync.py`**

骨架（你补全 Cypher/逻辑，**严格对齐源文件**）：

```python
"""GraphRAG sync 内核：飞书多维表 → Neo4j 图 → fastembed(ONNX) 向量。

移植 retrieving-context/scripts/pipeline/{sync,feishu_reader,graph_builder,embedding}.py，
去 CLI/argparse/print；embedding 用 fastembed（与查询侧 retrieving_context.embed 同源 →
向量自洽，无 ONNX/PyTorch 混用 parity 风险）。失败抛 SkillError。

公共入口：sync_graph(only=None, dry_run=False, force_embed=False) -> dict[str,Any]。
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from typing import Any

from sda_mcp.config import get_env, load_config
from sda_mcp.errors import ConfigError, ExternalAPIError, ValidationError
from sda_mcp.skills.retrieving_context import Neo4jClient, embed as _embed_text

_SKIP_PROPS = frozenset({"search_text", "embedding", "embedding_model",
                         "embedding_dimensions", "embedding_updated_at"})


# ---------- Phase 1: feishu fetch（移植 feishu_reader.py）----------

def _lark_cli(*args: str) -> dict:
    """lark-cli base 子命令，--as bot，返回解析后 JSON。移植 feishu_reader._run_lark_cli。"""
    lark = shutil.which("lark-cli") or "lark-cli"
    try:
        proc = subprocess.run([lark, *args, "--as", "bot"],
                              capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise ConfigError("未找到 lark-cli") from exc
    if proc.returncode != 0:
        raise ExternalAPIError(f"lark-cli 失败: {(proc.stderr or '').strip()[:300]}")
    lines = proc.stdout.strip().split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("{")), None)
    if start is None:
        raise ExternalAPIError(f"lark-cli 无 JSON 输出: {proc.stdout[:300]}")
    try:
        return json.loads("\n".join(lines[start:]))
    except json.JSONDecodeError as exc:
        raise ExternalAPIError("lark-cli 返回非 JSON") from exc


def fetch_table_fields(app_token: str, table_id: str) -> list[dict]:
    """移植 feishu_reader.fetch_table_fields（过滤 auto_number）。"""
    data = _lark_cli("base", "+field-list", "--base-token", app_token, "--table-id", table_id)
    return [{"name": f["name"], "type": f["type"], "id": f["id"]}
            for f in data.get("data", {}).get("fields", []) if f["type"] != "auto_number"]


def _extract_cell(field_type: str, cell: Any) -> Any:
    """移植 feishu_reader._extract_cell_value。"""
    if cell is None:
        return None
    if field_type in ("select", "multi_select") and isinstance(cell, list):
        return cell[0] if field_type == "select" and len(cell) == 1 else cell
    if isinstance(cell, str):
        return cell.strip() or None
    return cell


def fetch_table_records(app_token: str, table_id: str, fields: list[dict] | None = None) -> list[dict]:
    """移植 feishu_reader.fetch_table_records（分页 200，列对齐，过滤 None）。"""
    if fields is None:
        fields = fetch_table_fields(app_token, table_id)
    field_map = {f["name"]: f["type"] for f in fields}
    field_names = {f["name"] for f in fields}
    all_rows: list[list] = []
    offset = 0
    while True:
        resp = _lark_cli("base", "+record-list", "--base-token", app_token, "--table-id", table_id,
                         "--format", "json", "--limit", "200", "--offset", str(offset))
        payload = resp.get("data", {})
        rows = payload.get("data", [])
        col_names = payload.get("fields", [])
        col_index = {n: i for i, n in enumerate(col_names)}
        all_rows.extend(rows)
        if not payload.get("has_more", False) or len(rows) < 200:
            break
        offset += len(rows)
    records = []
    for row in all_rows:
        rec = {}
        for name in field_names:
            if name in col_index:
                val = _extract_cell(field_map[name], row[col_index[name]])
                if val is not None:
                    rec[name] = val
        records.append(rec)
    return records


def _fetch_all_feishu(gc: dict) -> dict[str, list[dict]]:
    app_token = get_env("FEISHU_GRAPH_BITABLE_APP_TOKEN")["FEISHU_GRAPH_BITABLE_APP_TOKEN"]
    data: dict[str, list[dict]] = {}
    for label, cfg in (gc.get("entities") or {}).items():
        tid = cfg["table_id"]
        fields = fetch_table_fields(app_token, tid)
        data[label] = fetch_table_records(app_token, tid, fields)
    seen = set()
    for rel in (gc.get("relationships") or []):
        via = rel.get("via")
        if via and via.get("table_id") not in seen:
            seen.add(via["table_id"])
            tid = via["table_id"]
            fields = fetch_table_fields(app_token, tid)
            data[f"via_{tid}"] = fetch_table_records(app_token, tid, fields)
    return data


# ---------- Phase 2: graph build（移植 graph_builder.py，逐行对齐 Cypher）----------
# 实现前必读 graph_builder.py：build_nodes / build_relationships / clear_graph。
# 关键：节点 key_field 去重 upsert；关系按 match/via 两种模式建边；via 中间表连 from↔to。

def _clear_graph(client: Neo4jClient) -> None:
    """移植 graph_builder.clear_graph（MATCH (n) DETACH DELETE n 或按需）。读源文件对齐。"""
    # TODO: 按 graph_builder.clear_graph 实现（用 client.run_cypher / driver session）
    raise NotImplementedError("见 graph_builder.clear_graph，用 Neo4jClient 执行")


def _build_nodes(client: Neo4jClient, entities: dict, feishu_data: dict) -> dict[str, int]:
    """移植 graph_builder.build_nodes。读源文件对齐 Cypher（MERGE on key_field + SET props）。"""
    raise NotImplementedError("见 graph_builder.build_nodes")


def _build_relationships(client: Neo4jClient, relationships: list, entities: dict, feishu_data: dict) -> dict[str, int]:
    """移植 graph_builder.build_relationships（含 via 中间表）。读源文件对齐。"""
    raise NotImplementedError("见 graph_builder.build_relationships")


# ---------- Phase 3: embed（移植 embedding.py 的非 embed 部分 + fastembed 替换）----------

def _generate_search_text(client: Neo4jClient, entities: dict) -> dict[str, int]:
    """移植 embedding.generate_search_text：拼 '字段名：值。' 写回 n.search_text。"""
    # 用 Neo4jClient 的 session；逐行对齐 embedding.py generate_search_text（84-136）
    raise NotImplementedError("见 embedding.generate_search_text")


def _create_vector_indexes(client: Neo4jClient, entities: dict, dimensions: int) -> list[str]:
    """移植 embedding.create_vector_indexes（CREATE VECTOR INDEX IF NOT EXISTS，cosine）。"""
    raise NotImplementedError("见 embedding.create_vector_indexes（139-179）")


def _embed_nodes(client: Neo4jClient, entities: dict, dimensions: int, force: bool) -> dict[str, int]:
    """生成 embedding。**关键差异**：用 fastembed 批量编码（retrieving_context.embed 同源），
    替代原 SentenceTransformer。normalize：fastembed 对 bge 默认 L2 归一化（与原 normalize_embeddings=True 一致）。
    写回 n.embedding / embedding_model='BAAI/bge-small-zh-v1.5' / dimensions / updated_at。
    读源 embedding.embed_nodes（204-282）对齐写回字段；embed 用下方批量函数。"""
    model = (load_config().get("graph-config", {}).get("embedding", {}) or {}).get("model", "BAAI/bge-small-zh-v1.5")
    from fastembed import TextEmbedding
    fe = TextEmbedding(model_name=model)
    counts: dict[str, int] = {}
    for label, cfg in entities.items():
        if (cfg or {}).get("vector_index", True) is False:
            continue
        esc = label.replace("`", "``")
        where = "n.search_text IS NOT NULL" if force else "n.search_text IS NOT NULL AND n.embedding IS NULL"
        # 取需 embed 的 (id, text)（用 client session）
        pairs = client.run_cypher(  # 注意 run_cypher 返回 dict 列表；按需直接用 driver session
            f"MATCH (n:`{esc}`) WHERE {where} RETURN elementId(n) AS id, n.search_text AS t")
        # ⚠️ run_cypher 不支持写回 SET；embedding 阶段需 driver session。给 Neo4jClient 暴露一个轻量写入口或直接在此用 driver。
        # 见 Task 1 Step 3 的 Neo4jClient 扩展说明。
        texts = [p["t"] for p in pairs]
        ids = [p["id"] for p in pairs]
        if not texts:
            counts[label] = 0
            continue
        vecs = list(fe.embed(texts))   # fastembed 批量，已归一化
        # 写回（driver session，SET n.embedding=...）
        # ... 对齐 embedding.py 264-277 的 SET 语句 ...
        counts[label] = len(ids)
    return counts


# ---------- 编排 ----------

def sync_graph(only: str | None = None, dry_run: bool = False, force_embed: bool = False) -> dict[str, Any]:
    """同步飞书多维表 → Neo4j → ONNX 向量。

    Args:
        only: 'fetch' | 'graph' | 'embed'，只跑某阶段；None 全跑。
        dry_run: 只 fetch 预览，不写库。
        force_embed: 重新生成全部 embedding（即使已存在）。
    Returns: 各阶段计数 {fetch:{...}, nodes:{...}, relationships:{...}, search_text:{...}, indexes:n, embed:{...}}。
    """
    if only is not None and only not in ("fetch", "graph", "embed"):
        raise ValidationError("only 必须是 fetch|graph|embed 或 None")
    gc = load_config().get("graph-config", {}) or {}
    if "entities" not in gc:
        raise ConfigError("config.json 缺 graph-config.entities")
    dimensions = (gc.get("embedding", {}) or {}).get("dimensions", 512)
    result: dict[str, Any] = {}

    if only in (None, "fetch", "graph"):
        feishu_data = _fetch_all_feishu(gc)
        result["fetch"] = {k: len(v) for k, v in feishu_data.items()}
    else:
        feishu_data = {}

    if dry_run:
        return result

    client = Neo4jClient()
    try:
        if only in (None, "graph"):
            if only is None:
                _clear_graph(client)
            result["nodes"] = _build_nodes(client, gc["entities"], feishu_data)
            result["relationships"] = _build_relationships(client, gc.get("relationships", []), gc["entities"], feishu_data)
        if only in (None, "embed"):
            result["search_text"] = _generate_search_text(client, gc["entities"])
            result["indexes"] = len(_create_vector_indexes(client, gc["entities"], dimensions))
            result["embed"] = _embed_nodes(client, gc["entities"], dimensions, force_embed)
    finally:
        client.close()
    return result
```

> **重要实现约束：**
> 1. **读源文件再实现** Phase 2 的三个函数（`_clear_graph/_build_nodes/_build_relationships`）—— 它们的 Cypher 必须与 graph_builder.py 一致（key_field 去重、match/via 两种关系模式、via 中间表双向连边）。别猜，照搬。
> 2. **Neo4jClient 写入能力**：现有 `Neo4jClient` 只有读（`run_cypher`）和图扩展，**没有通用写入口**。embed/graph 阶段要 `SET`/`MERGE`/`CREATE`。**给 Neo4jClient 加一个 `execute(write_cypher, **params)` 方法**（在 `retrieving_context.py` 内加，对外只增不改现有方法——这不算违反铁律，是给内核补能力）或在本 sync 模块内直接用 `from neo4j import GraphDatabase` 自建短生命 driver。**优先在 retrieving_context.py 给 Neo4jClient 加 `execute()`（一行包装 session.run），保持单一 driver 来源**。改动后跑现有 retrieving_context 测试确保无回归。
> 3. embed 用 `TextEmbedding(model).embed(list)` 批量，已 L2 归一化；写回字段对齐 embedding.py 264-277。
> 4. 去 CLI：原 sync.py 的 print/argparse 全删；进度信息不返回（MCP 工具用 Context.report_progress，但本内核先不接 Context，只返回计数）。

- [ ] **Step 3: （若需要）给 Neo4jClient 加通用 `execute()` 写入口** —— 在 `retrieving_context.py` 的 `Neo4jClient` 加：
```python
    def execute(self, cypher: str, **params) -> None:
        """通用写/DDL 执行（MERGE/SET/CREATE/CLEAR）。无返回。"""
        with self._session() as s:
            s.run(cypher, **params)
```
跑 `python -m pytest tests/test_retrieving_context.py -q` 确认无回归。

- [ ] **Step 4: 冒烟** `python -c "from sda_mcp.skills.retrieving_context_sync import sync_graph; print('ok')"`

- [ ] **Step 5: 提交**
```bash
git add mcp/sda_mcp/skills/retrieving_context_sync.py mcp/sda_mcp/skills/retrieving_context.py
git commit -m "feat(mcp): retrieving_context sync pipeline core (ONNX-consistent embed)"
```

---

## Task 2: 导出 + sync MCP 工具 + 测试

- [ ] **Step 1: `skills/__init__.py` 导出** `sync_graph`（from retrieving_context_sync）。

- [ ] **Step 2: `retrieve_tools.py` 加 `sync` 工具**：
```python
class SyncIn(BaseModel):
    only: str | None = Field(default=None, description="fetch|graph|embed；None 全跑")
    dry_run: bool = False
    force_embed: bool = False

@mcp.tool(name="sync")
def sync(params: SyncIn) -> dict[str, Any]:
    """同步飞书多维表 → Neo4j → ONNX 向量（首次或刷新语义层数据）。"""
    from sda_mcp.skills.retrieving_context_sync import sync_graph
    return sync_graph(params.only, params.dry_run, params.force_embed)
```
注册后工具数变 24。

- [ ] **Step 3: 写 `test_retrieving_context_sync.py`**（mock lark-cli 子进程 + Neo4j，断言三阶段计数与 fastembed 调用）：
  - `test_fetch_extracts_records`：mock `_lark_cli` 返回固定 field-list/record-list → `fetch_table_records` 解析正确（含 select 取值、分页停止）。
  - `test_sync_graph_orchestration`：mock `_fetch_all_feishu`/`_build_nodes`/.../`_embed_nodes`（monkeypatch 为计数 stub）→ `sync_graph()` 返回各阶段计数、按 only 选择性执行（only='embed' 不调 build）。
  - `test_sync_dry_run_no_write`：dry_run=True → 不构造 Neo4jClient、只返回 fetch 计数。
  - `test_sync_bad_only_raises`：only='bogus' → ValidationError。
  - `test_embed_uses_fastembed_batch`：mock TextEmbedding，断言批量 embed 被调用、写回字段齐（用 fake driver 记录 SET 语句）。

- [ ] **Step 4: 全量 + 铁律 + 工具数**
```bash
cd mcp && python -m pytest -q
git diff --stat -- retrieving-context/   # 空
python -c "import asyncio; from mcp import Client; from sda_mcp.tools._common import mcp
async def t():
 async with Client(mcp) as c: print('tools:', len((await c.list_tools()).tools))
asyncio.run(t())"   # 期望 24
```
Expected: 全绿（102 + sync 新增 ≈ 5）；原 retrieving-context 零改动；工具 24。

- [ ] **Step 5: 提交**
```bash
git add mcp/sda_mcp/skills/__init__.py mcp/sda_mcp/tools/retrieve_tools.py mcp/tests/test_retrieving_context_sync.py
git commit -m "feat(mcp): sync tool + tests (24 tools, ONNX-consistent graph sync)"
```

---

## 完成标准

- [ ] `retrieving_context_sync.py`：fetch(飞书) + build(图) + embed(fastembed) 三阶段，忠实复刻原 pipeline，embedding 用 ONNX。
- [ ] `sync_graph(only, dry_run, force_embed) -> dict`；`sync` MCP 工具；工具数 24。
- [ ] 去 CLI/argparse/print；失败抛 SkillError。
- [ ] mock 单测覆盖 fetch 解析 / 编排 / dry_run / fastembed 批量；全量绿；原 retrieving-context 零改动。
- [ ] Neo4jClient 新增 `execute()` 写入口且无回归。
