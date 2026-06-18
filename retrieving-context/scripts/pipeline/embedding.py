"""
embedding.py — Auto search_text generation, vector index creation,
and node embedding for the GraphRAG pipeline.

Functions:
    generate_search_text(driver, entities_config) -> dict[str, int]
    create_vector_indexes(driver, entities_config, dimensions=512) -> list[str]
    encode_texts(model_path, texts) -> list[list[float]]
    embed_nodes(driver, entities_config, model_path, dimensions=512,
                force=False, batch_size=16) -> dict[str, int]

CLI:
    python embedding.py encode "text" [--model-path PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Internal property names to skip when generating search_text
# ---------------------------------------------------------------------------
_SKIP_PROPS = frozenset({
    "search_text",
    "embedding",
    "embedding_model",
    "embedding_dimensions",
    "embedding_updated_at",
})

# scripts/pipeline/embedding.py → project root is two levels up
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "graph-config.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape(label: str) -> str:
    """Escape a label for Cypher backtick quotes."""
    return label.replace("`", "``")


def _should_vectorize(cfg: dict) -> bool:
    """Return True if the entity config has vector_index enabled (default)."""
    return cfg.get("vector_index", True) is not False


def _load_model_path_from_config() -> str | None:
    """Read embedding.model_path from graph-config.yaml."""
    import yaml

    if not _CONFIG_PATH.exists():
        return None
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("embedding", {}).get("model_path")


def _format_value(value) -> str:
    """Format a property value for search_text concatenation.

    Lists (multi-select fields) are joined with Chinese enumeration
    comma.  Everything else is str()'d.
    """
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_search_text(driver, entities_config: dict) -> dict[str, int]:
    """For each vector-indexed entity, concatenate all non-internal
    properties as ``"字段名：值。"`` and write back to ``n.search_text``.

    Args:
        driver: Neo4j driver instance.
        entities_config: Entity definitions from graph-config.yaml.

    Returns:
        dict mapping label -> count of nodes updated.
    """
    counts: dict[str, int] = {}

    for label, cfg in entities_config.items():
        if not _should_vectorize(cfg):
            continue

        esc_label = _escape(label)
        count = 0

        with driver.session() as session:
            result = session.run(
                f"MATCH (n:`{esc_label}`) "
                f"RETURN properties(n) AS props, elementId(n) AS id"
            )

            for record in result:
                props = record["props"]
                node_id = record["id"]

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

                session.run(
                    f"MATCH (n) WHERE elementId(n) = $id "
                    f"SET n.search_text = $text",
                    id=node_id,
                    text=text,
                )
                count += 1

        counts[label] = count

    return counts


def create_vector_indexes(
    driver,
    entities_config: dict,
    dimensions: int = 512,
) -> list[str]:
    """Create vector indexes for all vector-indexed entities.

    Args:
        driver: Neo4j driver instance.
        entities_config: Entity definitions from graph-config.yaml.
        dimensions: Vector embedding dimensions (default 512).

    Returns:
        List of index names created.
    """
    index_names: list[str] = []

    for label, cfg in entities_config.items():
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

        with driver.session() as session:
            session.run(cypher)

        index_names.append(index_name)

    return index_names


def encode_texts(
    model_path: str,
    texts: list[str],
) -> list[list[float]]:
    """Encode texts to embeddings using a local SentenceTransformer model.

    Args:
        model_path: Local filesystem path to the model directory.
        texts: List of strings to encode.

    Returns:
        List of float arrays (one per input text).
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_path)
    embeddings = model.encode(texts, normalize_embeddings=True)

    # Convert numpy arrays to plain Python lists for JSON serialisation
    return [emb.tolist() for emb in embeddings]


def embed_nodes(
    driver,
    entities_config: dict,
    model_path: str,
    dimensions: int = 512,
    force: bool = False,
    batch_size: int = 16,
) -> dict[str, int]:
    """Embed nodes that have ``search_text`` but no ``embedding`` yet.

    Args:
        driver: Neo4j driver instance.
        entities_config: Entity definitions from graph-config.yaml.
        model_path: Local path to the SentenceTransformer model.
        dimensions: Expected embedding dimensions.
        force: If True, re-embed even nodes that already have embeddings.
        batch_size: Number of nodes to encode per batch.

    Returns:
        dict mapping label -> count of nodes embedded.
    """
    counts: dict[str, int] = {}

    # Load model once for all entities
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_path)

    model_name = Path(model_path).name

    for label, cfg in entities_config.items():
        if not _should_vectorize(cfg):
            continue

        esc_label = _escape(label)
        count = 0

        with driver.session() as session:
            # Collect nodes needing embedding
            if force:
                where = "n.search_text IS NOT NULL"
            else:
                where = "n.search_text IS NOT NULL AND n.embedding IS NULL"

            result = session.run(
                f"MATCH (n:`{esc_label}`) "
                f"WHERE {where} "
                f"RETURN elementId(n) AS id, n.search_text AS text"
            )

            nodes = [(r["id"], r["text"]) for r in result]

        # Process in batches
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            ids = [n[0] for n in batch]
            texts = [n[1] for n in batch]

            embeddings = model.encode(texts, normalize_embeddings=True)

            with driver.session() as session:
                for nid, emb in zip(ids, embeddings):
                    now = datetime.now(timezone.utc).isoformat()
                    session.run(
                        f"MATCH (n) WHERE elementId(n) = $id "
                        f"SET n.embedding = $emb, "
                        f"    n.embedding_model = $model, "
                        f"    n.embedding_dimensions = $dims, "
                        f"    n.embedding_updated_at = datetime($now)",
                        id=nid,
                        emb=emb.tolist(),
                        model=model_name,
                        dims=dimensions,
                        now=now,
                    )
                    count += 1

        counts[label] = count

    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Embedding utilities for GraphRAG pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    enc = sub.add_parser("encode", help="Encode a text string to an embedding")
    enc.add_argument("text", help="Text to encode")
    enc.add_argument(
        "--model-path",
        default=None,
        help="Path to local SentenceTransformer model "
             "(default: read from graph-config.yaml)",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "encode":
        model_path = args.model_path
        if model_path is None:
            model_path = _load_model_path_from_config()
            if model_path is None:
                print(
                    "Error: --model-path not provided and cannot read "
                    "from graph-config.yaml",
                    file=sys.stderr,
                )
                sys.exit(1)
            # Resolve relative to config file location
            resolved = _CONFIG_PATH.parent / model_path
            model_path = str(resolved)

        result = encode_texts(model_path, [args.text])
        print(json.dumps(result[0]))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
