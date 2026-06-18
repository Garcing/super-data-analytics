import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "evaluating-impact" / "scripts" / "impact.py"


def run_impact(tmp_path, payload):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(input_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_json(result):
    return json.loads(result.stdout)


def test_ab_rate_detects_significant_lift(tmp_path):
    result = run_impact(
        tmp_path,
        {
            "analysis_type": "ab_rate",
            "alpha": 0.05,
            "control": {"n": 10000, "success": 1200},
            "treatment": {"n": 10000, "success": 1350},
        },
    )

    body = parse_json(result)
    assert result.returncode == 0
    assert body["ok"] is True
    assert body["analysis_type"] == "ab_rate"
    assert body["control_rate"] == 0.12
    assert body["treatment_rate"] == 0.135
    assert body["absolute_lift"] > 0
    assert body["relative_lift"] > 0
    assert body["p_value"] < 0.05
    assert body["significant"] is True
    assert body["confidence_interval"]["lower"] < body["absolute_lift"]
    assert body["confidence_interval"]["upper"] > body["absolute_lift"]


def test_ab_rate_returns_non_significant_for_close_result(tmp_path):
    result = run_impact(
        tmp_path,
        {
            "analysis_type": "ab_rate",
            "control": {"n": 1000, "success": 120},
            "treatment": {"n": 1000, "success": 124},
        },
    )

    body = parse_json(result)
    assert result.returncode == 0
    assert body["ok"] is True
    assert body["p_value"] > 0.05
    assert body["significant"] is False


def test_ab_rate_rejects_success_greater_than_sample(tmp_path):
    result = run_impact(
        tmp_path,
        {
            "analysis_type": "ab_rate",
            "control": {"n": 100, "success": 101},
            "treatment": {"n": 100, "success": 20},
        },
    )

    body = parse_json(result)
    assert result.returncode != 0
    assert body["ok"] is False
    assert "success" in body["error"]


def test_ab_mean_outputs_difference_and_interval(tmp_path):
    result = run_impact(
        tmp_path,
        {
            "analysis_type": "ab_mean",
            "alpha": 0.05,
            "control": {"n": 500, "mean": 10.0, "stddev": 4.0},
            "treatment": {"n": 520, "mean": 10.8, "stddev": 4.2},
        },
    )

    body = parse_json(result)
    assert result.returncode == 0
    assert body["ok"] is True
    assert body["mean_difference"] == 0.8
    assert body["relative_difference"] == 0.08
    assert 0 <= body["p_value"] <= 1
    assert body["confidence_interval"]["lower"] < 0.8
    assert body["confidence_interval"]["upper"] > 0.8


def test_did_returns_double_difference(tmp_path):
    result = run_impact(
        tmp_path,
        {
            "analysis_type": "did",
            "treatment_before": 100,
            "treatment_after": 130,
            "control_before": 80,
            "control_after": 90,
        },
    )

    body = parse_json(result)
    assert result.returncode == 0
    assert body["ok"] is True
    assert body["treatment_change"] == 30
    assert body["control_change"] == 10
    assert body["did_effect"] == 20
    assert body["relative_did_effect"] == 0.2
    assert body["warnings"]


def test_roi_returns_positive_result(tmp_path):
    result = run_impact(
        tmp_path,
        {
            "analysis_type": "roi",
            "benefit": 1200000,
            "cost": 300000,
            "gross_margin_rate": 0.4,
        },
    )

    body = parse_json(result)
    assert result.returncode == 0
    assert body["ok"] is True
    assert body["net_benefit"] == 900000
    assert body["roi"] == 3.0
    assert body["profitable"] is True
    assert body["margin_adjusted_benefit"] == 480000
    assert body["margin_adjusted_roi"] == 0.6


def test_roi_handles_zero_benefit(tmp_path):
    result = run_impact(
        tmp_path,
        {
            "analysis_type": "roi",
            "benefit": 0,
            "cost": 100,
        },
    )

    body = parse_json(result)
    assert result.returncode == 0
    assert body["ok"] is True
    assert body["net_benefit"] == -100
    assert body["roi"] == -1.0
    assert body["profitable"] is False


def test_sample_size_rate_returns_positive_integer(tmp_path):
    result = run_impact(
        tmp_path,
        {
            "analysis_type": "sample_size_rate",
            "baseline_rate": 0.1,
            "minimum_detectable_effect": 0.02,
            "alpha": 0.05,
            "power": 0.8,
        },
    )

    body = parse_json(result)
    assert result.returncode == 0
    assert body["ok"] is True
    assert isinstance(body["sample_size_per_group"], int)
    assert body["sample_size_per_group"] > 0


def test_unknown_analysis_type_fails_clearly(tmp_path):
    result = run_impact(tmp_path, {"analysis_type": "unknown"})

    body = parse_json(result)
    assert result.returncode != 0
    assert body["ok"] is False
    assert "Unknown analysis_type" in body["error"]
