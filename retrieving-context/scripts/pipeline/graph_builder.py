"""
graph_builder.py — Read YAML config and Feishu data to MERGE nodes
and create relationships in Neo4j.

Functions:
    _escape(label) -> str
    _expand_records(records) -> list[dict]
    build_nodes(driver, entities_config, feishu_data) -> dict[str, int]
    build_relationships(driver, relationships_config, entities_config, feishu_data) -> dict[str, int]
    clear_graph(driver) -> None
"""
from __future__ import annotations


def _escape(label: str) -> str:
    """Escape a label for Cypher backtick quotes (replace ` with ``)."""
    return label.replace("`", "``")


def _expand_records(records: list[dict]) -> list[dict]:
    """Expand multi-valued (list) fields into separate rows.

    For each record, any field whose value is a list gets expanded into
    one row per element. Multiple list fields are expanded via recursion
    (Cartesian product). Non-list fields are left unchanged.

    Expanded rows are only used for relationship matching — they are NOT
    written as node properties. Node MERGE always uses original records
    so list fields stay intact on nodes.

    Args:
        records: Original records from feishu_reader.

    Returns:
        Expanded list of records (may be longer than input).
        Each list field is replaced by a single value per row.
    """
    if not records:
        return records

    # Auto-detect list fields across all records
    expand_fields: set[str] = set()
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, list) and v:
                expand_fields.add(k)

    if not expand_fields:
        return records

    expanded: list[dict] = []
    for rec in records:
        # Find list fields present in this record
        list_fields = [
            (k, v) for k, v in rec.items()
            if k in expand_fields and isinstance(v, list) and v
        ]

        if not list_fields:
            expanded.append(dict(rec))
            continue

        # Expand the first list field, recurse for the rest
        field, values = list_fields[0]
        for val in values:
            new_rec = dict(rec)
            new_rec[field] = val
            expanded.extend(_expand_records([new_rec]))

    return expanded


def build_nodes(
    driver,
    entities_config: dict,
    feishu_data: dict,
) -> dict[str, int]:
    """MERGE entity nodes from Feishu records.

    Uses original (non-expanded) records so multi-select fields are stored
    as lists on nodes. MERGE on key_field ensures idempotency.

    Args:
        driver: Neo4j driver instance.
        entities_config: Entity definitions from config.json (graph-config.entities).
        feishu_data: Records keyed by label.

    Returns:
        dict mapping label -> count of unique nodes.
    """
    counts: dict[str, int] = {}

    for label, cfg in entities_config.items():
        key_field = cfg["key_field"]
        records = feishu_data.get(label, [])
        if not records:
            counts[label] = 0
            continue

        esc_label = _escape(label)

        with driver.session() as session:
            for record in records:
                key_value = record.get(key_field)
                if key_value is None:
                    continue

                other_props = {
                    k: v for k, v in record.items() if k != key_field
                }

                cypher = (
                    f"MERGE (n:`{esc_label}` {{"
                    f"`{_escape(key_field)}`: $key_value}}) "
                    f"SET n += $props"
                )
                session.run(cypher, key_value=key_value, props=other_props)

            # Count unique nodes
            count_result = session.run(
                f"MATCH (n:`{esc_label}`) RETURN count(n) AS cnt"
            )
            counts[label] = int(count_result.single()["cnt"])

    return counts


