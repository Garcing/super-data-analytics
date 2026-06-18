# retrieving-business-context GraphRAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete GraphRAG agent skill that syncs business knowledge from Feishu into Neo4j and serves semantic retrieval with graph expansion.

**Architecture:** YAML config drives everything — Python sync pipeline reads Feishu via lark-cli, builds Neo4j graph, generates embeddings; Node.js CLI handles query-time vector search + graph expansion. Agent uses the JSON output to answer business questions.

**Tech Stack:** Python (neo4j driver, sentence-transformers, pyyaml), Node.js (neo4j-driver, ESM), lark-cli, Neo4j 5.x with vector indexes, BAAI/bge-small-zh-v1.5

**Spec:** `docs/superpowers/specs/2026-06-01-retrieving-business-context-graphrag.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `retrieving-business-context/graph-config.yaml` | Entity/relationship/embedding config — single source of truth |
| `retrieving-business-context/.env` | NEO4J_USER, NEO4J_PASSWORD |
| `retrieving-business-context/.gitignore` | .env, __pycache__, node_modules |
| `retrieving-business-context/sync/requirements.txt` | Python deps: neo4j, sentence-transformers, pyyaml |
| `retrieving-business-context/sync/feishu_reader.py` | Call lark-cli to fetch table fields + records |
| `retrieving-business-context/sync/graph_builder.py` | MERGE nodes + create relationships from config |
| `retrieving-business-context/sync/embedding.py` | Auto-generate search_text, encode, write vector indexes |
| `retrieving-business-context/sync/sync.py` | Main orchestrator CLI (fetch → graph → embed) |
| `retrieving-business-context/server/package.json` | neo4j-driver dependency |
| `retrieving-business-context/server/query.js` | Node.js query CLI (vector search + graph expansion) |
| `retrieving-business-context/SKILL.md` | Agent skill definition |
| `retrieving-business-context/CLAUDE.md` | Technical reference |

---

### Task 1: Configuration & Project Scaffold

**Files:**
- Create: `retrieving-business-context/graph-config.yaml`
- Create: `retrieving-business-context/.env`
- Create: `retrieving-business-context/.gitignore`
- Create: `retrieving-business-context/sync/requirements.txt`
- Create: `retrieving-business-context/server/package.json`

- [ ] **Step 1: Create graph-config.yaml**

Write the full config based on real Feishu table structure (9 tables, 7 relationship types):

```yaml
# ============================================
# GraphRAG 配置 — 唯一真相来源
# 改字段/改关系只改这里，不改代码
# ============================================

feishu:
  app_token: BHINbLiOKa4rXDsLTlQcRwuSn9c

neo4j:
  uri: bolt://localhost:7687
  database: neo4j
  # user/password 从 .env 读取

embedding:
  model: BAAI/bge-small-zh-v1.5
  model_path: sync/models/bge-small-zh-v1.5
  dimensions: 512

# ============================================
# 实体定义：每张飞书表 → 一个 Neo4j 标签
# search_text 自动拼接所有字段：字段名：值。
# vector_index 默认 true，改为 false 则跳过向量索引
# ============================================
entities:
  业务线:
    table_id: tbljp4PEWKQcjQzD
    key_field: 业务线名称

  业务板块:
    table_id: tbl3LKdowDu3KLQm
    key_field: 业务板块名称

  业务小点:
    table_id: tblmwx8jwrZVX49t
    key_field: 业务小点名称

  指标:
    table_id: tblDiMrN7GaGVtpc
    key_field: 指标名称

  维度:
    table_id: tblzgo2FcMG7eSwR
    key_field: 维度名称

  数据看板:
    table_id: tblaOZqdUnySDDMG
    key_field: 数据看板名称
    vector_index: false

  数据域:
    table_id: tblJY0BfS8LAPTcf
    key_field: 数据域名称
    vector_index: false

  表:
    table_id: tbl6Ri6dTIwTWGch
    key_field: 表名称

# ============================================
# 关系定义
# ============================================
relationships:
  - type: 包含
    from: 业务线
    to: 业务板块
    match:
      source_field: 业务线名称
      target_field: 业务线名称

  - type: 包含
    from: 业务板块
    to: 业务小点
    match:
      source_field: 业务板块名称
      target_field: 业务板块名称

  - type: 涉及
    from: 业务小点
    to: 指标
    match:
      source_field: 指标名称
      target_field: 指标名称
      multi: true

  - type: 展示
    from: 数据看板
    to: 指标
    match:
      source_field: 数据看板名称
      target_field: 数据看板名称

  - type: 筛选
    from: 维度
    to: 指标
    match:
      source_field: 维度板块
      target_field: 维度板块
      multi: true

  - type: 包含
    from: 数据域
    to: 表
    match:
      source_field: 数据域主题
      target_field: 数据域主题

  - type: 关联
    from: 表
    to: 表
    via:
      table_id: tblhMmvHGmEh9MWx
      from_field: 从表
      to_field: 到表
      properties:
        - 关联类型
        - 关联表达式
```

- [ ] **Step 2: Create .env**

```
NEO4J_USER=neo4j
NEO4J_PASSWORD=hejiachengg
```

- [ ] **Step 3: Create .gitignore**

```
.env
__pycache__/
node_modules/
*.pyc
```

- [ ] **Step 4: Create sync/requirements.txt**

```
neo4j>=5.0
sentence-transformers>=2.0
pyyaml>=6.0
```

- [ ] **Step 5: Create server/package.json**

```json
{
  "name": "graphrag-query",
  "private": true,
  "type": "module",
  "dependencies": {
    "neo4j-driver": "^5.0.0"
  }
}
```

- [ ] **Step 6: Install Python dependencies**

Run: `cd retrieving-business-context/sync && pip install -r requirements.txt`

- [ ] **Step 7: Install Node.js dependencies**

Run: `cd retrieving-business-context/server && npm install`

- [ ] **Step 8: Verify config parses**

Quick smoke test — run `python -c "import yaml; c=yaml.safe_load(open('retrieving-business-context/graph-config.yaml')); print(len(c['entities']), 'entities,', len(c['relationships']), 'relationships')"`.

Expected: `8 entities, 7 relationships`

- [ ] **Step 9: Commit**

```bash
git add retrieving-business-context/graph-config.yaml retrieving-business-context/.env retrieving-business-context/.gitignore retrieving-business-context/sync/requirements.txt retrieving-business-context/server/package.json retrieving-business-context/server/package-lock.json
git commit -m "feat(graphrag): config files and project scaffold"
```

---

### Task 2: feishu_reader.py — Read Feishu Data via lark-cli

**Files:**
- Create: `retrieving-business-context/sync/feishu_reader.py`

This module wraps `lark-cli base` commands to fetch table field schemas and records. It uses `subprocess.run` to call lark-cli (following the pattern from `dispatching-data-briefs/feishu-briefs.js` which wraps lark-cli via `execFileSync`).

- [ ] **Step 1: Create feishu_reader.py**

```python
"""
feishu_reader.py — Read Feishu Base data via lark-cli.

Functions:
    fetch_table_fields(app_token, table_id) -> list[dict]
        Returns field metadata for a table (name, type, etc.)

    fetch_table_records(app_token, table_id) -> list[dict]
        Returns all records as a list of {field_name: field_value} dicts.
        Multi-select fields are returned as lists.
        Auto_number fields are skipped.
"""
from __future__ import annotations

