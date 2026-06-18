#!/usr/bin/env python3
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


SUPPORTED_GRAINS = {"day", "week", "month", "quarter"}
SUPPORTED_MODELS = {
    "naive",
    "seasonal_naive",
    "moving_average",
    "weighted_moving_average",
    "exponential_smoothing",
    "holt_linear",
    "linear_trend",
    "log_linear_trend",
    "auto_baseline",
}
AUTO_MODELS = [
    "naive",
    "moving_average",
    "weighted_moving_average",
    "exponential_smoothing",
    "holt_linear",
    "linear_trend",
    "log_linear_trend",
]


class ForecastError(ValueError):
    pass


def emit(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return code


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ForecastError(f"invalid date '{value}', expected YYYY-MM-DD") from exc


def add_months(day, months):
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = [31, 29 if is_leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(day.day, month_lengths[month - 1]))


def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def next_dates(last_date, grain, horizon):
    if grain == "day":
        return [last_date + timedelta(days=index + 1) for index in range(horizon)]
    if grain == "week":
        return [last_date + timedelta(weeks=index + 1) for index in range(horizon)]
    if grain == "month":
        return [add_months(last_date, index + 1) for index in range(horizon)]
    if grain == "quarter":
        return [add_months(last_date, (index + 1) * 3) for index in range(horizon)]
    raise ForecastError(f"unsupported grain '{grain}'")


def validate_payload(payload):
    for field in ["metric", "grain", "horizon", "model", "series"]:
        if field not in payload:
            raise ForecastError(f"missing required field '{field}'")

    grain = payload["grain"]
    if grain not in SUPPORTED_GRAINS:
        raise ForecastError(f"unsupported grain '{grain}'")

    model = payload["model"]
    if model not in SUPPORTED_MODELS:
        raise ForecastError(f"unknown model '{model}'")

    try:
        horizon = int(payload["horizon"])
    except (TypeError, ValueError) as exc:
        raise ForecastError("horizon must be a positive integer") from exc
    if horizon < 1:
        raise ForecastError("horizon must be a positive integer")

    raw_series = payload["series"]
    if not isinstance(raw_series, list) or len(raw_series) < 2:
        raise ForecastError("series must contain at least 2 observations")

    parsed = []
    seen_dates = set()
    for row in raw_series:
        if not isinstance(row, dict):
            raise ForecastError("series rows must be objects")
        current_date = parse_date(row.get("date"))
        if current_date in seen_dates:
            raise ForecastError(f"duplicate date '{current_date.isoformat()}' in series")
        seen_dates.add(current_date)
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ForecastError("series values must be numeric") from exc
        if not math.isfinite(value):
            raise ForecastError("series values must be finite numbers")
        parsed.append({"date": current_date, "value": value})

    parsed.sort(key=lambda item: item["date"])
    return {
        "metric": str(payload["metric"]),
        "grain": grain,
        "horizon": horizon,
        "model": model,
        "series": parsed,
        "season_length": int(payload.get("season_length", 0) or 0),
        "target": payload.get("target"),
        "options": payload.get("options", {}) if isinstance(payload.get("options", {}), dict) else {},
    }


def mean(values):
    return sum(values) / len(values)


def forecast_naive(values, horizon, options=None, season_length=0):
    return [values[-1]] * horizon


def forecast_seasonal_naive(values, horizon, options=None, season_length=0):
    if season_length < 1:
        raise ForecastError("seasonal_naive requires season_length")
    if len(values) < season_length * 2:
        raise ForecastError("seasonal_naive requires at least two seasonal cycles of history")
    return [values[-season_length + (index % season_length)] for index in range(horizon)]


def forecast_moving_average(values, horizon, options=None, season_length=0):
    options = options or {}
    window = int(options.get("window", min(3, len(values))))
    if window < 1 or window > len(values):
        raise ForecastError("moving_average window must fit available history")
    level = mean(values[-window:])
    return [level] * horizon


def forecast_weighted_moving_average(values, horizon, options=None, season_length=0):
    options = options or {}
    window = int(options.get("window", min(3, len(values))))
    if window < 1 or window > len(values):
        raise ForecastError("weighted_moving_average window must fit available history")
    recent = values[-window:]
    weights = list(range(1, window + 1))
    level = sum(value * weight for value, weight in zip(recent, weights)) / sum(weights)
    return [level] * horizon


def forecast_exponential_smoothing(values, horizon, options=None, season_length=0):
    options = options or {}
    alpha = float(options.get("alpha", 0.4))
    if not 0 < alpha <= 1:
        raise ForecastError("exponential_smoothing alpha must be in (0, 1]")
    level = values[0]
    for value in values[1:]:
        level = alpha * value + (1 - alpha) * level
    return [level] * horizon


def forecast_holt_linear(values, horizon, options=None, season_length=0):
    if len(values) < 3:
        raise ForecastError("holt_linear requires at least 3 observations")
    options = options or {}
    alpha = float(options.get("alpha", 0.5))
    beta = float(options.get("beta", 0.3))
    if not 0 < alpha <= 1 or not 0 < beta <= 1:
        raise ForecastError("holt_linear alpha and beta must be in (0, 1]")
    level = values[0]
    trend = values[1] - values[0]
    for value in values[1:]:
        previous_level = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (1 - beta) * trend
    return [level + (index + 1) * trend for index in range(horizon)]


def linear_coefficients(values):
    n = len(values)
    if n < 2:
        raise ForecastError("linear trend requires at least 2 observations")
    xs = list(range(n))
    x_bar = mean(xs)
    y_bar = mean(values)
    denominator = sum((x - x_bar) ** 2 for x in xs)
    if denominator == 0:
        raise ForecastError("linear trend requires varying x values")
    slope = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, values)) / denominator
    intercept = y_bar - slope * x_bar
    return intercept, slope


