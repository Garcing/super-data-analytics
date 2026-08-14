"""GraphRAG sync 内核：飞书多维表 → Neo4j 图 → fastembed(ONNX) 向量。

同步侧和查询侧共用 Fastembed 模型，确保写入向量与查询向量一致。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sda_mcp.config import get_env, load_config
from sda_mcp.errors import ConfigError, ValidationError
from sda_mcp.feishu import FeishuClient
from sda_mcp.feishu import (_F_TEXT, _F_NUMBER, _F_SINGLE_SELECT,
                            _F_MULTI_SELECT, _F_DATE, _F_CHECKBOX, _F_USER,
                            _F_URL, _F_ATTACHMENT, _F_SINGLE_LINK, _F_LOOKUP, _F_FORMULA,
                            _F_DUPLEX_LINK, _F_LOCATION, _F_GROUP_CHAT,
                            _F_CREATED_TIME, _F_MODIFIED_TIME, _F_CREATED_USER,
                            _F_MODIFIED_USER)
from sda_mcp.skills.retrieving_context import Neo4jClient

_SKIP_PROPS = frozenset({"search_text", "embedding", "embedding_model",
                         "embedding_dimensions", "embedding_updated_at"})


def _escape(label: str) -> str:
    """转义 Cypher 反引号标识符。"""
    return label.replace("`", "``")


def _should_vectorize(cfg: dict) -> bool:
    """判断实体是否参与检索；vector_index 默认为 True。"""
    return (cfg or {}).get("vector_index", True) is not False


def _format_value(value) -> str:
    """把属性值格式化为 search_text 片段。"""
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value)


# ---------- 阶段 1：读取飞书多维表并简化字段值 ----------

def fetch_table_fields(app_token: str, table_id: str) -> list[dict]:
    """把飞书字段定义转换为同步所需的描述符。

    每项含：name/type/id、ui_type、options(Select 选项 [{id,name}])、
    formula_data_type（公式/lookup【结果】data_type int，分派用，见下）。
    """
    raw = FeishuClient().list_bitable_fields(app_token, table_id)
    out: list[dict] = []
    for f in raw:
        prop = f.get("property") or {}
        result = (prop.get("type") or {}) if isinstance(prop, dict) else {}
        out.append({
            "name": f.get("field_name"),
            "type": f.get("type"),
            "id": f.get("field_id"),
            "ui_type": f.get("ui_type"),
            "options": [{"id": o.get("id"), "name": o.get("name")}
                        for o in (prop.get("options") or [])],
            # 公式结果 data_type（int）：与字段类型常量同构（1=Text/2=Number/3=Single/5=Date…），
            # 比 ui_type 字符串更稳——真实 base 里设过格式后 ui_type 可能缺失，data_type 始终在。
            "formula_data_type": result.get("data_type"),
        })
    return out


def _join_text(runs: Any) -> Any:
    """text/公式(文本)/lookup(文本)/url 值 → 拼接字符串；空→None。

    支持形态：纯串（含 \\n 多行）、单段 dict（{text,...}，如 url {text,link}）、
    片段数组 [{text,...}]（多段/多行，逐段拼接，内嵌 \\n 保留）。
    """
    if isinstance(runs, str):
        return runs.strip() or None
    if isinstance(runs, dict):
        return (runs.get("text") or "").strip() or None
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


def _resolve_opt(oid: Any, opt_map: dict[str, str] | None) -> str | None:
    """选项 ID → 选项名。oid 已是名字串则原样返回；dict 取 text/name；未知 ID 返回 None。"""
    if isinstance(oid, dict):
        return _opt_to_str(oid)
    if isinstance(oid, str):
        oid = oid.strip()
        if not oid:
            return None
        return (opt_map or {}).get(oid) or oid  # optId→name；若 opt_map 无则原样（已是名字）
    return None


# 暂不支持的字段类型（值结构复杂、语义层用不到）：返回简短提示给 agent，不做清洗。
# 见官方《多维表格记录数据结构》：人员/附件/群组/位置/系统时间/关联 等。
_UNSUPPORTED: dict[int, str] = {
    _F_USER: "人员", _F_CREATED_USER: "创建人", _F_MODIFIED_USER: "修改人",
    _F_ATTACHMENT: "附件", _F_LOCATION: "地理位置", _F_GROUP_CHAT: "群组",
    _F_CREATED_TIME: "创建时间", _F_MODIFIED_TIME: "更新时间",
    _F_SINGLE_LINK: "单向关联", _F_DUPLEX_LINK: "双向关联",
}


def _to_number(value: Any) -> Any:
    """Number 字段开放平台返回【字符串】（"12.5"/"8"），公式数字返回真 int/float。
    统一规整：整数→int，小数→float，非数字串→原样。bool 不当数字。
    公式经 search 接口以 {type,value} 包装返回时，value 是单元素列表 [n]，这里解开。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, list) and len(value) == 1:  # 包装形态 [n]
        value = value[0]
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            f = float(s)
        except ValueError:
            return s  # 非数字串原样保留
        return int(f) if f.is_integer() else f
    return value