import json
import subprocess


def _run_lark_cli(*args: str) -> dict:
    """Call lark-cli and return parsed JSON output."""
    cmd = ["lark-cli", *args, "--as", "bot"]
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        raise RuntimeError(f"lark-cli failed: {result.stderr}")

    # lark-cli may output warning lines before JSON; find the JSON object
    lines = result.stdout.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(f"No JSON output from lark-cli: {result.stdout[:500]}")


def fetch_table_fields(app_token: str, table_id: str) -> list[dict]:
    """Fetch field definitions for a table.

    Returns list of dicts with keys: name, type, id.
    Filters out auto_number fields.
    """
    data = _run_lark_cli(
        "base", "+field-list",
        "--base-token", app_token,
        "--table-id", table_id,
    )
    fields = data.get("data", {}).get("fields", [])
    return [
        {"name": f["name"], "type": f["type"], "id": f["id"]}
        for f in fields
        if f["type"] != "auto_number"
    ]


def _extract_cell_value(field_type: str, cell: object) -> object:
    """Extract a readable value from a Feishu cell value object.

    Feishu cell values come in different shapes depending on field type:
    - text: [{"type": "text", "text": "hello"}]
    - select: "option_name"
    - multi_select: ["opt1", "opt2"]
    - number: 42 or 3.14
    - formula: computed value (same as underlying type)
    """
    if cell is None:
        return None

    # Text fields: list of content segments
    if field_type == "text" and isinstance(cell, list):
        parts = []
        for seg in cell:
            if isinstance(seg, dict):
                parts.append(seg.get("text", ""))
            else:
                parts.append(str(seg))
        return "".join(parts).strip() or None

    # Multi-select: already a list of strings
    if field_type in ("multi_select",) and isinstance(cell, list):
        return cell

    # Single select: string
    if isinstance(cell, str):
        return cell.strip() or None

    # Number, etc.
    return cell


def fetch_table_records(
    app_token: str,
    table_id: str,
    fields: list[dict] | None = None,
) -> list[dict]:
    """Fetch all records from a Feishu table.

    Args:
        app_token: Feishu base app token.
        table_id: Table ID within the base.
        fields: Optional field metadata list from fetch_table_fields().
                If provided, used to extract cell values correctly.
                If None, fetches fields automatically.

    Returns:
        List of dicts, each mapping field_name -> extracted_value.
        auto_number fields are excluded.
    """
    if fields is None:
        fields = fetch_table_fields(app_token, table_id)

    # Build field_name -> field_type lookup
    field_types = {f["name"]: f["type"] for f in fields}

    data = _run_lark_cli(
        "base", "+record-list",
        "--base-token", app_token,
        "--table-id", table_id,
        "--page-all",
    )

    items = data.get("data", {}).get("items", [])
    records = []
    for item in items:
        fields_data = item.get("fields", {})
        row = {}
        for field in fields:
            name = field["name"]
            ftype = field["type"]
            raw = fields_data.get(name)
            value = _extract_cell_value(ftype, raw)
            if value is not None:
                row[name] = value
        records.append(row)

    return records
```

- [ ] **Step 2: Verify feishu_reader works**

Run: `cd retrieving-business-context && python -c "from sync.feishu_reader import fetch_table_fields, fetch_table_records; fields = fetch_table_fields('BHINbLiOKa4rXDsLTlQcRwuSn9c', 'tbl3LKdowDu3KLQm'); print(f'{len(fields)} fields:', [f['name'] for f in fields]); records = fetch_table_records('BHINbLiOKa4rXDsLTlQcRwuSn9c', 'tbl3LKdowDu3KLQm', fields); print(f'{len(records)} records'); print(records[0])"`

Expected: Shows 3 fields (业务板块名称, 业务板块介绍, 业务线名称), 8 records, first record has those field values.

- [ ] **Step 3: Commit**

```bash
git add retrieving-business-context/sync/feishu_reader.py
git commit -m "feat(graphrag): feishu_reader — fetch table fields and records via lark-cli"
```

---

### Task 3: graph_builder.py — Build Neo4j Graph from Config

**Files:**
- Create: `retrieving-business-context/sync/graph_builder.py`

This module reads the YAML config and uses feishu_reader data to MERGE nodes and create relationships in Neo4j.

- [ ] **Step 1: Create graph_builder.py**

```python
"""
graph_builder.py — Build Neo4j nodes and relationships from config.

Functions:
    build_nodes(driver, config, feishu_data) -> dict[str, int]
        MERGE nodes for each entity. Returns {label: count}.

    build_relationships(driver, config, feishu_data) -> dict[str, int]
        Create relationships between nodes. Returns {rel_type: count}.

    clear_graph(driver) -> None
        DELETE all nodes and relationships (for full rebuild).
"""
from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase


def _escape(label: str) -> str:
    """Escape a label for use in Cypher backtick quotes."""
    return label.replace("`", "``")


def build_nodes(driver, entities_config: dict, feishu_data: dict) -> dict[str, int]:
    """MERGE nodes for each entity defined in config.

    Args:
        driver: Neo4j driver instance.
        entities_config: entities section from graph-config.yaml.
        feishu_data: {label: [records]} — fetched Feishu records per entity.

    Returns:
        {label: node_count} for each entity.
    """
    counts = {}
    with driver.session() as session:
        for label, entity_cfg in entities_config.items():
            key_field = entity_cfg["key_field"]
            records = feishu_data.get(label, [])
            if not records:
                counts[label] = 0
                continue

            escaped_label = _escape(label)
            escaped_key = _escape(key_field)

            # Build SET clause for all non-key properties
            for record in records:
                key_value = record.get(key_field)
                if key_value is None:
                    continue

                # Collect properties to set
                props = {k: v for k, v in record.items() if k != key_field}

                # MERGE on key_field, SET other properties
                cypher = (
                    f"MERGE (n:`{escaped_label}` {{`{escaped_key}`: $key_value}}) "
                    f"SET n += $props"
                )
                session.run(cypher, key_value=key_value, props=props)

            # Count created nodes
            count_result = session.run(f"MATCH (n:`{escaped_label}`) RETURN count(n) AS cnt")
            counts[label] = int(count_result.single()["cnt"])

    return counts


