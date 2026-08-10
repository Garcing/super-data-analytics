"""GraphRAG sync 内核：飞书多维表 → Neo4j 图 → fastembed(ONNX) 向量。

移植 retrieving-context/scripts/pipeline/{sync,feishu_reader,graph_builder,embedding}.py，
去 CLI/argparse/print；embedding 用 fastembed（与查询侧 retrieving_context.embed 同源 →
向量自洽，无 ONNX/PyTorch 混用 parity 风险）。失败抛 SkillError。

公共入口：sync_graph(only=None, dry_run=False, force_embed=False) -> dict[str,Any]。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sda_mcp.config import get_env, load_config
from sda_mcp.errors import ConfigError, ExternalAPIError, ValidationError
from sda_mcp.feishu import FeishuClient
from sda_mcp.feishu import (_F_AUTO_NUMBER, _F_TEXT, _F_SINGLE_SELECT,
                            _F_MULTI_SELECT, _F_FORMULA, _F_LOOKUP)
from sda_mcp.skills.retrieving_context import Neo4jClient

_SKIP_PROPS = frozenset({"search_text", "embedding", "embedding_model",
                         "embedding_dimensions", "embedding_updated_at"})


def _escape(label: str) -> str:
    """Escape a label for Cypher backtick quotes (replace ` with ``)。

    对齐 graph_builder._escape / embedding._escape。
    """
    return label.replace("`", "``")


def _should_vectorize(cfg: dict) -> bool:
    """对齐 embedding._should_vectorize：vector_index 默认 True。"""
    return (cfg or {}).get("vector_index", True) is not False


def _format_value(value) -> str:
    """对齐 embedding._format_value：list 用中文顿号连接，其余 str()。"""
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value)


# ---------- Phase 1: feishu fetch（开放平台 FeishuClient + 值简化器）----------

def fetch_table_fields(app_token: str, table_id: str) -> list[dict]:
    """开放平台字段 → {name,type,id}，过滤 auto_number。"""
    raw = FeishuClient().list_bitable_fields(app_token, table_id)
    return [{"name": f.get("field_name"), "type": f.get("type"), "id": f.get("field_id")}
            for f in raw if f.get("type") != _F_AUTO_NUMBER]


def _join_text(runs: Any) -> Any:
    """text 字段值（[{text:..}] 或字符串）→ 拼接字符串；空→None。"""
    if isinstance(runs, str):
        return runs.strip() or None
    if isinstance(runs, list):
        parts = [r.get("text", "") if isinstance(r, dict) else str(r) for r in runs]
        return "".join(parts).strip() or None
    return runs


def _opt_to_str(v: Any) -> Any:
    """单选项（字符串 或 {text:'x'}）→ 字符串；空→None。"""
    if isinstance(v, dict):
        return (v.get("text") or v.get("name") or "").strip() or None
    if isinstance(v, str):
        return v.strip() or None
    return v


def _simplify_value(field_type: int, value: Any) -> Any:
    """开放平台记录值 → graph 用的简化形式。对齐旧 _extract_cell 的输出契约。"""
    if value is None:
        return None
    # 公式(20)/查找引用(19) 文本结果与 Text(1) 同构（[{text,type}] 片段数组）；
    # 非文本结果（数字）经 _join_text 原样返回。本 base 公式/lookup 均为文本结果（已验证）。
    if field_type in (_F_TEXT, _F_FORMULA, _F_LOOKUP):
        return _join_text(value)
    if field_type == _F_SINGLE_SELECT:
        return _opt_to_str(value)
    if field_type == _F_MULTI_SELECT:
        if isinstance(value, list):
            return [_opt_to_str(v) for v in value if _opt_to_str(v) is not None]
        v = _opt_to_str(value)
        return [v] if v is not None else None
    if isinstance(value, str):
        return value.strip() or None
    return value


def fetch_table_records(app_token: str, table_id: str, fields: list[dict] | None = None) -> list[dict]:
    """开放平台记录 → [{字段名: 简化值}, ...]，过滤 None/空字符串。"""
    if fields is None:
        fields = fetch_table_fields(app_token, table_id)
    field_types = {f["name"]: f["type"] for f in fields}
    items = FeishuClient().list_bitable_records(app_token, table_id)
    records: list[dict] = []
    for item in items:
        raw_fields = item.get("fields") or {}
        rec: dict = {}
        for name, ftype in field_types.items():
            if name in raw_fields:
                val = _simplify_value(ftype, raw_fields[name])
                if val is not None and val != "":
                    rec[name] = val
        records.append(rec)
    return records


