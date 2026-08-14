"""检索质量回归测试。

算法单测默认执行；连接真实 Neo4j 的 gold set 测试仅在
``SDA_INTEGRATION=1`` 时执行，避免日常单测依赖外部服务。
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any, Callable

import pytest

from sda_mcp.skills.retrieving_context import search


GOLD_SET = Path(__file__).with_name("retrieval_gold.json")


def _matches(result: dict[str, Any], expected: dict[str, str]) -> bool:
    return (
        result.get("label") == expected["label"]
        and result.get("properties", {}).get(expected["key_field"]) == expected["value"]
    )


def find_first_relevant_rank(
    results: list[dict[str, Any]], expected: list[dict[str, str]],
) -> int | None:
    """返回第一个目标实体的一基排名，未命中则返回 None。"""
    for rank, result in enumerate(results, start=1):
        if any(_matches(result, item) for item in expected):
            return rank
    return None


def percentile(values: list[float], percentile_value: float) -> float:
    """按 nearest-rank 计算小样本百分位数。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile_value * len(ordered)))
    return ordered[rank - 1]


def evaluate_cases(
    cases: list[dict[str, Any]],
    search_fn: Callable[..., dict[str, Any]] = search,
    *,
    source_top_k: int = 10,
    metric_k: int = 5,
    strategy: str = "vector",
) -> dict[str, Any]:
    """用固定问题集评估实体检索，不调用 LLM，也不修改 Neo4j。"""
    if source_top_k < metric_k:
        raise ValueError("source_top_k 必须大于等于 metric_k")
    if not cases:
        raise ValueError("gold set 不能为空")

    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    for case in cases:
        started = perf_counter()
        response = search_fn(
            case["question"],
            top_k=source_top_k,
            targets=case.get("targets"),
            strategy=strategy,
        )
        latency_ms = (perf_counter() - started) * 1000
        latencies.append(latency_ms)
        rank = find_first_relevant_rank(response.get("results", []), case["expected"])
        details.append({
            "id": case["id"],
            "rank": rank,
            "hit_at_1": rank == 1,
            f"hit_at_{metric_k}": rank is not None and rank <= metric_k,
            f"reciprocal_rank_at_{metric_k}": (
                1.0 / rank if rank is not None and rank <= metric_k else 0.0
            ),
            "latency_ms": round(latency_ms, 2),
        })

    total = len(details)
    return {
        "cases": details,
        "summary": {
            "cases": total,
            "strategy": strategy,
            "recall_at_1": sum(item["hit_at_1"] for item in details) / total,
            f"recall_at_{metric_k}": (
                sum(item[f"hit_at_{metric_k}"] for item in details) / total
            ),
            f"mrr_at_{metric_k}": fmean(
                item[f"reciprocal_rank_at_{metric_k}"] for item in details
            ),
            "avg_latency_ms": round(fmean(latencies), 2),
            "p95_latency_ms": round(percentile(latencies, 0.95), 2),
        },
    }


def _load_gold_set() -> list[dict[str, Any]]:
    data = json.loads(GOLD_SET.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("gold set 顶层必须是 JSON array")
    return data


def test_find_first_relevant_rank_matches_label_key_and_value():
    results = [
        {"label": "表", "properties": {"表名称": "wrong"}},
        {"label": "指标", "properties": {"指标ID": "repurchase_users"}},
    ]
    expected = [{"label": "指标", "key_field": "指标ID", "value": "repurchase_users"}]
    assert find_first_relevant_rank(results, expected) == 2


def test_find_first_relevant_rank_returns_none_for_wrong_label():
    results = [{"label": "表", "properties": {"指标ID": "repurchase_users"}}]
    expected = [{"label": "指标", "key_field": "指标ID", "value": "repurchase_users"}]
    assert find_first_relevant_rank(results, expected) is None


def test_evaluate_cases_computes_recall_mrr_and_passes_targets():
    calls = []

    def fake_search(question, top_k, targets, strategy):
        calls.append((question, top_k, targets, strategy))
        return {"results": [
            {"label": "指标", "properties": {"指标ID": "wrong"}},
            {"label": "指标", "properties": {"指标ID": "right"}},
        ]}

    cases = [{
        "id": "q1", "question": "Q", "targets": ["指标"],
        "expected": [{"label": "指标", "key_field": "指标ID", "value": "right"}],
    }]
    report = evaluate_cases(cases, fake_search, source_top_k=10, metric_k=5)

    assert calls == [("Q", 10, ["指标"], "vector")]
    assert report["summary"]["recall_at_1"] == 0
    assert report["summary"]["recall_at_5"] == 1
    assert report["summary"]["mrr_at_5"] == 0.5
    assert report["cases"][0]["rank"] == 2


def test_evaluate_cases_rejects_too_small_source_pool():
    with pytest.raises(ValueError, match="source_top_k"):
        evaluate_cases([{"id": "q", "question": "Q", "expected": []}],
                       source_top_k=2, metric_k=5)


def test_percentile_uses_nearest_rank():
    assert percentile([1.0, 2.0, 3.0, 100.0], 0.95) == 100.0


@pytest.mark.skipif(
    not os.environ.get("SDA_INTEGRATION"),
    reason="检索质量测试默认跳过；设 SDA_INTEGRATION=1 启用",
)
def test_live_vector_and_hybrid_quality():
    """守住当前质量下限，并防止 Hybrid 明显回退。"""
    cases = _load_gold_set()
    vector = evaluate_cases(cases, strategy="vector")["summary"]
    hybrid = evaluate_cases(cases, strategy="hybrid")["summary"]
    print(json.dumps({"vector": vector, "hybrid": hybrid}, ensure_ascii=False, indent=2))

    assert vector["recall_at_1"] >= 0.65
    assert vector["recall_at_5"] >= 0.90
    assert vector["mrr_at_5"] >= 0.75
    assert hybrid["recall_at_1"] >= 0.80
    assert hybrid["recall_at_5"] >= 0.95
    assert hybrid["mrr_at_5"] >= 0.85
    assert hybrid["recall_at_1"] >= vector["recall_at_1"]
    assert hybrid["recall_at_5"] >= vector["recall_at_5"]
    assert hybrid["mrr_at_5"] >= vector["mrr_at_5"]