_CN_TZ = timezone(timedelta(hours=8))  # 业务数据均中国时区；ms 时间戳按 +8 显示


def _format_date_value(value: Any) -> str | None:
    """日期值（ms 毫秒时间戳）→ 'YYYY-MM-DD HH:MM:SS'（+8 时区）。

    POST /records/search 接口下，datetime 字段与所有公式日期（含 EDATE/TODAY）统一返回
    ms 毫秒时间戳。值可能是裸 int，或单元素列表 [ms]（公式 {type,value} 包装解包后）。
    旧 GET /records 接口对 TODAY()/EDATE() 曾返回 Excel 日序号，该接口已下架，不再兼容。
    """
    v = value[0] if isinstance(value, list) and value else value
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return datetime.fromtimestamp(v / 1000, tz=_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _simplify_formula(value: Any, data_type: int | None,
                      opt_map: dict[str, str] | None) -> Any:
    """公式(20)/查找引用(19) → 按【结果】data_type(int) 分派。

    data_type 与字段类型常量同构（官方文档：1=Text/2=Number/3=Single/4=Multi/
    5=DateTime/7=Checkbox/...）。公式 select 返回选项 ID/名字，与存储 select 形态不同，
    用 opt_map 反查。

    【值形态】当前 POST /records/search 接口返回 {type, value:[...]} 包装（官方文档示例
    即此形态），下方先解包再分派——这是主路径。同时容忍【裸值】（旧 GET /records 接口的
    返回形态）：裸值不触发解包 if，直接进下方分派。保留裸值分支作防御，因飞书接口形态多次
    变动，webhook/单条 get/未来接口仍可能返回裸值。两种形态在此汇流到同一分派逻辑。
    """
    # 解包 {type:int, value:list}：search 接口的标准形态（主路径）。
    # 裸值（旧 GET /records）不是 dict 或无 int 型 type → 不触发，原样进下方分派。
    # 三个条件缺一不可，避免误拆 url 的 {text,link}、location 的 {full_address} 等 dict。
    if isinstance(value, dict) and isinstance(value.get("type"), int) and "value" in value:
        data_type = value.get("type") or data_type
        value = value.get("value")
    if value is None:
        return None
    dt = data_type or 0
    if dt in (_F_FORMULA, _F_LOOKUP, 19, 20):
        # 结果类型又是公式/lookup（罕见嵌套）→ 文本降级，避免无限递归
        return _join_text(value)
    # 公式 select/multi 返回选项 ID 列表，与存储 select（名字串）形态不同 → 反查
    if dt in (_F_SINGLE_SELECT, _F_MULTI_SELECT):
        ids = value if isinstance(value, list) else [value]
        names = [n for n in (_resolve_opt(i, opt_map) for i in ids) if n]
        if not names:
            return None
        return names[0] if dt == _F_SINGLE_SELECT else names
    # 其余结果类型与存储字段值同构 → 复用存储分派
    return _simplify_value(dt, value, opt_map=opt_map)


def _simplify_value(field_type: int, value: Any, *,
                    opt_map: dict[str, str] | None = None) -> Any:
    """开放平台记录值 → graph 用的简化形式（Neo4j 原生类型：str/int/float/bool/list[str]）。

    存储字段按 type 分派；公式/lookup 由 _simplify_formula 按结果 data_type 路由进来复用本函数。
    语义层用不到的复杂类型（人员/附件/群组/位置/系统时间/关联，见 _UNSUPPORTED）
    不做清洗，返回 "（X字段，暂不支持取值）" 提示给 agent。
    """
    if value is None:
        return None
    if field_type in (_F_FORMULA, _F_LOOKUP):
        return _simplify_formula(value, None, opt_map)  # storage 不会到这；防御
    if field_type == _F_TEXT:
        return _join_text(value)
    if field_type == _F_NUMBER:
        return _to_number(value)
    if field_type == _F_SINGLE_SELECT:
        return _opt_to_str(value)
    if field_type == _F_MULTI_SELECT:
        if isinstance(value, list):
            out = [n for n in (_opt_to_str(v) for v in value) if n is not None]
            return out or None
        v = _opt_to_str(value)
        return [v] if v is not None else None
    if field_type == _F_DATE:
        return _format_date_value(value)
    if field_type == _F_CHECKBOX:
        if isinstance(value, list) and len(value) == 1:  # 公式包装形态 [bool]
            value = value[0]
        return value  # bool 原样（Neo4j 原生支持）
    if field_type == _F_URL:
        return _join_text(value)
    if field_type in _UNSUPPORTED:
        return f"（{_UNSUPPORTED[field_type]}字段，暂不支持取值）"
    if isinstance(value, str):
        return value.strip() or None  # 电话(13)/自动编号(1005) 等本身就是串，走这里
    # 兜底：未识别类型若返回结构化 dict/片段数组，也拍平成可读串，避免写坏 Neo4j（Map 类型错）。
    if isinstance(value, dict):
        return _join_text(value)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return _join_text(value)
    return value


def fetch_table_records(app_token: str, table_id: str, fields: list[dict] | None = None) -> list[dict]:
    """开放平台记录 → [{字段名: 简化值}, ...]，过滤 None/空串/空列表。"""
    if fields is None:
        fields = fetch_table_fields(app_token, table_id)
    # 表级 optId→name 映射：覆盖所有 select 字段的选项，供公式返回选项 ID 时反查。
    opt_map: dict[str, str] = {}
    for f in fields:
        for o in f.get("options") or []:
            if o.get("id") and o.get("name"):
                opt_map[o["id"]] = o["name"]
    items = FeishuClient().list_bitable_records(app_token, table_id)
    records: list[dict] = []
    for item in items:
        raw_fields = item.get("fields") or {}
        rec: dict = {}
        for f in fields:
            name = f["name"]
            if name in raw_fields:
                ftype = f["type"]
                if ftype in (_F_FORMULA, _F_LOOKUP):
                    # 公式/lookup：按结果 data_type 分派（_simplify_formula 内自行处理）
                    val = _simplify_formula(raw_fields[name], f.get("formula_data_type"), opt_map)
                else:
                    val = _simplify_value(ftype, raw_fields[name], opt_map=opt_map)
                if val is not None and val != "" and val != []:
                    rec[name] = val
        records.append(rec)
    return records


def _fetch_all_feishu(gc: dict) -> dict[str, list[dict]]:
    """拉所有 entity 多维表记录。"""
    app_token = get_env("FEISHU_GRAPH_BITABLE_APP_TOKEN")["FEISHU_GRAPH_BITABLE_APP_TOKEN"]
    data: dict[str, list[dict]] = {}
    for label, cfg in (gc.get("entities") or {}).items():
        tid = cfg["table_id"]
        fields = fetch_table_fields(app_token, tid)
        data[label] = fetch_table_records(app_token, tid, fields)
    return data


# ---------- 阶段 2：构建 Neo4j 节点和关系 ----------

def _clear_graph(client: Neo4jClient) -> None:
    """清空当前数据库中的图数据。"""
    client.execute("MATCH (n) DETACH DELETE n")


def _build_nodes(client: Neo4jClient, entities: dict, feishu_data: dict) -> dict[str, int]:
    """按 key_field 幂等写入实体节点。"""
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
    """按 match 字段直连建边：from 实体的 source_field 值（含列表）匹配 to 实体的
    target_field 值。"""
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


# ---------- 阶段 3：生成检索文本、索引和向量 ----------

def _generate_search_text(client: Neo4jClient, entities: dict) -> dict[str, int]:
    """把节点属性拼成“字段名：值。”并写入 search_text。"""
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
    """为参与检索的实体创建 cosine 向量索引。"""
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


def _create_fulltext_indexes(client: Neo4jClient, entities: dict) -> list[str]:
    """按实体类型为 search_text 创建 CJK 全文索引。"""
    index_names: list[str] = []
    for label, cfg in entities.items():
        if not _should_vectorize(cfg):
            continue
        index_name = f"{label}_search_text_index"
        client.execute(
            f"CREATE FULLTEXT INDEX `{_escape(index_name)}` IF NOT EXISTS "
            f"FOR (n:`{_escape(label)}`) ON EACH [n.search_text] "
            "OPTIONS {indexConfig: {`fulltext.analyzer`: 'cjk'}}"
        )
        index_names.append(index_name)
    return index_names


def _embed_nodes(client: Neo4jClient, entities: dict, dimensions: int, force: bool) -> dict[str, int]:
    """批量生成 L2 归一化向量，并写入模型、维度和更新时间。"""
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
    Returns: 各阶段计数 {fetch:{...}, nodes:{...}, relationships:{...},
    search_text:{...}, indexes:n, fulltext_indexes:n, embed:{...}}。
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
            result["fulltext_indexes"] = len(_create_fulltext_indexes(client, gc["entities"]))
            result["embed"] = _embed_nodes(client, gc["entities"], dimensions, force_embed)
    finally:
        client.close()
    return result