def forecast_linear_trend(values, horizon, options=None, season_length=0):
    intercept, slope = linear_coefficients(values)
    start = len(values)
    return [intercept + slope * (start + index) for index in range(horizon)]


def forecast_log_linear_trend(values, horizon, options=None, season_length=0):
    if any(value <= 0 for value in values):
        raise ForecastError("log_linear_trend requires positive values")
    logs = [math.log(value) for value in values]
    intercept, slope = linear_coefficients(logs)
    start = len(values)
    return [math.exp(intercept + slope * (start + index)) for index in range(horizon)]


MODEL_FUNCS = {
    "naive": forecast_naive,
    "seasonal_naive": forecast_seasonal_naive,
    "moving_average": forecast_moving_average,
    "weighted_moving_average": forecast_weighted_moving_average,
    "exponential_smoothing": forecast_exponential_smoothing,
    "holt_linear": forecast_holt_linear,
    "linear_trend": forecast_linear_trend,
    "log_linear_trend": forecast_log_linear_trend,
}


def error_metrics(actual, predicted):
    errors = [prediction - value for value, prediction in zip(actual, predicted)]
    abs_errors = [abs(error) for error in errors]
    mae = mean(abs_errors)
    rmse = math.sqrt(mean([error**2 for error in errors]))
    non_zero_pairs = [(value, abs_error) for value, abs_error in zip(actual, abs_errors) if value != 0]
    mape = mean([abs_error / abs(value) for value, abs_error in non_zero_pairs]) if non_zero_pairs else None
    return {"mae": mae, "mape": mape, "rmse": rmse, "residuals": errors}


def run_model(model, values, horizon, options, season_length):
    return MODEL_FUNCS[model](values, horizon, options, season_length)


