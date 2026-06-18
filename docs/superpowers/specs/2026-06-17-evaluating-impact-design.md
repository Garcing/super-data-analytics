# evaluating-impact Skill Design

## Goal

Add a reusable `evaluating-impact/` skill for effect evaluation, business impact assessment, and experiment decision support. The skill should help an agent answer questions such as whether a product launch worked, whether a campaign produced positive ROI, whether an A/B test is significant enough to ship, or whether a non-random rollout likely created incremental business value.

This skill sits in the analysis layer. It complements `diagnosing-anomalies` and `predicting_trends`: anomaly diagnosis explains why a metric changed; trend prediction estimates what may happen next; impact evaluation estimates whether a specific action caused or likely contributed to an observed result.

The first version should be practical for internet business analysis. It should favor clear business questions, lightweight statistical checks, explicit assumptions, guardrail metrics, and decision-ready conclusions over a broad causal inference toolkit.

## Non-Goals

- Do not make `evaluating-impact` responsible for retrieving metric definitions or querying data. Existing skills own context and data access.
- Do not build a full experimentation platform.
- Do not implement advanced causal methods such as propensity score matching, synthetic control, regression discontinuity, Bayesian experiments, sequential testing, or multi-test correction in the first version.
- Do not implement CUPED in the first script version. The skill should mention CUPED as an A/B test variance-reduction technique, but leave implementation for a later user-level data workflow.
- Do not present a directionally positive movement as proven causal impact unless the evaluation design supports that conclusion.
- Do not judge ROI from revenue alone when cost, margin, subsidy, or cannibalization materially changes the answer.

## Architecture

Create a new skill directory:

```text
evaluating-impact/
  SKILL.md
  references/
    method-routing.md
    ab-testing.md
    did.md
    roi-and-business-actions.md
    output-checklist.md
  scripts/
    impact.py
  tests/
    test_impact.py
```

`SKILL.md` stays concise. It tells agents when to use the skill, the default impact-evaluation workflow, which reference file to read for each evaluation design, and how to collaborate with adjacent skills.

`references/` holds the reusable method library. It should explain how to choose an evaluation path, run A/B test checks, use DID responsibly, evaluate business actions and ROI, and self-check final conclusions.

`scripts/impact.py` is the stable CLI entry point for deterministic lightweight calculations. It accepts an input JSON file and writes machine-readable JSON to stdout. The script should be small and dependency-light so it remains maintainable inside the skill.

## Trigger Scope

Use this skill when the user asks whether a specific action worked, whether an experiment is safe to ship, or what business value an intervention created. Example questions:

- "新版首页上线一周了，整体点击率提升了多少？对北极星指标有负面影响吗？"
- "这次双十一发了 100 万的券，核销率多少？ROI 能算正吗？"
- "AB 实验的数据现在看起来还不显著，但业务急着上线，能强行全量吗？"
- "Push 发完后次日留存提升了吗？"
- "某城市试点策略有没有带来真实增量？"
- "活动 GMV 涨了，但是不是本来就会涨？"
- "这个功能上线后转化率涨了，能说是功能带来的吗？"

If the user asks why a metric changed without naming a specific action to evaluate, use `diagnosing-anomalies`. If the user asks what will happen next or how to set a future target, use `predicting_trends`. If the user asks whether a past action will continue to pay off, evaluate the action first, then use trend prediction only when a forward-looking estimate is needed.

## Skill Collaboration

The skill should not directly query data. It should coordinate with:

- `retrieving-context` for metric definitions, business hierarchy, table names, experiment names, event definitions, and known launch or campaign context.
- `querying-via-powerbi` or `querying-via-sql` for experiment aggregates, user-level samples, time series, cohort data, and cost or revenue data.
- `diagnosing-anomalies` when the evaluation window contains abnormal movement, data-quality risk, or concurrent metric shifts that could confound the result.
- `predicting_trends` when the question depends on future continuation, target setting, or extrapolating observed impact.
- `visualizing-data` for experiment result charts, pre/post trend charts, DID comparison charts, funnel charts, and ROI breakdowns.
- `building-report` when the evaluation should be delivered as a formal report, dashboard, PDF, image, web page, or Feishu document.

## Default Workflow

1. Clarify the action and decision.

   Confirm the evaluated action, launch or campaign window, affected population, expected direction, primary metric, guardrail metrics, cost, and business decision. The decision might be ship, stop, continue observing, expand rollout, repeat campaign, or allocate more budget.

