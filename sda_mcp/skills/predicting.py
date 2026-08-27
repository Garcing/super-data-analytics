"""趋势预测内核（从 predicting-trends/scripts/forecast.py 剥离）。

去 CLI/文件读/{ok} 信封；ForecastError 改继承 SkillError；出参 ForecastResult。
收紧 horizon/window 的整数校验；标注 interval_width 为启发式带。
算法与原脚本一致。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from sda_mcp.errors import SkillError

SUPPORTED_GRAINS = {"day", "week", "month", "quarter"}
SUPPORTED_MODELS = {
    "naive", "seasonal_naive", "moving_average", "weighted_moving_average",
    "exponential_smoothing", "holt_linear", "linear_trend", "log_linear_trend",
    "auto_baseline",
}
AUTO_MODELS = [
    "naive", "moving_average", "weighted_moving_average", "exponential_smoothing",
    "holt_linear", "linear_trend", "log_linear_trend",
]


class ForecastError(SkillError):
    """预测输入或计算失败。"""


@dataclass
class ForecastPoint:
    date: str
    value: float
    lower: float
    upper: float


@dataclass
class ForecastSummary:
    forecast_total: float
    last_actual: float
    change_vs_last_actual: float | None
    target_gap: float | None = None


@dataclass
class Backtest:
    holdout: int
    mae: float | None
    mape: float | None
    rmse: float | None


@dataclass
class ForecastResult:
    metric: str
    model: str
    model_reason: str
    forecast: list[ForecastPoint]
    summary: ForecastSummary
    backtest: Backtest
    confidence: str
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---- 以下函数体逐字搬迁自原 forecast.py（仅 horizon/window 整数校验收紧）----

def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ForecastError(f"invalid date '{value}', expected YYYY-MM-DD") from exc


def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def add_months(day, months):
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = [31, 29 if is_leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(day.day, month_lengths[month - 1]))


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


def _require_int(value, label):
    """收紧整数校验：原 int() 会静默截断 2.7 → 2。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForecastError(f"{label} must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ForecastError(f"{label} must be an integer, got {value}")
    return int(value)


# 各 grain 对应的序列日期中位间隔(天)合理区间;月/季度取宽边界覆盖 28-31/89-93 天。
_GRAIN_INTERVAL_DAYS = {
    "day": (0, 2),
    "week": (5.5, 8.5),
    "month": (26, 32.5),
    "quarter": (85, 97),
}


def _median_interval_days(series) -> float | None:
    """序列相邻日期间隔的中位数(天);点数不足返回 None。"""
    gaps = sorted((series[i + 1]["date"] - series[i]["date"]).days
                  for i in range(len(series) - 1))
    if not gaps:
        return None
    mid = len(gaps) // 2
    if len(gaps) % 2:
        return float(gaps[mid])
    return (gaps[mid - 1] + gaps[mid]) / 2


def validate_payload(payload):
    for field_name in ["metric", "grain", "horizon", "model", "series"]:
        if field_name not in payload:
            raise ForecastError(f"missing required field '{field_name}'")
    grain = payload["grain"]
    if grain not in SUPPORTED_GRAINS:
        raise ForecastError(f"unsupported grain '{grain}'")
    model = payload["model"]
    if model not in SUPPORTED_MODELS:
        raise ForecastError(f"unknown model '{model}'")
    horizon = _require_int(payload["horizon"], "horizon")
    if horizon < 1:
        raise ForecastError("horizon must be a positive integer")
    raw_series = payload["series"]
    if not isinstance(raw_series, list) or len(raw_series) < 2:
        raise ForecastError("series must contain at least 2 observations")
    parsed, seen_dates = [], set()
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
        "metric": str(payload["metric"]), "grain": grain, "horizon": horizon,
        "model": model, "series": parsed,
        "season_length": _require_int(payload.get("season_length", 0) or 0, "season_length"),
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
    if "window" in options:
        window = _require_int(options["window"], "window")
    else:
        window = min(3, len(values))
    if window < 1 or window > len(values):
        raise ForecastError("moving_average window must fit available history")
    level = mean(values[-window:])
    return [level] * horizon


def forecast_weighted_moving_average(values, horizon, options=None, season_length=0):
    options = options or {}
    if "window" in options:
        window = _require_int(options["window"], "window")
    else:
        window = min(3, len(values))
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
        if "window" in backtest_options:
            backtest_options["window"] = min(_require_int(backtest_options["window"], "window"), len(train))
        else:
            backtest_options["window"] = min(3, len(train))
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
    """启发式预测带宽度（残差RMS×1.28），非严格置信区间。"""
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


def forecast(payload: Mapping[str, Any]) -> ForecastResult:
    """趋势预测入口。失败抛 ForecastError。"""
    validated = validate_payload(payload)
    values = [row["value"] for row in validated["series"]]
    warnings = []
    if len(values) < 6:
        warnings.append("Series has limited history; treat the forecast as low confidence.")
    # QA 2026-08-26:月度数据标 grain=day 曾静默输出逐日日期,数值单位口径失真无警告。
    interval = _median_interval_days(validated["series"])
    low, high = _GRAIN_INTERVAL_DAYS[validated["grain"]]
    if interval is not None and not low <= interval <= high:
        warnings.append(
            f"声明的 grain='{validated['grain']}' 与序列日期实际间隔（约 {interval:.1f} 天）不符；"
            "预测日期将按声明的 grain 生成，数值的单位口径可能有误导，请核对 grain 或日期序列。")
    # QA 2026-08-26:12 点历史 horizon=200 照跑且 confidence 仍 high——长程外推须降级。
    if validated["horizon"] > len(values):
        warnings.append(
            f"horizon={validated['horizon']} 超过历史点数（{len(values)}）；"
            "长程外推可靠性低，远端点值与区间不足以支撑决策。")

    selected_model = validated["model"]
    precomputed_backtest = None
    if selected_model == "auto_baseline":
        selected_model, precomputed_backtest = choose_auto_model(
            values, validated["options"], validated["season_length"])

    bt = precomputed_backtest or backtest_model(
        selected_model, values, validated["options"], validated["season_length"])
    predictions = run_model(selected_model, values, validated["horizon"],
                            validated["options"], validated["season_length"])
    width = interval_width(bt, values)
    dates = next_dates(validated["series"][-1]["date"], validated["grain"], validated["horizon"])
    forecast_rows = [
        ForecastPoint(date=fd.isoformat(), value=round_value(v),
                      lower=round_value(v - width), upper=round_value(v + width))
        for fd, v in zip(dates, predictions)
    ]
    forecast_total = sum(p.value for p in forecast_rows)
    last_actual = values[-1]
    summary = ForecastSummary(
        forecast_total=round_value(forecast_total),
        last_actual=round_value(last_actual),
        change_vs_last_actual=round_value((forecast_rows[0].value - last_actual) / last_actual) if last_actual else None,
    )
    if validated["target"] is not None:
        try:
            summary.target_gap = round_value(forecast_total - float(validated["target"]))
        except (TypeError, ValueError):
            warnings.append("Target was provided but is not numeric.")
    return ForecastResult(
        metric=validated["metric"], model=selected_model,
        model_reason=model_reason(selected_model, bt),
        forecast=forecast_rows, summary=summary,
        backtest=Backtest(holdout=bt.get("holdout", 0),
                          mae=round_value(bt["mae"]) if bt.get("mae") is not None else None,
                          mape=round_value(bt["mape"]) if bt.get("mape") is not None else None,
                          rmse=round_value(bt["rmse"]) if bt.get("rmse") is not None else None),
        confidence=classify_confidence(bt, warnings),
        assumptions=["Metric definition remains stable during the forecast period."],
        warnings=warnings,
    )
