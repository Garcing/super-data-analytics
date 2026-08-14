import pytest

from evals.benchmark_retrieval import (
    evaluate_cases, find_first_relevant_rank, percentile,
)


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
        evaluate_cases([{"id": "q", "question": "Q", "expected": []}], source_top_k=2, metric_k=5)


def test_percentile_uses_nearest_rank():
    assert percentile([1.0, 2.0, 3.0, 100.0], 0.95) == 100.0
