import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "predicting_trends" / "scripts" / "forecast.py"


def run_forecast(tmp_path, payload):
    input_path = tmp_path / "forecast-input.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return run_forecast_file(input_path)


def run_forecast_file(input_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(input_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        output = {"raw_stdout": result.stdout, "stderr": result.stderr}
    return result, output


def monthly_series(values):
    return [
        {"date": f"2026-{index + 1:02d}-01", "value": value}
        for index, value in enumerate(values)
    ]


def base_payload(model, values):
    return {
        "metric": "Monthly revenue",
        "grain": "month",
        "horizon": 2,
        "model": model,
        "series": monthly_series(values),
        "options": {"holdout": 2},
    }


def test_naive_repeats_last_value(tmp_path):
    result, output = run_forecast(tmp_path, base_payload("naive", [100, 110, 125]))

    assert result.returncode == 0, output
    assert output["ok"] is True
    assert output["model"] == "naive"
    assert [row["value"] for row in output["forecast"]] == [125, 125]
    assert output["summary"]["forecast_total"] == 250


def test_moving_average_uses_recent_window(tmp_path):
    payload = base_payload("moving_average", [100, 120, 150, 180])
    payload["options"]["window"] = 3

    result, output = run_forecast(tmp_path, payload)

    assert result.returncode == 0, output
    assert output["model"] == "moving_average"
    assert output["forecast"][0]["value"] == 150


def test_exponential_smoothing_returns_contract_fields(tmp_path):
    result, output = run_forecast(
        tmp_path,
        base_payload("exponential_smoothing", [100, 105, 104, 110, 112]),
    )

    assert result.returncode == 0, output
    assert output["ok"] is True
    assert output["forecast"]
    assert "summary" in output
    assert output["confidence"] in {"high", "medium", "low"}


def test_holt_linear_extrapolates_upward_trend(tmp_path):
    result, output = run_forecast(
        tmp_path,
        base_payload("holt_linear", [100, 110, 120, 130, 140]),
    )

    assert result.returncode == 0, output
    assert output["forecast"][0]["value"] > 140
    assert output["forecast"][1]["value"] > output["forecast"][0]["value"]


def test_linear_trend_extrapolates_upward_trend(tmp_path):
    result, output = run_forecast(
        tmp_path,
        base_payload("linear_trend", [100, 110, 120, 130, 140]),
    )

    assert result.returncode == 0, output
    assert output["forecast"][0]["value"] > 140
    assert output["model"] == "linear_trend"


def test_log_linear_trend_rejects_non_positive_values(tmp_path):
    result, output = run_forecast(
        tmp_path,
        base_payload("log_linear_trend", [100, 0, 120]),
    )

    assert result.returncode != 0
    assert output["ok"] is False
    assert "positive" in output["error"]


def test_seasonal_naive_rejects_insufficient_history(tmp_path):
    payload = base_payload("seasonal_naive", [100, 110, 120])
    payload["season_length"] = 12

    result, output = run_forecast(tmp_path, payload)

    assert result.returncode != 0
    assert output["ok"] is False
    assert "seasonal" in output["error"]


def test_auto_baseline_returns_supported_model_and_backtest(tmp_path):
    result, output = run_forecast(
        tmp_path,
        base_payload("auto_baseline", [100, 105, 110, 115, 120, 125, 130]),
    )

    assert result.returncode == 0, output
    assert output["model"] in {
        "naive",
        "moving_average",
        "weighted_moving_average",
        "exponential_smoothing",
        "holt_linear",
        "linear_trend",
        "log_linear_trend",
    }
    assert output["backtest"]["holdout"] > 0
    assert "mape" in output["backtest"]


def test_duplicate_dates_fail_with_json_error(tmp_path):
    payload = base_payload("naive", [100, 110, 120])
    payload["series"][1]["date"] = payload["series"][0]["date"]

    result, output = run_forecast(tmp_path, payload)

    assert result.returncode != 0
    assert output["ok"] is False
    assert "duplicate" in output["error"]


def test_cli_accepts_utf8_sig_input(tmp_path):
    input_path = tmp_path / "forecast-input-bom.json"
    input_path.write_text(
        json.dumps(base_payload("naive", [100, 110, 120]), ensure_ascii=False),
        encoding="utf-8-sig",
    )

    result, output = run_forecast_file(input_path)

    assert result.returncode == 0, output
    assert output["ok"] is True