def build_relationships(
    driver,
    relationships_config: list[dict],
    entities_config: dict,
    feishu_data: dict,
) -> dict[str, int]:
    """Create relationships between nodes based on config matching rules.

    Multi-select fields are automatically expanded before matching, so
    all relationships use the same direct-match logic. No special multi
    handling needed in config or code.

    Supports two matching modes:
      - Direct match: expanded source_field -> target_field (1:1 or N:1)
      - Via match: intermediate table links from and to entities

    Args:
        driver: Neo4j driver instance.
        relationships_config: List of relationship definitions from YAML.
        entities_config: Entity definitions (needed for key_field lookups).
        feishu_data: Records keyed by label or ``via_{table_id}``.

    Returns:
        dict mapping ``"{from_label}-{type}-{to_label}"`` -> count.
    """
    counts: dict[str, int] = {}

    for rel_cfg in relationships_config:
        rel_type = rel_cfg["type"]
        from_label = rel_cfg["from"]
        to_label = rel_cfg["to"]
        tag = f"{from_label}-{rel_type}->{to_label}"

        from_key = entities_config[from_label]["key_field"]
        to_key = entities_config[to_label]["key_field"]

        count = 0

        if "via" in rel_cfg:
            # --- Via match (intermediate table) ---
            via_cfg = rel_cfg["via"]
            via_table_id = via_cfg["table_id"]
            via_from_field = via_cfg["from_field"]
            via_to_field = via_cfg["to_field"]
            via_props_fields = via_cfg.get("properties", [])

            via_records = feishu_data.get(f"via_{via_table_id}", [])

            esc_from = _escape(from_label)
            esc_to = _escape(to_label)
            esc_rel = _escape(rel_type)
            esc_from_key = _escape(from_key)
            esc_to_key = _escape(to_key)

            with driver.session() as session:
                for via_rec in via_records:
                    from_val = via_rec.get(via_from_field)
                    to_val = via_rec.get(via_to_field)
                    if from_val is None or to_val is None:
                        continue

                    props = {
                        k: via_rec[k]
                        for k in via_props_fields
                        if k in via_rec and via_rec[k] is not None
                    }

                    cypher = (
                        f"MATCH (a:`{esc_from}` {{`{esc_from_key}`: $from_val}}) "
                        f"MATCH (b:`{esc_to}` {{`{esc_to_key}`: $to_val}}) "
                        f"MERGE (a)-[r:`{esc_rel}`]->(b) "
                        f"SET r += $props"
                    )
                    session.run(
                        cypher,
                        from_val=from_val,
                        to_val=to_val,
                        props=props,
                    )
                    count += 1

        else:
            # --- Direct match (unified, no multi branch) ---
            match_cfg = rel_cfg["match"]
            source_field = match_cfg["source_field"]
            target_field = match_cfg["target_field"]

            # Expand multi-select fields in from_records
            from_records = _expand_records(feishu_data.get(from_label, []))

            # Build lookup: target_field value -> list of to_key values
            to_records = feishu_data.get(to_label, [])
            to_lookup: dict[str, list[str]] = {}
            for rec in to_records:
                target_val = rec.get(target_field)
                key_val = rec.get(to_key)
                if target_val is None or key_val is None:
                    continue
                # Target side may also have list fields — expand them too
                vals = [target_val] if not isinstance(target_val, list) else target_val
                for v in vals:
                    to_lookup.setdefault(v, []).append(key_val)

            esc_from = _escape(from_label)
            esc_to = _escape(to_label)
            esc_rel = _escape(rel_type)
            esc_from_key = _escape(from_key)
            esc_to_key = _escape(to_key)

            with driver.session() as session:
                for from_rec in from_records:
                    from_key_val = from_rec.get(from_key)
                    if from_key_val is None:
                        continue

                    source_val = from_rec.get(source_field)
                    if source_val is None:
                        continue

                    # source_val is always a single value after expansion
                    matched_to_keys = to_lookup.get(source_val)
                    if not matched_to_keys:
                        continue

                    for to_key_val in matched_to_keys:
                        cypher = (
                            f"MATCH (a:`{esc_from}` {{`{esc_from_key}`: $from_key_val}}) "
                            f"MATCH (b:`{esc_to}` {{`{esc_to_key}`: $to_key_val}}) "
                            f"MERGE (a)-[:`{esc_rel}`]->(b)"
                        )
                        session.run(
                            cypher,
                            from_key_val=from_key_val,
                            to_key_val=to_key_val,
                        )
                        count += 1

        counts[tag] = count

    return counts


def clear_graph(driver) -> None:
    """Delete all nodes and relationships in the database."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