def backtest_model(model, values, options, season_length):
    requested = int(options.get("holdout", min(3, max(1, len(values) // 4))))
    if len(values) < 4:
        return {"holdout": 0, "mae": None, "mape": None, "rmse": None, "residuals": []}
    holdout = min(requested, max(1, len(values) // 2))
    train = values[:-holdout]
    actual = values[-holdout:]
    backtest_options = dict(options)
    if model in {"moving_average", "weighted_moving_average"}:
        backtest_options["window"] = min(int(backtest_options.get("window", min(3, len(train)))), len(train))
    predicted = run_model(model, train, holdout, backtest_options, season_length)
    metrics = error_metrics(actual, predicted)
    return {
        "holdout": holdout,
        "mae": metrics["mae"],
        "mape": metrics["mape"],
        "rmse": metrics["rmse"],
        "residuals": metrics["residuals"],
    }


def choose_auto_model(values, options, season_length):
    results = []
    for candidate in AUTO_MODELS:
        if candidate == "log_linear_trend" and not options.get("allow_log_trend", True):
            continue
        try:
            backtest = backtest_model(candidate, values, options, season_length)
            score = backtest["mape"] if backtest["mape"] is not None else backtest["mae"]
            if score is None:
                run_model(candidate, values, 1, options, season_length)
                score = float("inf")
            results.append((score, candidate, backtest))
        except ForecastError:
            continue
    if not results:
        raise ForecastError("auto_baseline could not find a valid model for this series")
    results.sort(key=lambda item: (item[0], AUTO_MODELS.index(item[1])))
    return results[0][1], results[0][2]


def round_value(value):
    rounded = round(float(value), 6)
    if rounded == 0:
        return 0
    return rounded


def interval_width(backtest, values):
    residuals = backtest.get("residuals") or []
    if residuals:
        base = math.sqrt(mean([residual**2 for residual in residuals]))
    elif len(values) > 1:
        deltas = [values[index] - values[index - 1] for index in range(1, len(values))]
        base = math.sqrt(mean([(delta - mean(deltas)) ** 2 for delta in deltas])) if len(deltas) > 1 else abs(deltas[0])
    else:
        base = 0
    return base * 1.28


def classify_confidence(backtest, warnings):
    if warnings:
        return "low"
    mape = backtest.get("mape")
    if mape is None:
        return "medium"
    if mape <= 0.08:
        return "high"
    if mape <= 0.2:
        return "medium"
    return "low"


def model_reason(model, backtest):
    if model == "auto_baseline":
        return "Selected by comparing lightweight baseline models on recent holdout error."
    if backtest.get("holdout", 0) > 0 and backtest.get("mape") is not None:
        return f"{model} was selected; recent holdout MAPE is {round_value(backtest['mape'])}."
    return f"{model} was selected based on the requested forecast method."


def build_result(payload):
    values = [row["value"] for row in payload["series"]]
    warnings = []
    if len(values) < 6:
        warnings.append("Series has limited history; treat the forecast as low confidence.")

    selected_model = payload["model"]
    precomputed_backtest = None
    if selected_model == "auto_baseline":
        selected_model, precomputed_backtest = choose_auto_model(values, payload["options"], payload["season_length"])

    backtest = precomputed_backtest or backtest_model(selected_model, values, payload["options"], payload["season_length"])
    predictions = run_model(
        selected_model,
        values,
        payload["horizon"],
        payload["options"],
        payload["season_length"],
    )
    width = interval_width(backtest, values)
    dates = next_dates(payload["series"][-1]["date"], payload["grain"], payload["horizon"])
    forecast_rows = [
        {
            "date": forecast_date.isoformat(),
            "value": round_value(value),
            "lower": round_value(value - width),
            "upper": round_value(value + width),
        }
        for forecast_date, value in zip(dates, predictions)
    ]
    forecast_total = sum(row["value"] for row in forecast_rows)
    last_actual = values[-1]
    summary = {
        "forecast_total": round_value(forecast_total),
        "last_actual": round_value(last_actual),
        "change_vs_last_actual": round_value((forecast_rows[0]["value"] - last_actual) / last_actual) if last_actual else None,
    }
    if payload["target"] is not None:
        try:
            summary["target_gap"] = round_value(forecast_total - float(payload["target"]))
        except (TypeError, ValueError):
            warnings.append("Target was provided but is not numeric.")

    return {
        "ok": True,
        "metric": payload["metric"],
        "model": selected_model,
        "model_reason": model_reason(selected_model, backtest),
        "forecast": forecast_rows,
        "summary": summary,
        "backtest": {
            "holdout": backtest.get("holdout", 0),
            "mae": round_value(backtest["mae"]) if backtest.get("mae") is not None else None,
            "mape": round_value(backtest["mape"]) if backtest.get("mape") is not None else None,
            "rmse": round_value(backtest["rmse"]) if backtest.get("rmse") is not None else None,
        },
        "confidence": classify_confidence(backtest, warnings),
        "assumptions": ["Metric definition remains stable during the forecast period."],
        "warnings": warnings,
    }


def load_payload(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ForecastError(f"input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ForecastError(f"invalid JSON input: {exc.msg}") from exc


def main(argv):
    if len(argv) != 2:
        return emit({"ok": False, "error": "usage: forecast.py <input.json>"}, 2)
    try:
        payload = validate_payload(load_payload(argv[1]))
        return emit(build_result(payload), 0)
    except ForecastError as exc:
        return emit({"ok": False, "error": str(exc)}, 1)
    except Exception as exc:
        return emit({"ok": False, "error": f"unexpected error: {exc}"}, 1)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
