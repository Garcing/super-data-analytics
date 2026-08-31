"""业务知识图谱检索内核：混合召回、图扩展、Cypher 和飞书文档。"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from functools import lru_cache
import re
from typing import Any

from neo4j import GraphDatabase

from sda_mcp.config import load_config
from sda_mcp.errors import ConfigError, DataSourceError, ExternalAPIError, ValidationError
from sda_mcp.feishu import FeishuClient
from sda_mcp.skills.docx_blocks import (
    build_descendants,
    is_text_block,
    normalize_blocks,
    select_subtree,
    update_request,
)

_INTERNAL_PROPS = {
    "search_text", "embedding", "embedding_model", "embedding_dimensions", "embedding_updated_at",
}

# 检索结果 context 每命中、每类邻居标签的保留上限；超限截断并置 truncated。
CONTEXT_NEIGHBOR_LIMIT = 20
DOC_READ_MAX_ATTEMPTS = 3


def _clean_properties(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in (raw or {}).items() if k not in _INTERNAL_PROPS}


def _to_jsonable(value: Any) -> Any:
    """把 Cypher 查询结果递归转成 JSON 安全结构。

    neo4j driver 6.x 的 Node/Relationship 是 Mapping（不再有 ``.properties``
    属性），5.x 同样实现 Mapping 协议，故按 Mapping 统一取属性并清洗内部字段；
    Path 按 nodes/relationships 鸭子判定；neo4j temporal/spatial 标量字符串化
    兜底。否则 ``RETURN n`` 原样穿透，MCP 序列化崩成裸错误。
    """
    if value is None or isinstance(value, (str, bytes, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return _clean_properties({k: _to_jsonable(v) for k, v in value.items()})
    if hasattr(value, "nodes") and hasattr(value, "relationships"):
        return {
            "nodes": [_to_jsonable(n) for n in value.nodes],
            "relationships": [_to_jsonable(r) for r in value.relationships],
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_jsonable(v) for v in value]
    if type(value).__module__.split(".")[0] == "neo4j":
        return str(value)
    return value


def _format_schema_pattern(source: str, rel_type: str, target: str) -> str:
    """把关系模式格式化为可直接参考的 Cypher 片段。"""
    esc = lambda value: value.replace("`", "``")
    return f"(:`{esc(source)}`)-[:`{esc(rel_type)}`]->(:`{esc(target)}`)"


def _build_live_schema(
    property_rows: list[dict[str, Any]],
    constraint_rows: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """把 Neo4j 元数据收敛为大模型写 Cypher 所需的最小结构。"""
    nodes: dict[str, dict[str, Any]] = {}
    for row in property_rows:
        labels = row.get("nodeLabels") or []
        if not labels:
            continue
        label = ":".join(str(item) for item in labels)
        node = nodes.setdefault(label, {"properties": {}})
        property_name = row.get("propertyName")
        if not property_name or property_name in _INTERNAL_PROPS:
            continue
        property_types = [str(item) for item in (row.get("propertyTypes") or [])]
        node["properties"][property_name] = " | ".join(property_types) or "ANY"

    live_labels = set(nodes)
    for row in constraint_rows:
        constraint_type = str(row.get("type") or "")
        if "UNIQUENESS" not in constraint_type and not constraint_type.endswith("KEY"):
            continue
        labels = row.get("labelsOrTypes") or []
        properties = row.get("properties") or []
        if len(labels) != 1 or not properties:
            continue
        label = str(labels[0])
        if label not in live_labels:
            continue
        unique = nodes[label].setdefault("unique", [])
        for property_name in properties:
            if property_name in nodes[label]["properties"] and property_name not in unique:
                unique.append(property_name)

    for node in nodes.values():
        if "unique" in node:
            node["unique"].sort()

    relationships = sorted({
        _format_schema_pattern(
            str(row["sourceLabel"]),
            str(row["relationshipType"]),
            str(row["targetLabel"]),
        )
        for row in relationship_rows
        if row.get("sourceLabel") and row.get("relationshipType") and row.get("targetLabel")
    })
    return {"nodes": nodes, "relationships": relationships}


def schema() -> dict[str, Any]:
    """从 Neo4j 实时读取精简图 schema，不依赖 graph-config。"""
    client = Neo4jClient()
    try:
        cypher_prefix = "CYPHER 25 " if client._supports_vector_search_clause() else ""
        property_rows = client.run_cypher(
            cypher_prefix
            + "CALL db.schema.nodeTypeProperties() "
              "YIELD nodeLabels, propertyName, propertyTypes "
              "RETURN nodeLabels, propertyName, propertyTypes "
              "ORDER BY nodeLabels, propertyName"
        )
        constraint_rows = client.run_cypher(
            "SHOW CONSTRAINTS "
            "YIELD type, labelsOrTypes, properties"
        )
        relationship_rows = client.run_cypher(
            "MATCH (source)-[rel]->(target) "
            "UNWIND labels(source) AS sourceLabel "
            "UNWIND labels(target) AS targetLabel "
            "RETURN DISTINCT sourceLabel, type(rel) AS relationshipType, targetLabel "
            "ORDER BY sourceLabel, relationshipType, targetLabel"
        )
        result = _build_live_schema(property_rows, constraint_rows, relationship_rows)
        if not result["nodes"]:
            raise DataSourceError("Neo4j 图中没有可用 schema，请先执行 sync")
        return result
    except DataSourceError:
        raise
    except Exception as exc:
        raise DataSourceError(f"读取 Neo4j schema 失败：{exc}") from exc
    finally:
        client.close()


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


def _escape_lucene_query(text: str) -> str:
    """转义 Lucene 运算符，同时保留可分词文本。"""
    text = text.replace("&&", r"\&&").replace("||", r"\||")
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/])', r"\\\1", text)


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
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def _session(self):
        return self._driver.session(database=self._database)

    def _supports_vector_search_clause(self) -> bool:
        """判断当前 Neo4j 是否支持 Cypher 25 ``SEARCH``。"""
        cached = getattr(self, "_supports_search_clause_cache", None)
        if cached is not None:
            return cached
        try:
            info = self._driver.get_server_info()
            match = re.search(r"(?:Neo4j/)?(\d{4})\.(\d{1,2})", info.agent or "")
            supported = bool(match and (int(match.group(1)), int(match.group(2))) >= (2026, 1))
        except Exception:
            supported = False
        self._supports_search_clause_cache = supported
        return supported

    def find_vector_index_name(self, label: str) -> str | None:
        indexes = getattr(self, "_vector_index_names_cache", None)
        if indexes is None:
            indexes = {}
            try:
                with self._session() as s:
                    records = list(s.run("SHOW VECTOR INDEXES YIELD name, labelsOrTypes"))
                for rec in records:
                    for indexed_label in rec["labelsOrTypes"] or []:
                        indexes.setdefault(indexed_label, rec["name"])
            except Exception:
                pass
            self._vector_index_names_cache = indexes
        return indexes.get(label)

    def find_fulltext_index_name(self, label: str) -> str | None:
        indexes = getattr(self, "_fulltext_index_names_cache", None)
        if indexes is None:
            indexes = {}
            try:
                with self._session() as s:
                    records = list(s.run(
                        "SHOW FULLTEXT INDEXES YIELD name, labelsOrTypes, properties"
                    ))
                for rec in records:
                    if "search_text" not in (rec["properties"] or []):
                        continue
                    for indexed_label in rec["labelsOrTypes"] or []:
                        indexes.setdefault(indexed_label, rec["name"])
            except Exception:
                pass
            self._fulltext_index_names_cache = indexes
        return indexes.get(label)

    def search_vector_index(self, index_name: str, label: str, embedding: list[float], top_k: int) -> list[dict]:
        esc = label.replace("`", "``")
        if self._supports_vector_search_clause():
            # SEARCH 的索引名必须写成标识符；名称来自 SHOW VECTOR INDEXES，插入前仍需转义。
            esc_index = index_name.replace("`", "``")
            cypher = (
                f"CYPHER 25 MATCH (node:`{esc}`) "
                "SEARCH node IN ("
                f"VECTOR INDEX `{esc_index}` FOR $embedding LIMIT $topK"
                ") SCORE AS score "
                "RETURN elementId(node) AS id, score, properties(node) AS properties "
                "ORDER BY score DESC"
            )
            params = {"topK": top_k, "embedding": embedding}
        else:
            cypher = (
                "CALL db.index.vector.queryNodes($indexName, $topK, $embedding) "
                "YIELD node, score "
                f"WHERE node:`{esc}` "
                "RETURN elementId(node) AS id, score, properties(node) AS properties "
                "ORDER BY score DESC"
            )
            params = {"indexName": index_name, "topK": top_k, "embedding": embedding}
        try:
            with self._session() as s:
                return [{"id": r["id"], "score": r["score"], "properties": dict(r["properties"])}
                        for r in s.run(cypher, **params)]
        except Exception:
            return []

    def search_fulltext_index(
        self, index_name: str, label: str, question: str, top_k: int,
    ) -> list[dict]:
        esc_label = label.replace("`", "``")
        cypher = (
            "CALL db.index.fulltext.queryNodes("
            "$indexName, $question, {limit: $topK}) "
            "YIELD node, score "
            f"WHERE node:`{esc_label}` "
            "RETURN elementId(node) AS id, score, properties(node) AS properties "
            "ORDER BY score DESC"
        )
        try:
            with self._session() as s:
                return [{"id": r["id"], "score": r["score"], "properties": dict(r["properties"])}
                        for r in s.run(
                            cypher,
                            indexName=index_name,
                            question=_escape_lucene_query(question),
                            topK=top_k,
                        )]
        except Exception:
            return []

    def fetch_graph_context_batch(
        self, hits: list[dict[str, Any]], relationships: list[dict],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """按关系方向批量扩展图上下文，限制每个命中每类邻居的数量。

        每个桶为 ``{"items": [...], "total": 邻居总数, "truncated": 是否超限截断}``；
        ``truncated=true`` 时完整邻居应改用 ``retrieve_cypher`` 遍历。
        """
        contexts: dict[str, dict[str, dict[str, Any]]] = {
            hit["id"]: {} for hit in hits
        }
        ids_by_label: dict[str, list[str]] = defaultdict(list)
        for hit in hits:
            ids_by_label[hit["label"]].append(hit["id"])

        def expand(node_ids: list[str], rel_pattern: str, other_label: str, *, self_loop: bool) -> None:
            if not node_ids:
                return
            esc_other = other_label.replace("`", "``")
            self_exclude = " AND elementId(other) <> elementId(n)" if self_loop else ""
            cypher = (
                f"MATCH (n){rel_pattern}(other:`{esc_other}`) "
                f"WHERE elementId(n) IN $nodeIds{self_exclude} "
                "RETURN elementId(n) AS nodeId, properties(other) AS props"
            )
            try:
                with self._session() as s:
                    records = list(s.run(cypher, nodeIds=node_ids))
            except Exception:
                return
            for rec in records:
                bucket = contexts.get(rec["nodeId"])
                if bucket is None:
                    continue
                entry = bucket.get(other_label)
                if entry is None:
                    entry = bucket[other_label] = {
                        "items": [], "total": 0, "truncated": False,
                    }
                entry["total"] += 1
                if len(entry["items"]) < CONTEXT_NEIGHBOR_LIMIT:
                    entry["items"].append(_clean_properties(dict(rec["props"])))
                else:
                    entry["truncated"] = True

        for rel in relationships:
            from_label = rel.get("from")
            to_label = rel.get("to")
            rel_type = (rel.get("type") or "").replace("`", "``")
            if not from_label or not to_label or not rel_type:
                continue
            if from_label == to_label:
                expand(
                    ids_by_label.get(from_label, []),
                    f"-[:`{rel_type}`]-",
                    to_label,
                    self_loop=True,
                )
            else:
                expand(
                    ids_by_label.get(from_label, []),
                    f"-[:`{rel_type}`]->",
                    to_label,
                    self_loop=False,
                )
                expand(
                    ids_by_label.get(to_label, []),
                    f"<-[:`{rel_type}`]-",
                    from_label,
                    self_loop=False,
                )
        return contexts

    def execute(self, cypher: str, **params) -> None:
        """通用写/DDL 执行（MERGE/SET/CREATE/CLEAR）。无返回。"""
        with self._session() as s:
            s.run(cypher, **params)

    def run_cypher(self, statement: str) -> list[dict]:
        with self._session() as s:
            result = s.run(statement)
            return [
                {key: _to_jsonable(rec[key]) for key in rec.keys()}
                for rec in result
            ]


def _fuse_ranked_sources(
    ranked_sources: list[tuple[str, str, float, list[dict[str, Any]]]],
    *,
    rrf_k: int = 60,
) -> list[dict[str, Any]]:
    """用加权 RRF 融合各实体类型的向量、全文和精确命中结果。"""
    fused: dict[str, dict[str, Any]] = {}
    for source_kind, label, weight, hits in ranked_sources:
        for rank, hit in enumerate(hits, start=1):
            item = fused.setdefault(hit["id"], {
                "id": hit["id"],
                "label": label,
                "properties": hit["properties"],
                "fusion_score": 0.0,
                "vector_score": None,
                "fulltext_score": None,
                "exact_match": None,
                "vector_rank": None,
                "lexical_rank": None,
                "exact_rank": None,
                "matched_sources": 0,
            })
            item["fusion_score"] += weight / (rrf_k + rank)
            item["matched_sources"] += 1
            if source_kind == "vector":
                item["vector_score"] = hit["score"]
                item["vector_rank"] = rank
            elif source_kind == "fulltext":
                item["fulltext_score"] = hit["score"]
                item["lexical_rank"] = rank
            else:
                item["exact_match"] = hit.get("exact_match")
                item["exact_rank"] = rank

    def sort_key(item: dict[str, Any]):
        ranks = [r for r in (
            item["vector_rank"], item["lexical_rank"], item["exact_rank"],
        ) if r is not None]
        return (
            item["fusion_score"],
            item["matched_sources"],
            -(min(ranks) if ranks else 10**9),
            item["vector_score"] or 0.0,
        )

    return sorted(fused.values(), key=sort_key, reverse=True)


def _exact_property_hits(
    question: str, hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按问题中出现的受治理 ID、名称和别名对候选排序。

    不检查定义等长文本，避免因提到其他实体而获得错误加权。
    """
    normalized_question = question.casefold()
    ranked: list[tuple[int, dict[str, Any], str]] = []
    seen: set[str] = set()
    for hit in hits:
        if hit["id"] in seen:
            continue
        seen.add(hit["id"])
        matches: list[str] = []
        for key, raw_value in _clean_properties(hit.get("properties", {})).items():
            key_folded = key.casefold()
            is_identity_field = (
                key.endswith("ID")
                or "名称" in key
                or "别名" in key
                or key_folded.endswith("id")
                or key_folded.endswith("name")
                or "alias" in key_folded
            )
            if not is_identity_field:
                continue
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for value in values:
                if not isinstance(value, str):
                    continue
                value = value.strip()
                if 2 <= len(value) <= 80 and value.casefold() in normalized_question:
                    matches.append(value)
        if matches:
            best = max(matches, key=len)
            ranked.append((len(best), hit, best))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [{**hit, "exact_match": matched, "score": float(length)}
            for length, hit, matched in ranked]