def _resolve_multi_value(value: Any) -> list[str]:
    """Ensure a value is a list of strings for multi-select matching."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    if isinstance(value, str):
        # Feishu may return comma-separated strings for some multi fields
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(value)] if value is not None else []


def build_relationships(
    driver,
    relationships_config: list,
    entities_config: dict,
    feishu_data: dict,
) -> dict[str, int]:
    """Create relationships between nodes based on config.

    Handles three matching modes:
    1. Direct match: source_field value == target_field value
    2. Multi match: split multi-select, match each individually
    3. Via match: use intermediate table to link entities

    Returns:
        {rel_description: count} for each relationship type.
    """
    counts = {}
    with driver.session() as session:
        for rel in relationships_config:
            rel_type = rel["type"]
            from_label = rel["from"]
            to_label = rel["to"]

            if "via" in rel:
                # Via intermediate table
                count = _build_via_relationships(
                    session, rel, from_label, to_label, entities_config, feishu_data
                )
            else:
                # Direct or multi match
                match_cfg = rel["match"]
                is_multi = match_cfg.get("multi", False)
                source_field = match_cfg["source_field"]
                target_field = match_cfg["target_field"]

                count = _build_direct_relationships(
                    session,
                    from_label, to_label, rel_type,
                    source_field, target_field,
                    is_multi,
                    entities_config,
                    feishu_data,
                )

            desc = f"({from_label})-[:{rel_type}]->({to_label})"
            counts[desc] = count

    return counts


def _build_direct_relationships(
    session,
    from_label: str,
    to_label: str,
    rel_type: str,
    source_field: str,
    target_field: str,
    is_multi: bool,
    entities_config: dict,
    feishu_data: dict,
) -> int:
    """Build relationships by matching field values between entity records."""
    from_key = entities_config[from_label]["key_field"]
    to_key = entities_config[to_label]["key_field"]

    # Build lookup: target_key_value -> True
    # For multi targets, the target_field may differ from key_field
    # We look up target nodes by their target_field value
    to_records = feishu_data.get(to_label, [])
    target_lookup: dict[str, str] = {}  # target_field_value -> target_key_value
    for rec in to_records:
        key_val = rec.get(to_key)
        field_val = rec.get(target_field)
        if key_val is None or field_val is None:
            continue
        if target_field == to_key:
            target_lookup[str(key_val).strip()] = str(key_val).strip()
        else:
            target_lookup[str(field_val).strip()] = str(key_val).strip()

    from_records = feishu_data.get(from_label, [])
    count = 0

    escaped_from = _escape(from_label)
    escaped_to = _escape(to_label)
    escaped_from_key = _escape(from_key)
    escaped_to_key = _escape(to_key)
    escaped_rel = _escape(rel_type)

    for rec in from_records:
        from_key_val = rec.get(from_key)
        source_val = rec.get(source_field)
        if from_key_val is None or source_val is None:
            continue

        if is_multi:
            values = _resolve_multi_value(source_val)
        else:
            values = [str(source_val).strip()]

        for v in values:
            to_key_val = target_lookup.get(v)
            if to_key_val is None:
                continue

            cypher = (
                f"MATCH (a:`{escaped_from}` {{`{escaped_from_key}`: $from_key}}) "
                f"MATCH (b:`{escaped_to}` {{`{escaped_to_key}`: $to_key}}) "
                f"MERGE (a)-[:`{escaped_rel}`]->(b)"
            )
            session.run(cypher, from_key=str(from_key_val).strip(), to_key=to_key_val)
            count += 1

    return count


def _build_via_relationships(
    session,
    rel: dict,
    from_label: str,
    to_label: str,
    entities_config: dict,
    feishu_data: dict,
) -> int:
    """Build relationships using an intermediate table (via config)."""
    via_cfg = rel["via"]
    via_table_id = via_cfg["table_id"]
    from_field = via_cfg["from_field"]
    to_field = via_cfg["to_field"]
    via_properties = via_cfg.get("properties", [])

    from_key = entities_config[from_label]["key_field"]
    to_key = entities_config[to_label]["key_field"]

    # The via table records should be in feishu_data
    # We use a special key format: "via_{table_id}"
    via_records = feishu_data.get(f"via_{via_table_id}", [])
    if not via_records:
        return 0

    escaped_from = _escape(from_label)
    escaped_to = _escape(to_label)
    escaped_from_key = _escape(from_key)
    escaped_to_key = _escape(to_key)
    escaped_rel = _escape(rel["type"])

    count = 0
    for via_rec in via_records:
        from_val = via_rec.get(from_field)
        to_val = via_rec.get(to_field)
        if from_val is None or to_val is None:
            continue

        # Build relationship properties
        rel_props = {}
        for prop_name in via_properties:
            prop_val = via_rec.get(prop_name)
            if prop_val is not None:
                rel_props[prop_name] = prop_val

        # Build MERGE with optional properties
        if rel_props:
            prop_parts = ", ".join(
                f"`{_escape(k)}`: ${k}" for k in rel_props
            )
            cypher = (
                f"MATCH (a:`{escaped_from}` {{`{escaped_from_key}`: $from_key}}) "
                f"MATCH (b:`{escaped_to}` {{`{escaped_to_key}`: $to_key}}) "
                f"MERGE (a)-[:`{escaped_rel}` {{{prop_parts}}}]->(b)"
            )
            params = {
                "from_key": str(from_val).strip(),
                "to_key": str(to_val).strip(),
                **rel_props,
            }
        else:
            cypher = (
                f"MATCH (a:`{escaped_from}` {{`{escaped_from_key}`: $from_key}}) "
                f"MATCH (b:`{escaped_to}` {{`{escaped_to_key}`: $to_key}}) "
                f"MERGE (a)-[:`{escaped_rel}`]->(b)"
            )
            params = {
                "from_key": str(from_val).strip(),
                "to_key": str(to_val).strip(),
            }

        session.run(cypher, **params)
        count += 1

    return count


def clear_graph(driver) -> None:
    """Delete all nodes and relationships in the database."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        print("已清空图数据库")
