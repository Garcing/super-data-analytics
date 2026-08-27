"""P1-b 回归:forecast 的 grain 与 horizon 护栏。

QA 实测(2026-08-26):月度数据标 grain=day 静默输出逐日日期,"每月+3"被标成
"每日+3"且无警告;12 点历史 horizon=200 照跑,confidence 仍 high、区间不展宽。
修复:声明 grain 与序列日期实际中位间隔不符 → warning;horizon 超过历史点数 →
warning 且 confidence 降级(classify_confidence 对非空 warnings 返回 low)。
"""
from sda_mcp.skills.predicting import forecast


def _monthly_series(n=12, start=100, step=3):
    import datetime as dt
    base = dt.date(2025, 1, 1)
    return [
        {"date": (base.replace(year=2025 + i // 12, month=i % 12 + 1)).isoformat(),
         "value": start + step * i}
        for i in range(n)
    ]


def _daily_series(n=14):
    import datetime as dt
    base = dt.date(2025, 6, 1)
    return [{"date": (base + dt.timedelta(days=i)).isoformat(), "value": 100 + i}
            for i in range(n)]


def test_grain_mismatch_produces_warning():
    payload = {"metric": "m", "grain": "day", "horizon": 3, "model": "linear_trend",
               "series": _monthly_series()}
    r = forecast(payload)
    assert any("grain" in w and "间隔" in w for w in r.warnings), r.warnings


def test_grain_match_produces_no_grain_warning():
    payload = {"metric": "m", "grain": "month", "horizon": 3, "model": "linear_trend",
               "series": _monthly_series()}
    r = forecast(payload)
    assert not any("间隔" in w for w in r.warnings), r.warnings


def test_daily_series_with_day_grain_no_warning():
    payload = {"metric": "m", "grain": "day", "horizon": 3, "model": "linear_trend",
               "series": _daily_series()}
    r = forecast(payload)
    assert not any("间隔" in w for w in r.warnings), r.warnings


def test_horizon_beyond_history_warns_and_degrades_confidence():
    payload = {"metric": "m", "grain": "month", "horizon": 50, "model": "linear_trend",
               "series": _monthly_series(12)}
    r = forecast(payload)
    assert any("horizon" in w and "历史" in w for w in r.warnings), r.warnings
    assert r.confidence == "low"