def search(
    question: str,
    top_k: int = 5,
    targets: list[str] | None = None,
    strategy: str = "hybrid",
) -> dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        raise ValidationError("question 不能为空")
    if strategy not in ("vector", "hybrid"):
        raise ValidationError("strategy 必须是 vector|hybrid")
    gc = load_config().get("graph-config", {})
    entities = gc.get("entities") or {}
    relationships = gc.get("relationships") or []
    target_labels = [label for label in entities if not targets or label in targets]
    embedding_vec = embed(question)
    client = Neo4jClient()
    try:
        ranked_sources: list[tuple[str, str, float, list[dict[str, Any]]]] = []
        vector_results: list[dict[str, Any]] = []
        source_k = top_k * 2 if strategy == "hybrid" else top_k
        for label in target_labels:
            index_name = client.find_vector_index_name(label)
            if not index_name:
                continue
            hits = client.search_vector_index(index_name, label, embedding_vec, source_k)
            for hit in hits:
                hit["label"] = label
            if strategy == "vector":
                vector_results.extend(hits)
            else:
                ranked_sources.append(("vector", label, 1.0, hits))
                fulltext_name = client.find_fulltext_index_name(label)
                if fulltext_name:
                    lexical_hits = client.search_fulltext_index(
                        fulltext_name, label, question, source_k,
                    )
                    ranked_sources.append(("fulltext", label, 1.0, lexical_hits))
                exact_hits = _exact_property_hits(question, hits + (lexical_hits if fulltext_name else []))
                if exact_hits:
                    ranked_sources.append(("exact", label, 1.2, exact_hits))

        if strategy == "vector":
            candidates = sorted(vector_results, key=lambda x: x["score"], reverse=True)
        else:
            candidates = _fuse_ranked_sources(ranked_sources)[:top_k]

        contexts = (
            client.fetch_graph_context_batch(candidates, relationships)
            if relationships and candidates else {}
        )
        results = []
        for hit in candidates:
            result = {
                "label": hit["label"],
                # score 保持表示向量相似度；仅由全文召回的结果记为 0。
                "score": hit.get("vector_score", hit.get("score")) or 0.0,
                "properties": _clean_properties(dict(hit["properties"])),
                "context": contexts.get(hit["id"], {}),
            }
            if strategy == "hybrid":
                result["retrieval"] = {
                    "strategy": "hybrid_rrf",
                    "fusion_score": hit["fusion_score"],
                    "vector_score": hit["vector_score"],
                    "fulltext_score": hit["fulltext_score"],
                    "exact_match": hit["exact_match"],
                    "vector_rank": hit["vector_rank"],
                    "lexical_rank": hit["lexical_rank"],
                    "exact_rank": hit["exact_rank"],
                }
            results.append(result)
        return {"question": question, "strategy": strategy, "results": results}
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