```

- [ ] **Step 2: Verify graph_builder imports and has no syntax errors**

Run: `cd retrieving-business-context && python -c "from sync.graph_builder import build_nodes, build_relationships, clear_graph; print('graph_builder OK')"`

Expected: `graph_builder OK`

- [ ] **Step 3: Commit**

```bash
git add retrieving-business-context/sync/graph_builder.py
git commit -m "feat(graphrag): graph_builder — MERGE nodes and create relationships from config"
```

---

### Task 4: embedding.py — search_text + Vectorization

**Files:**
- Create: `retrieving-business-context/sync/embedding.py`

This module: (1) auto-generates search_text from node properties, (2) loads the local embedding model, (3) encodes nodes, (4) creates vector indexes. It also exposes a CLI `encode` subcommand for the Node.js query service to call.

- [ ] **Step 1: Create embedding.py**

```python
"""
embedding.py — Auto-generate search_text, encode embeddings, create vector indexes.

Functions:
    generate_search_text(driver, entities_config) -> dict[str, int]
        Auto-concatenate all node properties into search_text.

    create_vector_indexes(driver, entities_config, dimensions) -> list[str]
        Create vector indexes for entities with vector_index=true.

    encode_texts(model_path, texts) -> list[list[float]]
        Encode texts using local model.

CLI usage (called by Node.js query service):
    python embedding.py encode "用户问题文本"
    # Prints JSON array of floats to stdout
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def _escape(label: str) -> str:
    return label.replace("`", "``")


def generate_search_text(driver, entities_config: dict) -> dict[str, int]:
    """Auto-generate search_text for all nodes of each entity type.

    Concatenates all properties as "字段名：值。" format.
    Skips entities with vector_index=false.
    Skips internal properties: search_text, embedding, embedding_model,
    embedding_dimensions, embedding_updated_at.
    """
    counts = {}
    skip_props = {"search_text", "embedding", "embedding_model",
                  "embedding_dimensions", "embedding_updated_at"}

    with driver.session() as session:
        for label, cfg in entities_config.items():
            if not cfg.get("vector_index", True):
                counts[label] = 0
                continue

            escaped_label = _escape(label)

            # Fetch all nodes with their properties
            rows = list(session.run(
                f"MATCH (n:`{escaped_label}`) RETURN properties(n) AS props, elementId(n) AS id"
            ))

            updated = 0
            for row in rows:
                props = dict(row["props"])
                node_id = row["id"]

                # Build search_text from all non-internal properties
                parts = []
                for key, value in sorted(props.items()):
                    if key in skip_props:
                        continue
                    if value is None:
                        continue
                    str_val = str(value).strip()
                    if not str_val:
                        continue
                    # For list values (multi-select), join with comma
                    if isinstance(value, list):
                        str_val = "、".join(str(v) for v in value if v)
                    parts.append(f"{key}：{str_val}")

                if not parts:
                    continue

                search_text = "。".join(parts) + "。"

                # Write back to node
                session.run(
                    f"MATCH (n) WHERE elementId(n) = $id SET n.search_text = $text",
                    id=node_id,
                    text=search_text,
                )
                updated += 1

            counts[label] = updated

    return counts


def create_vector_indexes(
    driver,
    entities_config: dict,
    dimensions: int = 512,
) -> list[str]:
    """Create vector indexes for entities with vector_index=true.

    Index naming: {label}_embedding_index (using pinyin-safe lower case).
    Since labels are Chinese, we sanitize them.
    """
    # Mapping: label -> index_name
    index_names = []
    with driver.session() as session:
        for label, cfg in entities_config.items():
            if not cfg.get("vector_index", True):
                continue

            escaped_label = _escape(label)
            index_name = f"{label}_embedding_index"
            escaped_index = _escape(index_name)

            cypher = f"""
            CREATE VECTOR INDEX `{escaped_index}` IF NOT EXISTS
            FOR (n:`{escaped_label}`) ON (n.embedding)
            OPTIONS {{
              indexConfig: {{
                `vector.dimensions`: {dimensions},
                `vector.similarity_function`: 'cosine'
              }}
            }}
            """
            session.run(cypher).consume()
            index_names.append(index_name)
            print(f"  向量索引: {index_name} -> :{label}(embedding)")

    return index_names


def _load_model(model_path: str):
    """Load SentenceTransformer from local path."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_path)


def encode_texts(model_path: str, texts: list[str]) -> list[list[float]]:
    """Encode a list of texts using the local embedding model.

    Returns list of float arrays (each of length `dimensions`).
    """
    model = _load_model(model_path)
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [e.astype(float).tolist() for e in embeddings]


def embed_nodes(
    driver,
    entities_config: dict,
    model_path: str,
    dimensions: int = 512,
    force: bool = False,
    batch_size: int = 16,
) -> dict[str, int]:
    """Generate embeddings for nodes with search_text.

    For each entity with vector_index=true:
    1. Find nodes where search_text IS NOT NULL
    2. Encode in batches
    3. Write back embedding, embedding_model, embedding_dimensions, embedding_updated_at
    """
    counts = {}
    skip_props = {"search_text", "embedding", "embedding_model",
                  "embedding_dimensions", "embedding_updated_at"}

    model = _load_model(model_path)

    with driver.session() as session:
        for label, cfg in entities_config.items():
            if not cfg.get("vector_index", True):
                counts[label] = 0
                continue

            escaped_label = _escape(label)

            # Count nodes to process
            where_clause = "AND ($force OR n.embedding IS NULL)" if not force else ""
            total = 0

            while True:
                cypher = (
                    f"MATCH (n:`{escaped_label}`) "
                    f"WHERE n.search_text IS NOT NULL {where_clause} "
                    f"RETURN elementId(n) AS id, n.search_text AS text "
                    f"LIMIT $batch_size"
                )
                rows = list(session.run(cypher, force=force, batch_size=batch_size))
                if not rows:
                    break

                texts = [r["text"] for r in rows]
                ids = [r["id"] for r in rows]

                # Encode batch
                embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

                # Write back
                write_rows = [
                    {"id": node_id, "embedding": emb.astype(float).tolist()}
                    for node_id, emb in zip(ids, embeddings)
                ]
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (n) WHERE elementId(n) = row.id
                    SET n.embedding = row.embedding,
                        n.embedding_model = $model_name,
                        n.embedding_dimensions = $dimensions,
                        n.embedding_updated_at = datetime()
                    """,
                    rows=write_rows,
                    model_name=os.path.basename(model_path),
                    dimensions=dimensions,
                )
                batch_count = len(write_rows)
                total += batch_count
                print(f"  [{label}] 本批 {batch_count} 个，累计 {total} 个")

                if batch_count < batch_size:
                    break

            counts[label] = total

    return counts


def main():
    parser = argparse.ArgumentParser(description="Embedding utilities")
    sub = parser.add_subparsers(dest="command")

    encode_parser = sub.add_parser("encode", help="Encode a text to embedding vector")
    encode_parser.add_argument("text", help="Text to encode")
    encode_parser.add_argument("--model-path", default=None, help="Path to local model")

    args = parser.parse_args()

    if args.command == "encode":
        # Load model path from config if not specified
        model_path = args.model_path
        if model_path is None:
            import yaml
            config_path = os.path.join(os.path.dirname(__file__), "..", "graph-config.yaml")
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            model_path = cfg["embedding"]["model_path"]

        vectors = encode_texts(model_path, [args.text])
        # Output as JSON to stdout for Node.js to consume
        print(json.dumps(vectors[0]))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify embedding.py syntax and encode CLI**

First verify import: `cd retrieving-business-context && python -c "from sync.embedding import generate_search_text, create_vector_indexes, encode_texts; print('embedding OK')"`

- [ ] **Step 3: Commit**

```bash
git add retrieving-business-context/sync/embedding.py
git commit -m "feat(graphrag): embedding — auto search_text, vectorization, encode CLI"
```

---

### Task 5: sync.py — Main Orchestrator

**Files:**
- Create: `retrieving-business-context/sync/sync.py`

The main entry point. Reads config, orchestrates the full sync pipeline.

- [ ] **Step 1: Create sync.py**

```python
"""
sync.py — Main orchestrator for GraphRAG sync pipeline.

