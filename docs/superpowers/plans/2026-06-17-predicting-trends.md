# Predicting Trends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `predicting_trends` skill as a business forecasting method library with a deterministic lightweight forecast CLI and tests.

**Architecture:** `SKILL.md` provides concise agent routing and workflow instructions. `references/` contains reusable forecasting guidance. `scripts/forecast.py` is a dependency-light Python CLI that validates a JSON series, runs simple forecasting models, backtests where possible, and returns JSON.

**Tech Stack:** Markdown skill docs, Python standard library, pytest.

---

## File Structure

- Create `predicting_trends/SKILL.md`: trigger scope, workflow, collaborating skills, script usage, output contract.
- Create `predicting_trends/references/forecasting-workflow.md`: end-to-end forecasting workflow.
- Create `predicting_trends/references/input-contract.md`: JSON input/output and CLI examples.
- Create `predicting_trends/references/model-selection.md`: model choice rules and upgrade paths.
- Create `predicting_trends/references/target-setting.md`: converting forecasts into target suggestions.
- Create `predicting_trends/references/validation-and-uncertainty.md`: data checks, backtesting, intervals, confidence.
- Create `predicting_trends/references/output-checklist.md`: final answer self-check.
- Create `predicting_trends/scripts/forecast.py`: CLI and model implementation.
- Create `predicting_trends/tests/test_forecast.py`: behavior tests for CLI contract and supported models.
- Modify `AGENTS.md`: add `predicting_trends` to architecture and routing.
- Modify `aligning-requirements/SKILL.md`: add `predicting_trends` to the skill suite and examples.

## Task 1: Forecast CLI Tests

**Files:**
- Create: `predicting_trends/tests/test_forecast.py`

- [ ] **Step 1: Write failing tests**

Add pytest helpers that execute `python predicting_trends/scripts/forecast.py <input.json>` and parse JSON stdout.

Cover:

- `naive` repeats the last value.
- `moving_average` returns the recent average.
- `exponential_smoothing` succeeds with forecast, summary, and confidence.
- `holt_linear` extrapolates an upward trend.
- `linear_trend` extrapolates an upward trend.
- `log_linear_trend` rejects zero or negative values.
- `seasonal_naive` rejects insufficient seasonal history.
- `auto_baseline` returns one supported model and backtest fields.
- Duplicate dates fail with a clear JSON error.

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
python -m pytest predicting_trends/tests/test_forecast.py -q
```

Expected: fail because `predicting_trends/scripts/forecast.py` does not exist.

## Task 2: Forecast CLI Implementation

**Files:**
- Create: `predicting_trends/scripts/forecast.py`
- Test: `predicting_trends/tests/test_forecast.py`

- [ ] **Step 1: Implement minimal CLI structure**

Implement:

- `main(argv)`
- JSON file loading
- success and error JSON output
- validation for required fields, supported grains, numeric values, unique dates, positive horizon

- [ ] **Step 2: Implement model functions**

Implement:

- `forecast_naive`
- `forecast_seasonal_naive`
- `forecast_moving_average`
- `forecast_weighted_moving_average`
- `forecast_exponential_smoothing`
- `forecast_holt_linear`
- `forecast_linear_trend`
- `forecast_log_linear_trend`

Use the Python standard library only.

- [ ] **Step 3: Implement backtest and auto selection**

Implement:

- holdout splitting when enough rows exist
- MAE, MAPE, RMSE
- `auto_baseline` candidate scoring
- warnings and confidence classification

- [ ] **Step 4: Run forecast tests**

Run:

```bash
python -m pytest predicting_trends/tests/test_forecast.py -q
```

Expected: all tests pass.

## Task 3: Skill Documentation

**Files:**
- Create: `predicting_trends/SKILL.md`
- Create: `predicting_trends/references/forecasting-workflow.md`
- Create: `predicting_trends/references/input-contract.md`
- Create: `predicting_trends/references/model-selection.md`
- Create: `predicting_trends/references/target-setting.md`
- Create: `predicting_trends/references/validation-and-uncertainty.md`
- Create: `predicting_trends/references/output-checklist.md`

- [ ] **Step 1: Write concise SKILL.md**

Include frontmatter:

```yaml
---
name: predicting_trends
description: 业务预测和目标制定方法论。用于回答下月/下季度指标预测、目标设定、趋势外推、达成判断、资源预算预估等需要预测结果的问题；指导 agent 完成预测问题澄清、历史序列检查、轻量模型选择、回测验证、不确定性表达和目标建议。
---
```

- [ ] **Step 2: Write references**

Each reference file should be complete enough for an agent to use without external forecasting knowledge, but concise enough to stay maintainable.

- [ ] **Step 3: Check references from SKILL.md**

Verify every referenced file exists and the paths match exactly.

## Task 4: Routing Integration

**Files:**
- Modify: `AGENTS.md`
- Modify: `aligning-requirements/SKILL.md`

- [ ] **Step 1: Update root architecture**

Add `predicting_trends/` as an analysis-layer skill in the root architecture and horizontal service list.

- [ ] **Step 2: Update alignment suite**

Add predicting trends to the skill suite and route future-looking business questions to it.

## Task 5: Verification

**Files:**
- All created and modified files.

- [ ] **Step 1: Run tests**

Run:

```bash
python -m pytest predicting_trends/tests/test_forecast.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI smoke test**

Run the CLI against a small JSON input and confirm stdout contains `ok: true`, a forecast row, and summary fields.

- [ ] **Step 3: Scan docs**

Run:

```bash
Select-String -Path predicting_trends\**\*.md -Pattern 'TBD|TODO|待定'
```

Expected: no matches.

- [ ] **Step 4: Check git status**

Run:

```bash
git -c safe.directory=C:/Users/Administrator/.agents/skills/super-data-analytics status --short
```

Expected: only intended `predicting_trends`, plan, and routing docs changes are part of this work. Existing unrelated worktree changes may remain untouched.