def _fetch_all_feishu(gc: dict) -> dict[str, list[dict]]:
    """移植 sync.fetch_all_feishu_data：拉所有 entity + via 中间表。"""
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

def _clear_graph(client: Neo4jClient) -> None:
    """移植 graph_builder.clear_graph：MATCH (n) DETACH DELETE n。"""
    client.execute("MATCH (n) DETACH DELETE n")


def _build_nodes(client: Neo4jClient, entities: dict, feishu_data: dict) -> dict[str, int]:
    """移植 graph_builder.build_nodes：MERGE on key_field + SET n += props，幂等去重。"""
    counts: dict[str, int] = {}
    for label, cfg in entities.items():
        key_field = cfg["key_field"]
        records = feishu_data.get(label, [])
        if not records:
            counts[label] = 0
            continue
        esc_label = _escape(label)
        esc_key = _escape(key_field)
        for record in records:
            key_value = record.get(key_field)
            if key_value is None:
                continue
            other_props = {k: v for k, v in record.items() if k != key_field}
            cypher = (
                f"MERGE (n:`{esc_label}` {{`{esc_key}`: $key_value}}) "
                f"SET n += $props"
            )
            client.execute(cypher, key_value=key_value, props=other_props)
        rows = client.run_cypher(f"MATCH (n:`{esc_label}`) RETURN count(n) AS cnt")
        counts[label] = int(rows[0]["cnt"]) if rows else 0
    return counts


def _build_relationships(client: Neo4jClient, relationships: list, entities: dict,
                         feishu_data: dict) -> dict[str, int]:
    """移植 graph_builder.build_relationships：direct match + via 中间表两种模式。"""
    counts: dict[str, int] = {}
    for rel_cfg in relationships:
        rel_type = rel_cfg["type"]
        from_label = rel_cfg["from"]
        to_label = rel_cfg["to"]
        tag = f"{from_label}-{rel_type}->{to_label}"
        from_key = entities[from_label]["key_field"]
        to_key = entities[to_label]["key_field"]
        count = 0

        esc_from = _escape(from_label)
        esc_to = _escape(to_label)
        esc_rel = _escape(rel_type)
        esc_from_key = _escape(from_key)
        esc_to_key = _escape(to_key)

        if "via" in rel_cfg:
            via_cfg = rel_cfg["via"]
            via_table_id = via_cfg["table_id"]
            via_from_field = via_cfg["from_field"]
            via_to_field = via_cfg["to_field"]
            via_props_fields = via_cfg.get("properties", [])
            via_records = feishu_data.get(f"via_{via_table_id}", [])
            for via_rec in via_records:
                from_val = via_rec.get(via_from_field)
                to_val = via_rec.get(via_to_field)
                if from_val is None or to_val is None:
                    continue
                props = {k: via_rec[k] for k in via_props_fields
                         if k in via_rec and via_rec[k] is not None}
                cypher = (
                    f"MATCH (a:`{esc_from}` {{`{esc_from_key}`: $from_val}}) "
                    f"MATCH (b:`{esc_to}` {{`{esc_to_key}`: $to_val}}) "
                    f"MERGE (a)-[r:`{esc_rel}`]->(b) "
                    f"SET r += $props"
                )
                client.execute(cypher, from_val=from_val, to_val=to_val, props=props)
                count += 1
        else:
            match_cfg = rel_cfg["match"]
            source_field = match_cfg["source_field"]
            target_field = match_cfg["target_field"]
            from_records = feishu_data.get(from_label, [])
            to_records = feishu_data.get(to_label, [])
            to_lookup: dict[str, list] = {}
            for rec in to_records:
                target_val = rec.get(target_field)
                key_val = rec.get(to_key)
                if target_val is None or key_val is None:
                    continue
                vals = [target_val] if not isinstance(target_val, list) else target_val
                for v in vals:
                    to_lookup.setdefault(v, []).append(key_val)
            for from_rec in from_records:
                from_key_val = from_rec.get(from_key)
                if from_key_val is None:
                    continue
                source_value = from_rec.get(source_field)
                if source_value is None:
                    continue
                source_values = source_value if isinstance(source_value, list) else [source_value]
                for source_val in source_values:
                    matched_to_keys = to_lookup.get(source_val)
                    if not matched_to_keys:
                        continue
                    for to_key_val in matched_to_keys:
                        cypher = (
                            f"MATCH (a:`{esc_from}` {{`{esc_from_key}`: $from_key_val}}) "
                            f"MATCH (b:`{esc_to}` {{`{esc_to_key}`: $to_key_val}}) "
                            f"MERGE (a)-[:`{esc_rel}`]->(b)"
                        )
                        client.execute(cypher, from_key_val=from_key_val, to_key_val=to_key_val)
                        count += 1
        counts[tag] = count
    return counts