def _document_revision(doc_id: str, document: dict[str, Any]) -> int:
    revision_id = document.get("revision_id")
    if not isinstance(revision_id, int):
        raise ExternalAPIError(f"飞书文档 {doc_id} 元数据响应缺 revision_id")
    return revision_id


def _read_latest_consistent(
    client: FeishuClient, doc_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """读取 latest blocks，并用单调 revision 的前后元数据检查排除混合快照。"""
    warnings: list[str] = []
    for attempt in range(1, DOC_READ_MAX_ATTEMPTS + 1):
        before = client.get_document(doc_id)
        before_revision = _document_revision(doc_id, before)
        raw_blocks = client.list_blocks(doc_id, document_revision_id=-1)
        after = client.get_document(doc_id)
        after_revision = _document_revision(doc_id, after)
        if before_revision == after_revision:
            return after, raw_blocks, warnings
        warnings.append(
            f"读取 blocks 期间文档 revision 从 {before_revision} 变为 {after_revision}；"
            f"已丢弃该结果并重试（{attempt}/{DOC_READ_MAX_ATTEMPTS}）"
        )
    raise ExternalAPIError(
        f"飞书文档 {doc_id} 在 {DOC_READ_MAX_ATTEMPTS} 次读取期间持续发生变化；请稍后重试"
    )


def doc(
    doc_id: str, root_block_id: str | None = None, max_depth: int = -1,
    detail: str = "compact",
) -> dict[str, Any]:
    """读取飞书 docx 为带 revision 与父子 ID 的结构化块快照。"""
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValidationError("doc 不能为空")
    if max_depth < -1:
        raise ValidationError("max_depth 必须为 -1 或非负整数")
    if detail not in {"compact", "full"}:
        raise ValidationError("detail 必须是 compact 或 full")
    client = FeishuClient()
    document, raw_blocks, consistency_warnings = _read_latest_consistent(client, doc_id)
    revision_id = _document_revision(doc_id, document)
    page = next((block for block in raw_blocks if block.get("block_type") == 1), None)
    if page is None or not page.get("block_id"):
        raise ExternalAPIError(f"飞书文档 {doc_id} 块响应缺 page 根块")

    selected_root = root_block_id or page["block_id"]
    selected, traversal_warnings = select_subtree(raw_blocks, selected_root, max_depth)
    blocks, normalization_warnings = normalize_blocks(selected, detail=detail)
    return {
        "document_id": document.get("document_id") or doc_id,
        "title": document.get("title") or "",
        "revision_id": revision_id,
        "detail": detail,
        "root_block_id": selected_root,
        "blocks": blocks,
        "total_blocks": len(raw_blocks),
        "warnings": consistency_warnings + traversal_warnings + normalization_warnings,
    }


def update_doc(
    doc_id: str, expected_revision_id: int, operations: list[dict[str, Any]],
) -> dict[str, Any]:
    """在读取时的 revision 上执行一次批量文本更新或一个结构变更。"""
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValidationError("doc 不能为空")
    if not isinstance(expected_revision_id, int) or expected_revision_id < 0:
        raise ValidationError("expected_revision_id 必须是非负整数")
    if not isinstance(operations, list) or not operations:
        raise ValidationError("operations 不能为空")
    if len(operations) > 200:
        raise ValidationError("operations 一次最多 200 项")
    if any(not isinstance(operation, dict) for operation in operations):
        raise ValidationError("operations 每一项都必须是对象")

    client = FeishuClient()
    current_document = client.get_document(doc_id)
    current_revision_id = current_document.get("revision_id")
    if not isinstance(current_revision_id, int):
        raise ExternalAPIError(f"飞书文档 {doc_id} 元数据响应缺 revision_id")
    if current_revision_id != expected_revision_id:
        raise ValidationError(
            f"文档 revision 冲突：读取时为 {expected_revision_id}，当前为 {current_revision_id}；"
            "请重新调用 retrieve_doc_read 并基于最新块重新生成操作"
        )
    raw_blocks = client.list_blocks(doc_id, document_revision_id=-1)
    verified_document = client.get_document(doc_id)
    verified_revision_id = _document_revision(doc_id, verified_document)
    if verified_revision_id != expected_revision_id:
        raise ValidationError(
            f"文档 revision 冲突：读取时为 {expected_revision_id}，当前为 {verified_revision_id}；"
            "请重新调用 retrieve_doc_read 并基于最新块重新生成操作"
        )
    by_id = {block.get("block_id"): block for block in raw_blocks}
    if not raw_blocks:
        raise ExternalAPIError(f"飞书文档 {doc_id} 在 revision={expected_revision_id} 未返回块")

    kinds = [operation.get("op") if isinstance(operation, dict) else None
             for operation in operations]
    text_ops = {"replace_text", "replace_elements"}
    structural = [kind for kind in kinds if kind not in text_ops]
    if structural and len(operations) != 1:
        raise ValidationError("insert_subtree/delete_children 必须单独调用，不能与其他操作混用")

    affected_ids: list[str] = []
    block_id_relations: list[dict[str, Any]] = []
    if not structural:
        requests: list[dict[str, Any]] = []
        seen_block_ids: set[str] = set()
        for operation in operations:
            block_id = operation.get("block_id")
            if block_id in seen_block_ids:
                raise ValidationError(f"同一批次不能重复更新 block_id={block_id}")
            seen_block_ids.add(block_id)
            block = by_id.get(block_id)
            if block is None:
                raise ValidationError(f"文档中不存在 block_id={block_id}")
            if not is_text_block(block.get("block_type")):
                raise ValidationError(
                    f"block_id={block_id} 的类型 {block.get('block_type')} 不是可更新文本块"
                )
            requests.append(update_request(operation))
            affected_ids.append(block_id)
        response = client.batch_update_blocks(doc_id, expected_revision_id, requests)
    else:
        operation = operations[0]
        op = operation.get("op")
        parent_block_id = operation.get("parent_block_id")
        parent = by_id.get(parent_block_id)
        if parent is None:
            raise ValidationError(f"文档中不存在 parent_block_id={parent_block_id}")
        children = list(parent.get("children") or [])
        if op == "insert_subtree":
            index = operation.get("index")
            if not isinstance(index, int) or index < 0 or index > len(children):
                raise ValidationError(
                    f"insert_subtree.index 必须位于 0..{len(children)}（当前父块 children 数）"
                )
            root_ids, descendants = build_descendants(operation)
            response = client.insert_descendants(
                doc_id,
                descendants,
                root_ids,
                parent_block_id=parent_block_id,
                revision_id=expected_revision_id,
                index=index,
            )
        elif op == "delete_children":
            start = operation.get("start_index")
            end = operation.get("end_index")
            if (not isinstance(start, int) or not isinstance(end, int)
                    or start < 0 or end <= start or end > len(children)):
                raise ValidationError(
                    f"delete_children 必须满足 0 <= start_index < end_index <= {len(children)}"
                )
            affected_ids = children[start:end]
            response = client.delete_children(
                doc_id, parent_block_id, expected_revision_id, start, end,
            )
        else:
            raise ValidationError(f"不支持的文档操作 {op}")

    payload = response.get("data") or {}
    revision_id = payload.get("document_revision_id")
    if not isinstance(revision_id, int):
        raise ExternalAPIError("飞书文档更新响应缺 document_revision_id")
    block_id_relations = payload.get("block_id_relations") or []
    if block_id_relations:
        affected_ids = [relation.get("block_id") for relation in block_id_relations
                        if relation.get("block_id")]
    elif not affected_ids:
        affected_ids = [block.get("block_id") for block in payload.get("children") or []
                        if block.get("block_id")]
    return {
        "updated": True,
        "document_id": doc_id,
        "previous_revision_id": expected_revision_id,
        "revision_id": revision_id,
        "affected_block_ids": affected_ids,
        "block_id_relations": block_id_relations,
        "warnings": [],
    }