Usage:
    python sync.py                    # Full sync: fetch -> graph -> embed
    python sync.py --only fetch       # Only fetch Feishu data
    python sync.py --only graph       # Only build graph (no embedding rebuild)
    python sync.py --only embed       # Only rebuild embeddings (assume graph exists)
    python sync.py --dry-run          # Preview what would happen
    python sync.py --force-embed      # Force regenerate all embeddings
    python sync.py --download-model   # Download embedding model to local folder
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml
from neo4j import GraphDatabase

from feishu_reader import fetch_table_fields, fetch_table_records
from graph_builder import build_nodes, build_relationships, clear_graph
from embedding import (
    generate_search_text,
    create_vector_indexes,
    embed_nodes,
)


def load_config(config_path: str | None = None) -> dict:
    """Load graph-config.yaml."""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "graph-config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_env(env_path: str | None = None) -> None:
    """Load .env file (simple KEY=VALUE parser, no dotenv dependency)."""
    if env_path is None:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def get_neo4j_config(cfg: dict) -> tuple[str, str]:
    """Return (uri, database) from config, (user, password) from env."""
    uri = cfg["neo4j"]["uri"]
    database = cfg["neo4j"]["database"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    return uri, database, user, password


def fetch_all_feishu_data(cfg: dict) -> dict[str, list[dict]]:
    """Fetch records for all entities and via tables."""
    app_token = cfg["feishu"]["app_token"]
    entities = cfg["entities"]
    relationships = cfg["relationships"]

    feishu_data = {}

    # Fetch entity records
    for label, entity_cfg in entities.items():
        table_id = entity_cfg["table_id"]
        print(f"  拉取 [{label}] ({table_id})...")
        fields = fetch_table_fields(app_token, table_id)
        records = fetch_table_records(app_token, table_id, fields)
        feishu_data[label] = records
        print(f"    {len(records)} 条记录, {len(fields)} 个字段")

    # Fetch via tables (for relationship intermediaries)
    via_tables_seen = set()
    for rel in relationships:
        if "via" in rel:
            via_cfg = rel["via"]
            table_id = via_cfg["table_id"]
            if table_id in via_tables_seen:
                continue
            via_tables_seen.add(table_id)
            key = f"via_{table_id}"
            print(f"  拉取 [中间表 {table_id}]...")
            fields = fetch_table_fields(app_token, table_id)
            records = fetch_table_records(app_token, table_id, fields)
            feishu_data[key] = records
            print(f"    {len(records)} 条记录")

    return feishu_data


def download_model(model_path: str, model_name: str) -> None:
    """Download SentenceTransformer model to local folder."""
    from sentence_transformers import SentenceTransformer
    abs_path = os.path.abspath(model_path)
    print(f"下载模型 {model_name} -> {abs_path}")
    os.makedirs(abs_path, exist_ok=True)
    model = SentenceTransformer(model_name)
    model.save(abs_path)
    print(f"模型已保存到 {abs_path}")


def main():
    parser = argparse.ArgumentParser(description="GraphRAG sync pipeline")
    parser.add_argument("--only", choices=["fetch", "graph", "embed"],
                        help="Run only one phase")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--force-embed", action="store_true", help="Force regenerate all embeddings")
    parser.add_argument("--download-model", action="store_true", help="Download embedding model")
    args = parser.parse_args()

    load_env()
    cfg = load_config()
    uri, database, user, password = get_neo4j_config(cfg)
    entities_config = cfg["entities"]
    relationships_config = cfg["relationships"]
    embedding_cfg = cfg["embedding"]
    model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", embedding_cfg["model_path"]))
    dimensions = embedding_cfg["dimensions"]

    # Download model if requested
    if args.download_model:
        download_model(model_path, embedding_cfg["model"])
        return

    # Check model exists
    if args.only in (None, "embed") and not os.path.isdir(model_path):
        print(f"错误：模型路径不存在 {model_path}")
        print(f"请先运行: python sync.py --download-model")
        sys.exit(1)

    # Phase: Fetch
    if args.only in (None, "fetch"):
        print("\n=== Phase 1: 拉取飞书数据 ===")
        feishu_data = fetch_all_feishu_data(cfg)
        print(f"  共拉取 {len(feishu_data)} 个数据集")
    else:
        # For graph-only or embed-only, we don't need Feishu data
        feishu_data = {}

    if args.dry_run:
        print("\nDRY RUN: 预览完成，不写入。")
        for label, records in feishu_data.items():
            print(f"  [{label}]: {len(records)} 条")
        return

    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        # Phase: Graph
        if args.only in (None, "graph"):
            print("\n=== Phase 2: 构建 Neo4j 图 ===")

            if args.only is None:
                # Full sync: clear and rebuild
                clear_graph(driver)

            # Build nodes
            print("  创建节点...")
            node_counts = build_nodes(driver, entities_config, feishu_data)
            for label, count in node_counts.items():
                print(f"    [{label}]: {count} 个节点")

            # Build relationships
            print("  创建关系...")
            rel_counts = build_relationships(driver, relationships_config, entities_config, feishu_data)
            for desc, count in rel_counts.items():
                print(f"    {desc}: {count} 条")

        # Phase: Embed
        if args.only in (None, "embed"):
            print("\n=== Phase 3: 向量化 ===")

            # Generate search_text
            print("  生成 search_text...")
            st_counts = generate_search_text(driver, entities_config)
            for label, count in st_counts.items():
                print(f"    [{label}]: {count} 条")

            # Create vector indexes
            print("  创建向量索引...")
            indexes = create_vector_indexes(driver, entities_config, dimensions)
            print(f"  共 {len(indexes)} 个向量索引")

            # Generate embeddings
            print("  生成 embedding...")
            emb_counts = embed_nodes(driver, entities_config, model_path, dimensions, force=args.force_embed)
            for label, count in emb_counts.items():
                print(f"    [{label}]: {count} 个")

        print("\n✓ 同步完成")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify sync.py syntax**

Run: `cd retrieving-business-context && python -c "from sync.sync import load_config, load_env; load_env(); cfg = load_config(); print(f'{len(cfg[\"entities\"])} entities'); print('sync OK')"`

Expected: `8 entities` then `sync OK`

- [ ] **Step 3: Commit**

```bash
git add retrieving-business-context/sync/sync.py
git commit -m "feat(graphrag): sync.py — main orchestrator CLI"
```

---

### Task 6: Download Model + Full Sync Test

**Files:** None new. Uses existing sync pipeline.

This task downloads the embedding model and runs a full end-to-end sync to verify the entire pipeline works.

- [ ] **Step 1: Download embedding model**

Run: `cd retrieving-business-context && python sync/sync.py --download-model`

Expected: Model downloads to `sync/models/bge-small-zh-v1.5/`. This may take a few minutes on first run.

- [ ] **Step 2: Verify model exists**

Run: `ls retrieving-business-context/sync/models/bge-small-zh-v1.5/`

Expected: Directory contains files like `config.json`, `model.safetensors`, `tokenizer.json`, etc.

- [ ] **Step 3: Run full sync**

Run: `cd retrieving-business-context && python sync/sync.py`

Expected output (approximate):
```
=== Phase 1: 拉取飞书数据 ===
  拉取 [业务线] (tbljp4PEWKQcjQzD)...
    N 条记录, N 个字段
  ...
=== Phase 2: 构建 Neo4j 图 ===
  创建节点...
    [业务线]: N 个节点
    ...
  创建关系...
    (业务线)-[:包含]->(业务板块): N 条
    ...
=== Phase 3: 向量化 ===
  生成 search_text...
    [业务线]: N 条
    ...
  创建向量索引...
  生成 embedding...
    [业务线]: N 个
    ...
✓ 同步完成
```

- [ ] **Step 4: Verify Neo4j has data**

Run: `cd retrieving-business-context && python -c "from neo4j import GraphDatabase; import os; d=GraphDatabase.driver('bolt://localhost:7687',auth=('neo4j',os.getenv('NEO4J_PASSWORD','hejiachengg'))); s=d.session(database='neo4j'); print('Nodes:', list(s.run('MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt'))); print('Rels:', list(s.run('MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS cnt'))); d.close()"`

Expected: Non-zero counts for nodes and relationships.

- [ ] **Step 5: Test encode CLI**

Run: `cd retrieving-business-context && python sync/embedding.py encode "复购人数是什么意思？"`

Expected: A JSON array of 512 floats printed to stdout.

- [ ] **Step 6: Commit (model in .gitignore)**

Add model dir to gitignore if not already, then commit any remaining changes. The model files are large and should NOT be committed.

- [ ] **Step 7: Add model to .gitignore**

Add this line to `retrieving-business-context/.gitignore`:
```
sync/models/
```

```bash
git add retrieving-business-context/.gitignore
git commit -m "chore(graphrag): ignore model files in git"
```

---

### Task 7: server/query.js — Node.js Query CLI

**Files:**
- Create: `retrieving-business-context/server/query.js`

Node.js CLI that: (1) calls Python subprocess to encode the question, (2) queries Neo4j vector indexes, (3) expands graph context, (4) outputs JSON.

- [ ] **Step 1: Create query.js**

```javascript
#!/usr/bin/env node
// query.js — GraphRAG query CLI
// Usage: node query.js "用户问题" [--top-k 5] [--targets 表,指标]
//
// Output: JSON { question, results: [{ label, score, properties, context }] }

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import neo4j from "neo4j-driver";

// --- Config loading ---

const __dirname = path.dirname(new URL(import.meta.url).toString().replace("file:///", ""));
const PROJECT_DIR = path.resolve(__dirname, "..");

function loadEnv() {
  const envPath = path.join(PROJECT_DIR, ".env");
  if (!fs.existsSync(envPath)) return;
  const content = fs.readFileSync(envPath, "utf-8");
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq > 0) {
      const key = trimmed.slice(0, eq).trim();
      const value = trimmed.slice(eq + 1).trim();
      if (!process.env[key]) process.env[key] = value;
    }
  }
}

function loadConfig() {
  const configPath = path.join(PROJECT_DIR, "graph-config.yaml");
  // Simple YAML parser for our config structure (no external dep needed)
  // Since our YAML is simple, we use a minimal approach
  // Actually, we read the config from Neo4j at query time, or hardcode the index mapping
  // For now, we derive index names from entity labels
  const yamlContent = fs.readFileSync(configPath, "utf-8");

  // Parse entities section to find which have vector_index=true
  const entities = {};
  const entityRegex = /^  (\S+):\s*$/gm;
  const blockRegex = /^  (\S+):\s*\n((?:    .+\n)*)/gm;

  let match;
  while ((match = blockRegex.exec(yamlContent)) !== null) {
    const label = match[1];
    const body = match[2];
    const vectorIndex = !body.includes("vector_index: false");
    const tableIdMatch = body.match(/table_id:\s*(\S+)/);
    const keyFieldMatch = body.match(/key_field:\s*(.+)/);
    if (tableIdMatch && keyFieldMatch) {
      entities[label] = {
        table_id: tableIdMatch[1],
        key_field: keyFieldMatch[1].trim(),
        vector_index: vectorIndex,
      };
    }
  }

  // Parse embedding config
  const dimMatch = yamlContent.match(/dimensions:\s*(\d+)/);
  const dimensions = dimMatch ? parseInt(dimMatch[1]) : 512;

  const uriMatch = yamlContent.match(/uri:\s*(\S+)/);
  const dbMatch = yamlContent.match(/database:\s*(\S+)/);
  const modelPathMatch = yamlContent.match(/model_path:\s*(\S+)/);

  return {
    neo4j: {
      uri: uriMatch ? uriMatch[1] : "bolt://localhost:7687",
      database: dbMatch ? dbMatch[1] : "neo4j",
    },
    embedding: {
      dimensions,
      model_path: modelPathMatch ? modelPathMatch[1] : "sync/models/bge-small-zh-v1.5",
    },
    entities,
  };
}

// --- Embedding via Python subprocess ---

function encodeQuestion(text, modelPath) {
  const absModelPath = path.resolve(PROJECT_DIR, modelPath);
  const scriptPath = path.join(PROJECT_DIR, "sync", "embedding.py");

  const result = execFileSync("python", [scriptPath, "encode", text, "--model-path", absModelPath], {
    encoding: "utf-8",
    timeout: 30000,
    shell: true,
  });

  return JSON.parse(result.trim());
}

// --- Neo4j vector search ---

async function searchVectorIndex(session, indexName, label, embedding, topK) {
  const escapedIndex = indexName.replace(/`/g, "``");
  const cypher = `
    MATCH (node:\`${label}\`)
      SEARCH node IN (
        VECTOR INDEX \`${escapedIndex}\`
        FOR $embedding
        LIMIT $topK
      ) SCORE AS score
    RETURN elementId(node) AS id,
           score,
           properties(node) AS properties
    ORDER BY score DESC
  `;

  const result = await session.run(cypher, { embedding, topK: neo4j.int(topK) });
  return result.records.map((record) => ({
    id: record.get("id"),
    score: record.get("score"),
    properties: record.get("properties"),
  }));
}