2. Reproduce the evaluation definition.

   Confirm metric definitions, numerator and denominator, exposure or treatment definition, attribution window, deduplication logic, exclusion rules, data freshness, and whether the latest period is complete.

3. Route by evaluation design.

   Use the lightest credible method supported by the data:

   - Randomized treatment and control groups: use A/B testing.
   - Non-random treatment and comparison groups with before and after data: prefer DID.
   - Treatment and comparison groups with only post-treatment data: compare groups, but label the conclusion weaker.
   - Only treatment before and after data: use pre/post,同比/环比, funnel, segmentation, and ROI checks; label the result directional.
   - Insufficient data or unclear treatment definition: stop strong claims and state what data is needed.

4. Run the appropriate analysis.

   For A/B tests, check randomization health, sample size, sample ratio mismatch, primary metric, guardrails, effect size, confidence interval, p-value, and whether the result is robust enough for the requested decision.

   For DID, check whether treatment and control groups are comparable, whether pre-period trends are directionally close, whether the intervention timing is clear, and whether major concurrent events differ by group. Calculate the double difference, but do not claim the parallel trends assumption is proven by the calculation alone.

   For business action evaluation, calculate pre/post change, comparable period change, funnel shifts, segment effects, cost, gross or net benefit, ROI, and guardrail changes. Explicitly separate observed movement from estimated incremental effect.

5. Produce a decision-ready conclusion.

   Final output should include effect size, statistical judgment, business judgment, guardrail status, ROI when relevant, conclusion strength, and recommended action. The conclusion strength should use plain labels such as strong causal evidence, credible but assumption-dependent, directional only, or cannot judge.

6. Self-check the answer.

   Before finalizing, check that the answer does not turn correlation into causation, ignore guardrails, use incomplete periods as complete periods, overstate insignificant results, overlook sample size, or compute ROI without relevant cost and margin assumptions.

## Method Routing

The method-routing reference should act as the skill's decision tree. It should help an agent ask:

- Was assignment randomized?
- Is there a valid control group?
- Is there both pre-period and post-period data?
- Are the treatment and control populations comparable?
- Is the metric a rate, mean, count, revenue, margin, or funnel metric?
- Is the business decision about significance, launch safety, ROI, or strategic direction?
- Are guardrail metrics required before recommending rollout?

Recommended routing:

| Data condition | Recommended method | Conclusion strength |
| --- | --- | --- |
| Randomized treatment/control groups | A/B test | Strong causal evidence if design is healthy |
| Non-random treatment/control groups with pre/post data | DID | Credible but assumption-dependent |
| Treatment/control groups only after action | Group comparison | Directional or weak causal support |
| Only before/after for treated group | Pre/post and comparable-period checks | Directional only |
| Cost and benefit available | ROI overlay | Business value judgment, not causal proof by itself |
| Insufficient sample, unclear treatment, or missing metric definition | Stop and request data | Cannot judge |

## A/B Testing

The A/B testing reference should cover daily decision support rather than experimentation-platform depth:

- Primary metric and guardrail metric setup.
- Rate metrics such as CTR, conversion rate, retention rate, and coupon redemption rate.
- Mean metrics such as ARPU, average order value, session duration, and per-user activity count.
- Absolute lift, relative lift, p-value, confidence interval, and practical significance.
- Sample ratio mismatch as a randomization health check.
- Sample size and power as planning tools, not guarantees.
- Early stopping risk and why "not significant yet" should not automatically become "safe to ship."
- Guardrail interpretation when the primary metric improves but north-star, retention, revenue quality, complaint rate, latency, or refund rate worsens.
- CUPED as a variance-reduction option when user-level pre-period covariates are available and unaffected by treatment. The first version should mention when to consider it, but should not implement it in `impact.py`.

Recommended A/B output:

```text
实验结论：<实验组> 相比 <对照组>，<主指标> <上升/下降> <绝对变化>，相对变化 <相对变化>。
统计判断：p=<p 值>，<显著/不显著/样本不足>，置信区间为 <区间>。
业务判断：护栏指标 <无明显风险/存在风险>，实际效果 <达到/未达到> 最小业务可接受提升。
建议：<全量/继续观察/扩大样本/停止/只对某人群放量>。
限制：<样本量、提前停止、SRM、数据口径、观察窗口>。
```