# ---------- Phase 3: embed（移植 embedding.py 的非 embed 部分 + fastembed 替换）----------

def _generate_search_text(client: Neo4jClient, entities: dict) -> dict[str, int]:
    """移植 embedding.generate_search_text（84-136）：拼 '字段名：值。' 写回 n.search_text。"""
    counts: dict[str, int] = {}
    for label, cfg in entities.items():
        if not _should_vectorize(cfg):
            continue
        esc_label = _escape(label)
        rows = client.run_cypher(
            f"MATCH (n:`{esc_label}`) "
            f"RETURN properties(n) AS props, elementId(n) AS id"
        )
        count = 0
        for row in rows:
            props = row.get("props") or {}
            node_id = row.get("id")
            parts: list[str] = []
            for key, value in props.items():
                if key in _SKIP_PROPS:
                    continue
                if value is None:
                    continue
                parts.append(f"{key}：{_format_value(value)}。")
            text = "".join(parts)
            if not text:
                continue
            client.execute(
                f"MATCH (n) WHERE elementId(n) = $id "
                f"SET n.search_text = $text",
                id=node_id, text=text,
            )
            count += 1
        counts[label] = count
    return counts


def _create_vector_indexes(client: Neo4jClient, entities: dict, dimensions: int) -> list[str]:
    """移植 embedding.create_vector_indexes（139-179）：CREATE VECTOR INDEX IF NOT EXISTS，cosine。"""
    index_names: list[str] = []
    for label, cfg in entities.items():
        if not _should_vectorize(cfg):
            continue
        esc_label = _escape(label)
        index_name = f"{label}_embedding_index"
        cypher = (
            f"CREATE VECTOR INDEX `{_escape(index_name)}` IF NOT EXISTS "
            f"FOR (n:`{esc_label}`) ON (n.embedding) "
            f"OPTIONS {{ "
            f"indexConfig: {{ "
            f"`vector.dimensions`: {dimensions}, "
            f"`vector.similarity_function`: 'cosine' "
            f"}} "
            f"}}"
        )
        client.execute(cypher)
        index_names.append(index_name)
    return index_names


def _embed_nodes(client: Neo4jClient, entities: dict, dimensions: int, force: bool) -> dict[str, int]:
    """生成 embedding。**关键差异**：用 fastembed 批量编码（retrieving_context.embed 同源），
    替代原 SentenceTransformer。fastembed 对 bge 默认 L2 归一化（与原 normalize_embeddings=True 一致）。
    写回字段对齐 embedding.embed_nodes（264-277）：n.embedding / embedding_model /
    embedding_dimensions / embedding_updated_at。"""
    model = (load_config().get("graph-config", {}).get("embedding", {}) or {}).get(
        "model", "BAAI/bge-small-zh-v1.5")
    from fastembed import TextEmbedding
    fe = TextEmbedding(model_name=model)
    counts: dict[str, int] = {}
    for label, cfg in entities.items():
        if not _should_vectorize(cfg):
            continue
        esc_label = _escape(label)
        where = ("n.search_text IS NOT NULL" if force
                 else "n.search_text IS NOT NULL AND n.embedding IS NULL")
        rows = client.run_cypher(
            f"MATCH (n:`{esc_label}`) WHERE {where} "
            f"RETURN elementId(n) AS id, n.search_text AS text"
        )
        if not rows:
            counts[label] = 0
            continue
        texts = [r["text"] for r in rows]
        ids = [r["id"] for r in rows]
        vecs = list(fe.embed(texts))   # fastembed 批量，已 L2 归一化
        now = datetime.now(timezone.utc).isoformat()
        for nid, emb in zip(ids, vecs):
            client.execute(
                f"MATCH (n) WHERE elementId(n) = $id "
                f"SET n.embedding = $emb, "
                f"    n.embedding_model = $model, "
                f"    n.embedding_dimensions = $dims, "
                f"    n.embedding_updated_at = datetime($now)",
                id=nid, emb=list(emb), model=model, dims=dimensions, now=now,
            )
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
            result["relationships"] = _build_relationships(
                client, gc.get("relationships", []), gc["entities"], feishu_data)
        if only in (None, "embed"):
            result["search_text"] = _generate_search_text(client, gc["entities"])
            result["indexes"] = len(_create_vector_indexes(client, gc["entities"], dimensions))
            result["embed"] = _embed_nodes(client, gc["entities"], dimensions, force_embed)
    finally:
        client.close()
    return result