// --- Graph context expansion ---

async function fetchGraphContext(session, label, keyField, keyFieldVal, relationships) {
  const context = {};

  for (const rel of relationships) {
    const relType = rel.type;
    const isFrom = rel.from === label;
    const isTo = rel.to === label;

    if (!isFrom && !isTo) continue;

    const escapedRelType = relType.replace(/`/g, "``");
    const otherLabel = isFrom ? rel.to : rel.from;
    const escapedOther = otherLabel.replace(/`/g, "``");
    const escapedThisLabel = label.replace(/`/g, "``");
    const escapedKeyField = keyField.replace(/`/g, "``");

    let cypher;
    if (isFrom) {
      cypher = `
        MATCH (a:\`${escapedThisLabel}\` {\`${escapedKeyField}\`: $keyVal})-[:\`${escapedRelType}\`]->(b:\`${escapedOther}\`)
        RETURN properties(b) AS props
        LIMIT 10
      `;
    } else {
      cypher = `
        MATCH (b:\`${escapedOther}\`)-[:\`${escapedRelType}\`]->(a:\`${escapedThisLabel}\` {\`${escapedKeyField}\`: $keyVal})
        RETURN properties(b) AS props
        LIMIT 10
      `;
    }

    try {
      const result = await session.run(cypher, { keyVal: keyFieldVal });
      if (result.records.length > 0) {
        // Filter out internal properties
        context[otherLabel] = result.records.map((r) => {
          const props = r.get("props");
          const cleaned = {};
          for (const [k, v] of Object.entries(props)) {
            if (!["search_text", "embedding", "embedding_model", "embedding_dimensions", "embedding_updated_at"].includes(k)) {
              cleaned[k] = v;
            }
          }
          return cleaned;
        });
      }
    } catch {
      // Skip relationships that don't exist in the graph
    }
  }

  return context;
}