## DID

The DID reference should be practical and cautious. It should cover:

- Treatment group, control group, pre-period, and post-period definitions.
- Why DID subtracts the control group's concurrent movement from the treatment group's movement.
- Parallel trends as an assumption that must be argued from pre-period data and business context.
- Common use cases: city rollout, channel policy, user segment strategy, regional campaign, phased launch.
- Common failure modes: treatment and control groups already diverging before launch, different concurrent campaigns, spillover between groups, treatment timing ambiguity, and changing composition.
- When to stop at directional analysis instead of presenting DID as credible.

The first version script should calculate aggregate DID from four values. It should not fit panel regressions or support staggered adoption.

## Business Actions and ROI

The ROI and business-actions reference should cover common business evaluation patterns:

- Coupon campaigns: issuance, redemption, incremental orders, subsidy cost, gross margin, cannibalization, and repeat purchase.
- Push or messaging: send population, open/click/conversion, unsubscribe or complaint guardrails, incremental conversion, and frequency fatigue.
- Product launches: exposure, adoption, funnel conversion, retention, north-star metrics, latency or quality guardrails.
- Promotions and shopping festivals: revenue, margin, stock, user acquisition, retention, and comparable calendar windows.
- Channel spend: cost, attributed revenue, incrementality risk, CAC, payback, and saturation.

ROI calculations should support both simple revenue ROI and margin-adjusted ROI. The final answer must state which profit or revenue basis was used.

## CLI Input Contract

The impact script accepts one JSON file with an `analysis_type`:

```json
{
  "analysis_type": "ab_rate",
  "alpha": 0.05,
  "control": { "n": 10000, "success": 1200 },
  "treatment": { "n": 9800, "success": 1290 }
}
```

Supported first-version analysis types:

- `ab_rate`
- `ab_mean`
- `did`
- `roi`
- `sample_size_rate`

`ab_rate` requires treatment and control sample sizes and success counts. It should validate that sample sizes are positive and success counts are within sample sizes.

`ab_mean` requires treatment and control sample sizes, means, and standard deviations. It should validate positive sample sizes and non-negative standard deviations.

`did` requires `treatment_before`, `treatment_after`, `control_before`, and `control_after`. It may optionally accept baseline denominators for relative interpretation.

`roi` requires `benefit` and `cost`, and may optionally accept `gross_margin_rate` or `incremental_margin`.

`sample_size_rate` requires `baseline_rate`, `minimum_detectable_effect`, `alpha`, and `power`.

## CLI Output Contract

The command writes JSON to stdout. Example for `ab_rate`:

```json
{
  "ok": true,
  "analysis_type": "ab_rate",
  "control_rate": 0.12,
  "treatment_rate": 0.1316,
  "absolute_lift": 0.0116,
  "relative_lift": 0.0967,
  "p_value": 0.014,
  "alpha": 0.05,
  "significant": true,
  "confidence_interval": {
    "lower": 0.0023,
    "upper": 0.0209
  },
  "warnings": []
}
```

Example for `roi`:

```json
{
  "ok": true,
  "analysis_type": "roi",
  "benefit": 1200000,
  "cost": 300000,
  "net_benefit": 900000,
  "roi": 3.0,
  "profitable": true,
  "warnings": []
}
```

Failures return non-zero and write compact JSON:

```json
{
  "ok": false,
  "error": "treatment.success cannot exceed treatment.n"
}
```

## Supported Calculations

`ab_rate` should calculate:

- Control and treatment rates.
- Absolute and relative lift.
- Two-proportion z-test p-value.
- Approximate confidence interval for the rate difference.
- Significance against alpha.

`ab_mean` should calculate:

- Control and treatment means.
- Absolute and relative difference.
- Welch-style t-test p-value or a normal approximation if dependencies are intentionally kept minimal.
- Approximate confidence interval for the mean difference.
- Significance against alpha.

`did` should calculate:

- Treatment change.
- Control change.
- DID effect.
- Relative DID effect when a meaningful baseline is available.
- A warning that DID credibility still depends on pre-trend and business comparability checks.

`roi` should calculate:

- Net benefit.
- ROI.
- Profitability or payback status.
- Margin-adjusted values when margin input is supplied.

`sample_size_rate` should calculate:

- Approximate per-group sample size for detecting a rate change.
- The assumed baseline rate, minimum detectable effect, alpha, and power.
- Warnings when assumptions are outside normal ranges.

## Output Style

Recommended response structure:

```text
评估结论：<动作> 对 <主指标> 的观察效果为 <提升/下降> <幅度>。
证据：使用 <A/B/DID/前后对比/ROI>，关键结果为 <统计结果或业务结果>。
业务判断：ROI <为正/为负/无法判断>，护栏指标 <稳定/有风险/缺失>。
结论强度：<强因果/较可信但依赖假设/仅方向性/无法判断>。
建议：<全量/继续观察/扩大样本/停止/补充数据/分人群推进>。
限制：<样本量、非随机、同期干扰、数据口径、观察窗口、成本口径>。
```

When the user asks whether to force a launch from an insignificant A/B test, the answer should separate statistical evidence, business risk, and decision options. It should not treat "not significant" as proof of no effect, and should not treat urgency as evidence of positive effect.

## Validation and Uncertainty

The skill must avoid false certainty. It should check:

- Whether treatment assignment was randomized or self-selected.
- Whether exposure and treatment definitions are stable.
- Whether the observation window is long enough for the metric.
- Whether sample sizes and event counts are adequate.
- Whether guardrail metrics are present.
- Whether treatment and control groups differ before the action.
- Whether a shopping festival, holiday, campaign, data pipeline change, pricing change, or product incident occurred during the evaluation window.
- Whether ROI uses revenue, gross margin, contribution margin, or net profit.
- Whether long-term effects such as retention, repeat purchase, fatigue, or cannibalization are unknown.

Conclusion strength labels:

- Strong causal evidence: randomized experiment is healthy, sample size is adequate, primary and guardrail metrics support the same decision.
- Credible but assumption-dependent: DID or comparable-control analysis is plausible and major assumptions are checked.
- Directional only: pre/post or post-only comparison suggests a movement but cannot isolate causality.
- Cannot judge: missing control, missing metric definition, insufficient sample, incomplete period, or major confounding risk.

## Error Handling

Validation errors should be clear enough for an agent to fix the input:

- Missing required fields.
- Unknown analysis type.
- Non-numeric values.
- Zero or negative sample size.
- Success count greater than sample size.
- Invalid rate outside `[0, 1]`.
- Negative cost when not explicitly allowed.
- Missing before or after values for DID.
- Alpha or power outside valid ranges.

Warnings should not fail the run, but should be propagated into the final business answer.

## Testing

Use focused tests for the first release:

- `ab_rate` detects a significant lift on a known example.
- `ab_rate` returns non-significant on a small or close-difference example.
- `ab_rate` rejects success counts greater than sample size.
- `ab_mean` calculates mean difference and returns a p-value and confidence interval.
- `did` returns the expected double difference from four aggregate values.
- `roi` returns positive ROI and net benefit when benefit exceeds cost.
- `roi` handles negative or zero-benefit cases.
- `sample_size_rate` returns a positive integer per-group sample size.
- CLI stdout is valid JSON on success and failure.
- Unknown analysis types fail with a clear error.

The tests should validate calculation behavior and contract shape, not chase advanced statistical perfection.

## Integration Notes

Update the root skill routing documentation so `evaluating-impact` is listed as one of the three core internet data-analysis capabilities:

- `diagnosing-anomalies`: why a metric changed.
- `predicting_trends`: what may happen next or how to set a target.
- `evaluating-impact`: whether an action worked and what decision to make.

The root routing should direct requests about experiments, product launches, campaigns, coupons, push messages, promotions, ROI, and quasi-experiment evaluation to this skill after requirement alignment unless the user already provides clear metrics, groups, windows, and data.

## Acceptance Criteria

- `evaluating-impact/SKILL.md` exists and clearly defines trigger scope, workflow, collaboration, output style, and script usage.
- Reference files exist for method routing, A/B testing, DID, business actions and ROI, and output self-checking.
- `scripts/impact.py` runs from the repository root and returns JSON for valid and invalid inputs.
- Tests cover first-version calculations and common validation failures.
- Root routing documentation includes `evaluating-impact` as the third core analysis capability alongside anomaly diagnosis and trend prediction.
- CUPED is documented as an A/B variance-reduction method but not implemented in the first script version.
- The first version remains understandable to a business analyst and does not require advanced causal inference background to use responsibly.
