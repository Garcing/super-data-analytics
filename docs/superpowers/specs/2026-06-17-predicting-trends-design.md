# predicting_trends Skill Design

## Goal

Add a reusable `predicting_trends/` skill for business forecasting questions. The skill should help an agent answer questions such as next month's metric forecast, whether a target is reachable, what target should be set, or how current trend affects future demand, revenue, workload, budget, or supply planning.

This skill sits in the analysis layer. It complements `diagnosing-anomalies`: anomaly diagnosis explains why a metric changed; trend prediction estimates what may happen next and how to set a business target from that expectation.

The first version should be practical for internet business analysis. It should favor explainable baselines, light statistical models, backtesting, assumptions, and business interpretation over a broad data science toolkit.

## Non-Goals

- Do not make `predicting_trends` responsible for retrieving metric definitions or querying data. Existing skills own context and data access.
- Do not build a full forecasting platform.
- Do not implement ARIMA, SARIMA, Prophet, machine learning models, or automatic holiday/event modeling in the first version.
- Do not present a forecast as a guaranteed result. Every output must include assumptions, uncertainty, and known risks.
- Do not treat the forecast value as the KPI target by default. Target setting must account for business ambition and risk appetite.

## Architecture

Create a new skill directory:

```text
predicting_trends/
  SKILL.md
  references/
    forecasting-workflow.md
    input-contract.md
    model-selection.md
    target-setting.md
    validation-and-uncertainty.md
    output-checklist.md
  scripts/
    forecast.py
  tests/
    test_forecast.py
```

`SKILL.md` stays concise. It tells agents when to use the skill, the default forecasting workflow, when to read each reference file, and how to collaborate with adjacent skills.

`references/` holds the reusable forecasting method library. It should explain model choice, data checks, backtesting, uncertainty, target setting, and final answer quality control in business-analysis language.

`scripts/forecast.py` is the stable CLI entry point for deterministic light forecasting. It accepts an input JSON file and writes machine-readable JSON to stdout. The script is intentionally small and dependency-light so it can be maintained inside the skill.

## Trigger Scope

Use this skill when the user asks for or depends on a forecast, projection, target, pacing estimate, or future trend. Example questions:

- "下个月收入大概是多少？"
- "下季度 DAU 目标定多少合适？"
- "按现在趋势月底能不能完成目标？"
- "未来两周客服工单量预计多少，需要排多少人？"
- "这条业务线接下来会继续增长吗？"
- "如果没有新增投放，GMV 预计会到多少？"

If the user asks why a past movement happened, use `diagnosing-anomalies` instead. If the user asks both why it changed and what comes next, first diagnose the past movement enough to identify data quality issues and structural breaks, then use this skill for the forward estimate.

## Skill Collaboration

The skill should not directly query data. It should coordinate with:

- `retrieving-context` for metric definitions, business hierarchy, table names, semantic model names, and known calendar or campaign context.
- `querying-via-powerbi` or `querying-via-sql` for historical time-series data.
- `diagnosing-anomalies` when the historical series contains a recent abnormal movement or likely structural break.
- `visualizing-data` for forecast charts with actuals, forecast periods, target lines, and uncertainty bands.
- `building-report` when the forecast should be delivered as a report, dashboard, PDF, image, web page, or Feishu document.

## Default Workflow

1. Clarify the forecasting problem.

   Confirm metric, forecast horizon, historical window, time grain, business scope, target usage, and delivery format. If the missing information changes the answer materially, ask before forecasting. If it does not, make an explicit assumption.

2. Reproduce the metric and inspect the series.

   Check whether the metric definition is stable, whether the latest period is complete, whether missing values or duplicates exist, and whether there were changes in data collection, business rules, campaigns, supply constraints, or pricing.

3. Decide whether forecasting is appropriate.

   Forecasting is acceptable when the historical series is comparable to the forecast period and has enough observations for the chosen method. If the business recently changed regime, produce a scenario forecast instead of pretending the old trend continues.

4. Build simple baselines first.

   Compare naive, recent average, moving average, and seasonal naive baselines before using trend or smoothing methods. Baselines are often sufficient for stable operational metrics.

5. Choose a light model.

   Select from moving average, weighted moving average, exponential smoothing, Holt linear trend, linear trend regression, log-linear trend regression, or seasonal naive. Prefer the simplest model that backtests reasonably and matches the observed pattern.

6. Backtest and compare.

   Hold out recent periods when enough history exists. Report at least one error metric and favor a model that is accurate enough, stable, and explainable. Do not overfit a noisy short series.

7. Produce forecast and uncertainty.

   Output point forecast, forecast range, summary total where relevant, model rationale, assumptions, warnings, and confidence level.

8. Convert forecast into target advice when needed.

   Separate baseline forecast from target recommendation. Provide conservative, baseline, and challenge targets based on forecast uncertainty, business controllability, and risk tolerance.

## CLI Input Contract

