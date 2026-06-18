"""sync.py — Main orchestrator for GraphRAG sync pipeline."""
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

# scripts/pipeline/sync.py → project root is two levels up
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.join(_PROJECT_ROOT, "graph-config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_env(env_path=None):
    if env_path is None:
        env_path = os.path.join(_PROJECT_ROOT, ".env")
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


def fetch_all_feishu_data(cfg):
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

    # Fetch via tables
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


def download_model(model_path, model_name):
    from sentence_transformers import SentenceTransformer
    abs_path = os.path.abspath(model_path)
    print(f"下载模型 {model_name} -> {abs_path}")
    os.makedirs(abs_path, exist_ok=True)
    model = SentenceTransformer(model_name)
    model.save(abs_path)
    print(f"模型已保存到 {abs_path}")


def main():
    parser = argparse.ArgumentParser(description="GraphRAG sync pipeline")
    parser.add_argument("--only", choices=["fetch", "graph", "embed"], help="Run only one phase")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--force-embed", action="store_true", help="Force regenerate all embeddings")
    parser.add_argument("--download-model", action="store_true", help="Download embedding model")
    args = parser.parse_args()

    load_env()
    cfg = load_config()

    # Resolve paths
    project_dir = _PROJECT_ROOT
    model_path = os.path.join(project_dir, cfg["embedding"]["model_path"])
    dimensions = cfg["embedding"]["dimensions"]

    if args.download_model:
        download_model(model_path, cfg["embedding"]["model"])
        return

    # Check model exists for embed phase
    if args.only in (None, "embed") and not os.path.isdir(model_path):
        print(f"错误：模型路径不存在 {model_path}")
        print("请先运行: python sync.py --download-model")
        sys.exit(1)

    # Phase 1: Fetch
    if args.only in (None, "fetch", "graph"):
        print("\n=== Phase 1: 拉取飞书数据 ===")
        feishu_data = fetch_all_feishu_data(cfg)
        print(f"  共拉取 {len(feishu_data)} 个数据集")
    else:
        feishu_data = {}

    if args.dry_run:
        print("\nDRY RUN: 预览完成，不写入。")
        for label, records in feishu_data.items():
            print(f"  [{label}]: {len(records)} 条")
        return

    # Connect to Neo4j
    uri = cfg["neo4j"]["uri"]
    database = cfg["neo4j"]["database"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        # Phase 2: Build graph
        if args.only in (None, "graph"):
            print("\n=== Phase 2: 构建 Neo4j 图 ===")
            if args.only is None:
                clear_graph(driver)
            print("  创建节点...")
            node_counts = build_nodes(driver, cfg["entities"], feishu_data)
            for label, count in node_counts.items():
                print(f"    [{label}]: {count} 个节点")
            print("  创建关系...")
            rel_counts = build_relationships(driver, cfg["relationships"], cfg["entities"], feishu_data)
            for desc, count in rel_counts.items():
                print(f"    {desc}: {count} 条")

        # Phase 3: Embed
        if args.only in (None, "embed"):
            print("\n=== Phase 3: 向量化 ===")
            print("  生成 search_text...")
            st_counts = generate_search_text(driver, cfg["entities"])
            for label, count in st_counts.items():
                print(f"    [{label}]: {count} 条")
            print("  创建向量索引...")
            indexes = create_vector_indexes(driver, cfg["entities"], dimensions)
            print(f"  共 {len(indexes)} 个向量索引")
            print("  生成 embedding...")
            emb_counts = embed_nodes(driver, cfg["entities"], model_path, dimensions, force=args.force_embed)
            for label, count in emb_counts.items():
                print(f"    [{label}]: {count} 个")

        print("\n✓ 同步完成")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
