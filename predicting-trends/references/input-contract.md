# 预测 CLI 输入契约

当已经拿到干净的历史时间序列，并且需要一个可复现的轻量预测结果时，使用 `scripts/forecast.py`。

## 命令

```bash
python predicting_trends/scripts/forecast.py <input.json>
```

命令会把 JSON 写到 stdout。`ok: true` 表示预测成功；`ok: false` 表示输入需要修正，或所选模型不适合当前数据。

## 输入 JSON

```json
{
  "metric": "Monthly revenue",
  "grain": "month",
  "horizon": 3,
  "season_length": 12,
  "model": "auto_baseline",
  "target": 1200000,
  "series": [
    { "date": "2025-01-01", "value": 830000 },
    { "date": "2025-02-01", "value": 860000 }
  ],
  "options": {
    "holdout": 3,
    "window": 3,
    "alpha": 0.4,
    "beta": 0.3,
    "allow_log_trend": true
  }
}
```

## 必填字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `metric` | string | 便于阅读的指标名称。 |
| `grain` | string | `day`、`week`、`month` 或 `quarter`。 |
| `horizon` | integer | 需要预测的未来周期数。 |
| `model` | string | 支持的模型名称。 |
| `series` | array | 每行包含 `date` 和数值型 `value`。 |

日期必须使用 `YYYY-MM-DD`。重复日期会被拒绝。输入行可以未排序，脚本会按日期排序后再预测。

## 支持模型

- `naive`
- `seasonal_naive`
- `moving_average`
- `weighted_moving_average`
- `exponential_smoothing`
- `holt_linear`
- `linear_trend`
- `log_linear_trend`
- `auto_baseline`

`seasonal_naive` 需要传入 `season_length`，并且至少有两个完整季节周期。`log_linear_trend` 要求所有值都大于 0。

## 成功输出

```json
{
  "ok": true,
  "metric": "Monthly revenue",
  "model": "holt_linear",
  "model_reason": "holt_linear was selected; recent holdout MAPE is 0.041.",
  "forecast": [
    {
      "date": "2026-07-01",
      "value": 1120000,
      "lower": 1040000,
      "upper": 1200000
    }
  ],
  "summary": {
    "forecast_total": 1120000,
    "last_actual": 1060000,
    "change_vs_last_actual": 0.0566,
    "target_gap": -80000
  },
  "backtest": {
    "holdout": 3,
    "mae": 42000,
    "mape": 0.041,
    "rmse": 51000
  },
  "confidence": "medium",
  "assumptions": [
    "Metric definition remains stable during the forecast period."
  ],
  "warnings": []
}
```

## 失败输出

```json
{
  "ok": false,
  "error": "series values must be numeric"
}
```

## Agent 使用注意

- 将 `lower` 和 `upper` 理解为近似业务范围，不要当作严格统计置信区间。
- 必须把 `warnings` 带入最终回答，不要隐藏。
- 低置信度预测不要用过度精确的数字包装。
- 如果预测用于目标决策，回答前读取 `target-setting.md`。