// --- Parse relationships from config YAML ---

function parseRelationships() {
  const configPath = path.join(PROJECT_DIR, "graph-config.yaml");
  const content = fs.readFileSync(configPath, "utf-8");

  const rels = [];
  const relRegex = /^  - type: (.+)\n((?:    .+\n)*)/gm;
  let match;
  while ((match = relRegex.exec(content)) !== null) {
    const type = match[1].trim();
    const body = match[2];
    const fromMatch = body.match(/from: (\S+)/);
    const toMatch = body.match(/to: (\S+)/);
    if (fromMatch && toMatch) {
      rels.push({ type, from: fromMatch[1], to: toMatch[1] });
    }
  }
  return rels;
}

// --- Main ---

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { question: "", topK: 5, targets: null };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--top-k" && args[i + 1]) {
      opts.topK = parseInt(args[++i]);
    } else if (args[i] === "--targets" && args[i + 1]) {
      opts.targets = args[++i].split(",").map((s) => s.trim());
    } else if (!args[i].startsWith("-") && !opts.question) {
      opts.question = args[i];
    }
  }

  if (!opts.question) {
    console.error('Usage: node query.js "问题" [--top-k 5] [--targets 表,指标]');
    process.exit(1);
  }

  return opts;
}

async function main() {
  loadEnv();
  const config = loadConfig();
  const opts = parseArgs();
  const relationships = parseRelationships();

  // 1. Encode question
  console.error(`编码问题: ${opts.question}`);
  const embedding = encodeQuestion(opts.question, config.embedding.model_path);

  // 2. Connect to Neo4j
  const user = process.env.NEO4J_USER || "neo4j";
  const password = process.env.NEO4J_PASSWORD || "";
  const driver = neo4j.driver(config.neo4j.uri, neo4j.auth.basic(user, password));
  const session = driver.session({ database: config.neo4j.database });

  try {
    const results = [];

    // 3. Search vector indexes
    const targetLabels = opts.targets
      ? Object.entries(config.entities).filter(([l]) => opts.targets.includes(l))
      : Object.entries(config.entities).filter(([, c]) => c.vector_index);

    for (const [label, entityCfg] of targetLabels) {
      if (!entityCfg.vector_index) continue;

      const indexName = `${label}_embedding_index`;
      console.error(`搜索索引: ${indexName}`);

      try {
        const hits = await searchVectorIndex(session, indexName, label, embedding, opts.topK);

        for (const hit of hits) {
          // Filter internal properties from output
          const cleanProps = {};
          for (const [k, v] of Object.entries(hit.properties)) {
            if (!["search_text", "embedding", "embedding_model", "embedding_dimensions", "embedding_updated_at"].includes(k)) {
              cleanProps[k] = v;
            }
          }

          // 4. Fetch graph context
          const keyField = entityCfg.key_field;
          const keyFieldVal = hit.properties[keyField];
          const context = await fetchGraphContext(session, label, keyField, keyFieldVal, relationships);

          results.push({
            label,
            score: hit.score,
            properties: cleanProps,
            context,
          });
        }
      } catch (err) {
        console.error(`  索引 ${indexName} 查询失败: ${err.message}`);
      }
    }

    // 5. Sort by score and output
    results.sort((a, b) => b.score - a.score);

    const output = { question: opts.question, results };
    console.log(JSON.stringify(output, null, 2));
  } finally {
    await session.close();
    await driver.close();
  }
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
```

- [ ] **Step 2: Install neo4j-driver**

Run: `cd retrieving-business-context/server && npm install`

- [ ] **Step 3: Test query.js with a real question**

Run: `cd retrieving-business-context && node server/query.js "复购人数是什么意思？" --top-k 3`

Expected: JSON output with `results` array containing hits from vector indexes, each with `label`, `score`, `properties`, and `context` fields.

- [ ] **Step 4: Test with target filtering**

Run: `cd retrieving-business-context && node server/query.js "用户听课明细去哪张表看？" --targets 表 --top-k 3`

Expected: JSON output with results only from the `表` vector index.

- [ ] **Step 5: Commit**

```bash
git add retrieving-business-context/server/query.js retrieving-business-context/server/package-lock.json
git commit -m "feat(graphrag): query.js — Node.js vector search + graph expansion CLI"
```

---

### Task 8: SKILL.md + CLAUDE.md

**Files:**
- Create: `retrieving-business-context/SKILL.md`
- Create: `retrieving-business-context/CLAUDE.md`

- [ ] **Step 1: Create SKILL.md**

```markdown
---
name: retrieving-business-context
description: 检索业务知识图谱，回答业务概念、指标定义、数据来源、业务关系等问题。触发词：业务上下文、指标含义、哪张表、数据来源、业务板块
---

# 业务知识检索（GraphRAG）

通过本地 Neo4j 图数据库 + 向量语义检索，获取业务上下文。适用于回答业务概念、指标定义、数据表来源、业务线/板块/小点层级关系等问题。

## 触发条件

- 用户问业务概念："复购人数是什么意思？"
- 用户问数据来源："去哪张表查用户听课明细？"
- 用户问业务关系："前端增长投放包含哪些业务小点？"
- 用户问数据看板："哪个看板能看这个指标？"
- 其他 skill 需要业务上下文时引用

## 前置条件

- Neo4j 本地运行 (`bolt://localhost:7687`)
- 数据已同步（运行过 `python sync/sync.py`）
- Node.js 18+

## CLI 命令

```bash
# 查询业务上下文
node server/query.js "用户问题" [--top-k 5] [--targets 表,指标]
```

参数说明：
- `--top-k N`：每个向量索引返回的最大结果数，默认 5
- `--targets 逗号分隔的实体名`：限制搜索范围。可用值：业务线,业务板块,业务小点,指标,维度,表

## 核心流程

1. **理解用户意图**：判断用户在问什么类型的业务知识
2. **构造检索问题**：可以直接用用户原话，也可以改写为更精确的检索词
3. **执行查询**：`node server/query.js "检索问题" --top-k 5`
4. **解读结果**：基于返回的 JSON 上下文回答用户
   - 引用具体的指标定义、表名、业务板块名称
   - 说明层级关系（业务线 → 业务板块 → 业务小点 → 指标）
   - 如果涉及表关联，说明上下游表关系和关联条件
   - 如果结果不充分，换关键词重新查询
5. **格式化回答**：用清晰的结构组织信息

## 输出格式

查询返回 JSON 结构：
```json
{
  "question": "用户问题",
  "results": [
    {
      "label": "实体标签（如 指标、表、业务板块）",
      "score": 0.89,
      "properties": { "字段名": "值" },
      "context": { "关联实体标签": [{ "字段名": "值" }] }
    }
  ]
}
```

## 数据同步（维护时使用）

```bash
# 一键全流程同步（飞书 → Neo4j）
python sync/sync.py

# 分步执行
python sync/sync.py --only fetch       # 只拉飞书数据
python sync/sync.py --only graph       # 只建图
python sync/sync.py --only embed       # 只重建向量

# 下载/更新 embedding 模型
python sync/sync.py --download-model
```

## 回答指引

当拿到检索结果后：
- **指标类问题**：给出指标定义、所属业务板块、在哪个数据看板可以看
- **数据表问题**：给出表中文名、表名全称、所属数据域、上下游关联表
- **业务层级问题**：给出完整的 业务线→业务板块→业务小点 链路
- **维度问题**：给出维度名称、字段名称、级别、来自哪张表
- 如果 score 很低（<0.5），告知用户可能没有找到匹配的业务知识
```

- [ ] **Step 2: Create CLAUDE.md**

```markdown
# retrieving-business-context 技术参考

## 架构

```
graph-config.yaml        # 唯一真相来源
sync/                    # Python 同步管线
  sync.py                # 主入口
  feishu_reader.py       # lark-cli → 飞书数据
  graph_builder.py       # Neo4j 建图
  embedding.py           # search_text + 向量化
  models/                # 本地 embedding 模型
server/
  query.js               # Node.js 查询 CLI
```

## 配置文件

- `graph-config.yaml`：实体定义、关系映射、向量开关。改字段/改关系只改这里
- `.env`：NEO4J_USER, NEO4J_PASSWORD

## 关键实现细节

### feishu_reader.py
- 调用 `lark-cli base +field-list` 和 `+record-list --page-all`
- 使用 `subprocess.run(cmd, shell=True)` (Windows 兼容)
- 自动过滤 auto_number 字段
- 多选字段返回 list，文本字段拼接 segments

### graph_builder.py
- 节点用 `MERGE` 保证幂等
- 三种关系匹配模式：direct / multi / via
- 关系通过 `key_field` 值匹配，不依赖飞书外键
- via 中间表支持关系属性（如关联类型、关联表达式）

### embedding.py
- search_text 自动拼接：所有属性 `字段名：值。` 格式
- 过滤内部属性（search_text, embedding 等）
- 模型加载自本地路径 `sync/models/bge-small-zh-v1.5`
- `encode` 子命令供 Node.js 调用，输出 JSON 向量

### query.js
- ESM 模块，neo4j-driver 直连
- 调 Python 子进程做向量化（`python embedding.py encode "文本"`）
- 使用 Neo4j SEARCH Cypher 子句查询向量索引
- 图关系扩展根据 config 自动生成 OPTIONAL MATCH
- 输出 JSON 到 stdout，日志到 stderr

## Neo4j 向量索引

索引命名规则：`{实体标签}_embedding_index`
- 使用 cosine similarity，512 维
- 通过 Neo4j SEARCH 子句查询（2025.01+ 版本）

## Embedding 模型

- 模型：BAAI/bge-small-zh-v1.5
- 维度：512
- 存储：`sync/models/bge-small-zh-v1.5/`（本地完整文件）
- 不提交到 git（.gitignore 排除）
```

- [ ] **Step 3: Commit**

```bash
git add retrieving-business-context/SKILL.md retrieving-business-context/CLAUDE.md
git commit -m "feat(graphrag): SKILL.md + CLAUDE.md — agent skill definition"
```

---

### Task 9: End-to-End Verification

**Files:** None new. Verifies the complete pipeline works together.

- [ ] **Step 1: Full rebuild sync**

Run: `cd retrieving-business-context && python sync/sync.py`

Expected: All phases complete without error.

- [ ] **Step 2: Test typical queries**

```bash
cd retrieving-business-context

# Test 1: Metric query
node server/query.js "复购人数是什么意思？" --top-k 3

# Test 2: Table query
node server/query.js "用户听课明细去哪张表看？" --top-k 3

# Test 3: Business domain query
node server/query.js "前端增长投放包含哪些业务？" --top-k 3

# Test 4: Dashboard query
node server/query.js "哪个看板能看VIP相关的指标？" --top-k 5

# Test 5: Target filtering
node server/query.js "订单金额" --targets 指标 --top-k 3
```

Expected: Each query returns meaningful JSON results with relevant context.

- [ ] **Step 3: Verify SKILL.md is discoverable**

Run: `ls retrieving-business-context/SKILL.md`

Expected: File exists with proper frontmatter and sections.

- [ ] **Step 4: Final commit**

```bash
git add -A retrieving-business-context/
git status
# Review that no model files or sensitive data are staged
git commit -m "feat(graphrag): retrieving-business-context GraphRAG skill complete"
```

---

## Plan Self-Review

**Spec coverage:**
- ✅ graph-config.yaml with 8 entities, 7 relationships
- ✅ YAML-driven, no dependency on Feishu foreign keys
- ✅ Auto search_text generation (no manual templates)
- ✅ vector_index toggle (default true, 数据看板/数据域 set to false)
- ✅ Python sync pipeline (feishu_reader → graph_builder → embedding)
- ✅ Node.js query CLI (vector search + graph expansion)
- ✅ Local model storage at sync/models/
- ✅ SKILL.md + CLAUDE.md

**Placeholder scan:** No TBD/TODO found. All steps contain actual code or exact commands.

**Type consistency:** All functions use consistent parameter names across modules (driver, entities_config, feishu_data). query.js uses the same config key names as Python sync.
