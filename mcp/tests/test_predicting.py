"""predicting 内核契约测试 + 收紧校验回归。"""
import pytest
from sda_mcp.skills.predicting import forecast, ForecastResult, ForecastError


SERIES = [{"date": f"2025-01-{d:02d}", "value": v}
          for d, v in enumerate(range(100, 130), start=1)]  # 30 天


def test_linear_trend_basic():
    r = forecast({"metric": "gmv", "grain": "day", "horizon": 3,
                  "model": "linear_trend", "series": SERIES})
    assert isinstance(r, ForecastResult)
    assert r.model == "linear_trend"
    assert len(r.forecast) == 3
    assert all(p.lower <= p.value <= p.upper for p in r.forecast)
    assert not hasattr(r, "ok")


def test_auto_baseline_picks_a_model():
    r = forecast({"metric": "gmv", "grain": "day", "horizon": 2,
                  "model": "auto_baseline", "series": SERIES})
    assert r.model in {"naive", "moving_average", "weighted_moving_average",
                       "exponential_smoothing", "holt_linear", "linear_trend", "log_linear_trend"}


def test_non_integer_horizon_now_rejected():
    # 原 int(2.7)==2 静默截断；内核已收紧为抛错。
    with pytest.raises(ForecastError):
        forecast({"metric": "gmv", "grain": "day", "horizon": 2.7,
                  "model": "naive", "series": SERIES})


def test_missing_field_raises():
    with pytest.raises(ForecastError):
        forecast({"grain": "day", "horizon": 1, "model": "naive", "series": SERIES})


def test_non_integer_window_now_rejected():
    # 原 int(2.7)==2 静默截断；内核已收紧为抛错。
    with pytest.raises(ForecastError):
        forecast({"metric": "gmv", "grain": "day", "horizon": 2,
                  "model": "moving_average", "series": SERIES,
                  "options": {"window": 2.7}})
