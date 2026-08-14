"""Run a deterministic retrieval benchmark against the configured Neo4j graph.

This benchmark evaluates entity retrieval only.  It deliberately does not call
an LLM, mutate Neo4j, or score the generated natural-language answer.  That
makes it suitable for comparing vector, hybrid, and rank-fusion implementations
with the same gold set.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any, Callable

from sda_mcp.skills.retrieving_context import search


DEFAULT_GOLD_SET = Path(__file__).with_name("retrieval_gold.json")


def _matches(result: dict[str, Any], expected: dict[str, str]) -> bool:
    return (
        result.get("label") == expected["label"]
        and result.get("properties", {}).get(expected["key_field"]) == expected["value"]
    )


def find_first_relevant_rank(
    results: list[dict[str, Any]], expected: list[dict[str, str]],
) -> int | None:
    """Return the one-based rank of the first gold entity, or ``None``."""
    for rank, result in enumerate(results, start=1):
        if any(_matches(result, item) for item in expected):
            return rank
    return None


def percentile(values: list[float], percentile_value: float) -> float:
    """Nearest-rank percentile, adequate for the small deterministic gold set."""
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
        results = response.get("results", [])
        rank = find_first_relevant_rank(results, case["expected"])
        details.append({
            "id": case["id"],
            "question": case["question"],
            "rank": rank,
            "hit_at_1": rank == 1,
            f"hit_at_{metric_k}": rank is not None and rank <= metric_k,
            f"reciprocal_rank_at_{metric_k}": (
                1.0 / rank if rank is not None and rank <= metric_k else 0.0
            ),
            "latency_ms": round(latency_ms, 2),
            "result_count": len(results),
        })

    hit_at_k_key = f"hit_at_{metric_k}"
    rr_at_k_key = f"reciprocal_rank_at_{metric_k}"
    total = len(details)
    return {
        "summary": {
            "cases": total,
            "source_top_k": source_top_k,
            "metric_k": metric_k,
            "strategy": strategy,
            "recall_at_1": sum(d["hit_at_1"] for d in details) / total,
            f"recall_at_{metric_k}": sum(d[hit_at_k_key] for d in details) / total,
            f"mrr_at_{metric_k}": fmean(d[rr_at_k_key] for d in details),
            "avg_latency_ms": round(fmean(latencies), 2),
            "p95_latency_ms": round(percentile(latencies, 0.95), 2),
        },
        "cases": details,
    }


def load_gold_set(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("gold set 顶层必须是 JSON array")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="SDA Neo4j 检索基线评测（只读）")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD_SET)
    parser.add_argument("--source-top-k", type=int, default=10)
    parser.add_argument("--metric-k", type=int, default=5)
    parser.add_argument("--strategy", choices=("vector", "hybrid"), default="vector")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate_cases(
        load_gold_set(args.gold),
        source_top_k=args.source_top_k,
        metric_k=args.metric_k,
        strategy=args.strategy,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