The forecast script accepts one JSON file:

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
    "interval_level": 0.8,
    "allow_log_trend": true
  }
}
```

Required fields are `metric`, `grain`, `horizon`, `model`, and `series`. Each series row requires `date` and `value`.

Supported grains are `day`, `week`, `month`, and `quarter`.

Supported first-version models:

- `naive`
- `seasonal_naive`
- `moving_average`
- `weighted_moving_average`
- `exponential_smoothing`
- `holt_linear`
- `linear_trend`
- `log_linear_trend`
- `auto_baseline`

`auto_baseline` should run a small candidate set, backtest where possible, and choose a model based on forecast error and warnings.

## CLI Output Contract

The command writes JSON to stdout:

```json
{
  "ok": true,
  "metric": "Monthly revenue",
  "model": "holt_linear",
  "model_reason": "Recent history shows a steady upward trend and Holt linear had the lowest holdout MAPE.",
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

Failures return non-zero and write compact JSON:

```json
{
  "ok": false,
  "error": "series must contain at least 3 numeric observations"
}
```

## Model Selection Rules

The reference guide should describe model choice in business terms:

- Use `naive` when the metric is very short, volatile, or mostly flat.
- Use `moving_average` when recent stability matters more than old history.
- Use `weighted_moving_average` when the latest periods should count more but trend is not strong enough for extrapolation.
- Use `exponential_smoothing` for noisy metrics with a stable level.
- Use `holt_linear` when there is a persistent linear trend and no strong seasonality.
- Use `seasonal_naive` when enough same-season history exists and seasonality dominates.
- Use `linear_trend` for simple additive growth or decline.
- Use `log_linear_trend` for multiplicative growth where values are positive and growth rates are more stable than absolute changes.

The guide should also explain when to upgrade outside this first version:

- Use ARIMA/SARIMA or a dedicated forecasting stack when there is strong autocorrelation, multiple seasonalities, enough history, and meaningful forecast stakes.
- Use regression or causal models when future drivers are known, such as planned spend, price, traffic, inventory, or staffing.
- Use scenario planning when the forecast depends on uncertain business actions or external events.

## Target Setting

When the user asks what target to set, the skill should produce target options instead of a single number:

- Conservative target: near the lower forecast range or achievable with current execution.
- Baseline target: around the point forecast or current operating plan.
- Challenge target: above baseline, requiring explicit growth levers or extra resources.

The target recommendation should state whether the metric is controllable by the team, whether the forecast horizon is short enough for action, and which levers could close the gap.

## Validation and Uncertainty

The skill must avoid false precision. It should check:

- Number of observations and whether the history covers comparable periods.
- Missing values, duplicates, zeros, negative values, and outliers.
- Incomplete latest period.
- Structural breaks caused by launches, pricing changes, campaigns, supply constraints, policy changes, or data pipeline changes.
- Calendar effects such as weekdays, weekends, holidays, shopping festivals, and month length.
- Whether aggregate forecasts hide segment-level changes.

Uncertainty can be estimated from holdout residuals or recent volatility. The exact interval does not need to be statistically perfect, but it must be labeled as an approximate business range.

Confidence levels:

- High: stable metric, enough comparable history, low backtest error, no major known structural break.
- Medium: usable history and acceptable error, but some volatility or business context risk.
- Low: short history, unstable metric, major structural break, missing data, or forecast depends heavily on unmodeled future actions.

## Output Style

Recommended response structure:

```text
预测结论：预计 <指标> 在 <预测窗口> 为 <预测值>，合理区间为 <下限>-<上限>。
依据：历史 <窗口> 呈现 <趋势/季节性/波动>，所选方法为 <模型>，回测误差约 <误差>。
目标建议：若用于目标制定，建议保守目标 <值>、基准目标 <值>、挑战目标 <值>。
关键假设：<口径稳定/无重大活动变化/数据完整>。
风险：<节假日/投放变化/供给约束/样本不足>。
置信度：<高/中/低>。
下一步：<需要补充的数据或业务动作>。
```

When the question is about target achievement, the answer should emphasize gap, required run rate, and actionable levers.

## Error Handling

Validation errors should be clear enough for an agent to fix the input:

- Missing required fields.
- Unknown model.
- Non-numeric values.
- Invalid or duplicate dates.
- Non-positive values for `log_linear_trend`.
- Insufficient observations for the selected model.
- `seasonal_naive` requested without enough seasonal history.
- Holdout is too large for the available series.

Warnings should not fail the run, but should be propagated into the final business answer.

## Testing

Use focused tests for the first release:

- CLI succeeds with `naive` on a short monthly series.
- CLI succeeds with `moving_average`.
- CLI succeeds with `exponential_smoothing`.
- CLI succeeds with `holt_linear`.
- CLI succeeds with `linear_trend`.
- CLI rejects `log_linear_trend` when values are zero or negative.
- CLI rejects insufficient history for `seasonal_naive`.
- `auto_baseline` returns one supported model and includes backtest fields when holdout is possible.
- CLI stdout is valid JSON on success and failure.
- Duplicate or unsorted dates are handled deterministically.

The tests should validate calculation behavior and contract shape, not chase statistical perfection.

## Integration Notes

Update the root skill routing documentation so `predicting_trends` is listed as an analysis-layer skill. Forecasting questions should route to this skill after requirement alignment unless the user already provides a clear metric, time range, and historical data.

The existing `diagnosing-anomalies` references mention prediction baselines for anomaly validation. That can remain separate; `predicting_trends` owns forward-looking forecast and target-setting workflow.

## Acceptance Criteria

- `predicting_trends/SKILL.md` exists and clearly defines trigger scope, workflow, collaboration, output style, and script usage.
- Reference files exist for workflow, input contract, model selection, target setting, validation and uncertainty, and output checklist.
- `scripts/forecast.py` runs from the repository root and returns JSON for valid and invalid inputs.
- Tests cover supported first-version models and common validation failures.
- Root routing documentation includes `predicting_trends` in the analysis layer.
- The first version remains understandable to a business analyst and does not require advanced data science background to use responsibly.
