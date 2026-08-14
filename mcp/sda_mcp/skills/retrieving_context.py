"""retrieving_context 内核：GraphRAG 向量检索 + 图扩展 + Cypher + 飞书文档，
从原 retrieve.js 移植为纯 Python。embedding 用 fastembed(ONNX) in-process。
去 CLI/三态/{ok} 信封；失败抛 SkillError。行为对齐 retrieving-context/scripts/retrieve.js。
"""
from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from neo4j import GraphDatabase

from sda_mcp.config import load_config
from sda_mcp.errors import ConfigError, DataSourceError, ValidationError
from sda_mcp.feishu import FeishuClient

_INTERNAL_PROPS = {
    "search_text", "embedding", "embedding_model", "embedding_dimensions", "embedding_updated_at",
}


def _clean_properties(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in (raw or {}).items() if k not in _INTERNAL_PROPS}


def _build_schema(gc: dict[str, Any]) -> dict[str, Any]:
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
        relationships.append(out)
    return {"embedding": gc.get("embedding", {}), "entities": entities, "relationships": relationships}


def schema() -> dict[str, Any]:
    gc = load_config().get("graph-config", {})
    return _build_schema(gc)


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

    @lru_cache(maxsize=1)
    def _supports_vector_search_clause(self) -> bool:
        """Return whether the connected server supports Cypher 25 ``SEARCH``.

        ``db.index.vector.queryNodes`` is deprecated from Neo4j 2026.04.  The
        replacement was introduced in 2026.01 and is Cypher-25-only.  Keep the
        procedure fallback for Neo4j 5.x / 2025.x deployments so the MCP image
        remains backwards compatible.
        """
        try:
            info = self._driver.get_server_info()
            match = re.search(r"(?:Neo4j/)?(\d{4})\.(\d{1,2})", info.agent or "")
            return bool(match and (int(match.group(1)), int(match.group(2))) >= (2026, 1))
        except Exception:
            return False

    def find_vector_index_name(self, label: str) -> str | None:
        with self._session() as s:
            try:
                for rec in s.run("SHOW VECTOR INDEXES YIELD name, labelsOrTypes"):
                    labels = rec["labelsOrTypes"]
                    if labels and label in labels:
                        return rec["name"]
            except Exception:
                return None
        return None

    def search_vector_index(self, index_name: str, label: str, embedding: list[float], top_k: int) -> list[dict]:
        esc = label.replace("`", "``")
        if self._supports_vector_search_clause():
            # SEARCH requires the index name to be an identifier, not a
            # parameter.  It comes from SHOW VECTOR INDEXES; still escape it as
            # a Cypher identifier before interpolation.
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

    def fetch_graph_context(self, label: str, node_id: str, relationships: list[dict]) -> dict:
        """Port of retrieve.js fetchGraphContext (402-485). 沿库里已有边扩展，
        不再读 match / source_field。失败按 per-rel continue。"""
        context: dict[str, Any] = {}

        relevant = [rel for rel in relationships if rel.get("from") == label or rel.get("to") == label]

        for rel in relevant:
            try:
                is_from = rel.get("from") == label
                is_to = rel.get("to") == label
                other_label = rel.get("to") if is_from else rel.get("from")
                if not other_label:
                    continue

                esc_other = other_label.replace("`", "``")
                esc_rel_type = (rel.get("type") or "").replace("`", "``")

                # 自环走无向；否则按 from/to 判方向
                if is_from and is_to:
                    rel_pattern = f"-[:`{esc_rel_type}`]-"
                elif is_from:
                    rel_pattern = f"-[:`{esc_rel_type}`]->"
                else:
                    rel_pattern = f"<-[:`{esc_rel_type}`]-"

                # 自环时排除起点自身
                self_exclude = " AND elementId(other) <> $nodeId" if other_label == label else ""

                cypher = (
                    f"MATCH (n){rel_pattern}(other:`{esc_other}`) "
                    f"WHERE elementId(n) = $nodeId{self_exclude} "
                    "RETURN properties(other) AS props "
                    "LIMIT 20"
                )

                with self._session() as s:
                    records = list(s.run(cypher, nodeId=node_id))

                if not records:
                    continue

                context.setdefault(other_label, [])
                for rec in records:
                    props = _clean_properties(dict(rec["props"]))
                    context[other_label].append(props)
            except Exception:
                # 对齐 retrieve.js：单条关系失败不影响其余扩展
                continue

        return context

    def execute(self, cypher: str, **params) -> None:
        """通用写/DDL 执行（MERGE/SET/CREATE/CLEAR）。无返回。"""
        with self._session() as s:
            s.run(cypher, **params)

    def run_cypher(self, statement: str) -> list[dict]:
        with self._session() as s:
            result = s.run(statement)
            rows = []
            for rec in result:
                obj = {}
                for key in rec.keys():
                    val = rec[key]
                    if hasattr(val, "properties"):
                        val = _clean_properties(dict(val.properties))
                    elif isinstance(val, list):
                        val = [_clean_properties(dict(v.properties)) if hasattr(v, "properties") else v for v in val]
                    obj[key] = val
                rows.append(obj)
            return rows


def search(question: str, top_k: int = 5, targets: list[str] | None = None) -> dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        raise ValidationError("question 不能为空")
    gc = load_config().get("graph-config", {})
    entities = gc.get("entities") or {}
    relationships = gc.get("relationships") or []
    target_labels = [label for label, c in entities.items()
                     if c.get("vector_index", True) and (not targets or label in targets)]
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
        all_results.sort(key=lambda x: x["score"], reverse=True)
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


def doc(doc_id: str) -> dict[str, Any]:
    """读取飞书 docx 文档为 markdown。"""
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValidationError("doc 不能为空")
    content = FeishuClient().get_doc_markdown(doc_id)
    return {"content": content, "document_id": doc_id}


def update_doc(doc_id: str, content: str) -> dict[str, Any]:
    """覆盖写入飞书 docx 正文为 markdown（先清空正文块再重灌）。

    用于更新语义层「报告模板」实体链接的模板文档正文——模板元数据在多维表，
    正文在 docx，本函数只改正文，不碰多维表 / graph-config。
    """
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValidationError("doc 不能为空")
    if not isinstance(content, str) or not content:
        raise ValidationError("content 不能为空")
    client = FeishuClient()
    client.delete_all_children(doc_id)
    blocks, children_id = client.convert_markdown_to_blocks(content)
    if blocks:
        client.insert_descendants(doc_id, blocks, children_id)
    return {"updated": True, "document_id": doc_id}
