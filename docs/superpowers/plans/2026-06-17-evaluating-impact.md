# evaluating-impact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first version of the `evaluating-impact/` skill for effect evaluation, A/B test checks, DID, ROI, and business action assessment.

**Architecture:** Create a method-oriented skill directory with concise Chinese agent instructions, Chinese reference guides, and one deterministic Python CLI. Keep the CLI focused on aggregate calculations while the skill text owns business judgment, assumptions, routing, and collaboration with adjacent skills.

**Tech Stack:** Markdown skill docs, Python standard library, `pytest`, JSON CLI contracts.

---

## File Structure

- Create `evaluating-impact/SKILL.md`: Chinese skill entry point, trigger scope, workflow, collaboration, script usage, and output style.
- Create `evaluating-impact/references/method-routing.md`: Chinese decision tree for selecting A/B, DID, group comparison, pre/post, ROI, or stopping.
- Create `evaluating-impact/references/ab-testing.md`: Chinese A/B test guide covering rate metrics, mean metrics, guardrails, SRM, sample size, early stopping, and CUPED as a documented but unimplemented variance-reduction option.
- Create `evaluating-impact/references/did.md`: Chinese DID guide with assumptions, data requirements, four-cell calculation, pre-trend caution, and common failures.
- Create `evaluating-impact/references/roi-and-business-actions.md`: Chinese guide for coupons, Push, launches, promotions, channel spend, ROI, cost, margin, and guardrails.
- Create `evaluating-impact/references/output-checklist.md`: Chinese final-answer self-check list.
- Create `evaluating-impact/scripts/impact.py`: Python JSON CLI implementing `ab_rate`, `ab_mean`, `did`, `roi`, and `sample_size_rate`.
- Create `evaluating-impact/tests/test_impact.py`: pytest coverage for supported calculations and validation failures.
- Modify `AGENTS.md`: add `evaluating-impact/` to the architecture and routing instructions as the third core analysis capability.

## Task 1: Add CLI Tests First

**Files:**
- Create: `evaluating-impact/tests/test_impact.py`

- [x] **Step 1: Create the failing test file**

```python
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest evaluating-impact/tests/test_impact.py -q`

Expected: FAIL because `evaluating-impact/scripts/impact.py` does not exist.

## Task 2: Implement impact.py

**Files:**
- Create: `evaluating-impact/scripts/impact.py`
- Test: `evaluating-impact/tests/test_impact.py`

- [x] **Step 1: Create the CLI implementation**

```python
#!/usr/bin/env python3
import argparse
import json
import math
import statistics
import sys
from pathlib import Path


Z_BY_ALPHA = {
    0.1: 1.6448536269514722,
    0.05: 1.959963984540054,
    0.01: 2.5758293035489004,
}

Z_BY_POWER = {
    0.8: 0.8416212335729143,
    0.85: 1.0364333894937898,
    0.9: 1.2815515655446004,
    0.95: 1.6448536269514722,
}


class ValidationError(Exception):
    pass


def rounded(value, digits=6):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    return round(float(value), digits)


def require_number(payload, key):
    if key not in payload:
        raise ValidationError(f"Missing required field: {key}")
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{key} must be numeric")
    if not math.isfinite(float(value)):
        raise ValidationError(f"{key} must be finite")
    return float(value)


def require_group(payload, key, fields):
    if key not in payload or not isinstance(payload[key], dict):
        raise ValidationError(f"{key} must be an object")
    group = payload[key]
    return {field: require_number(group, field) for field in fields}


def alpha_value(payload):
    alpha = float(payload.get("alpha", 0.05))
    if not 0 < alpha < 1:
        raise ValidationError("alpha must be between 0 and 1")
    return alpha


def z_for_alpha(alpha):
    return Z_BY_ALPHA.get(round(alpha, 2), statistics.NormalDist().inv_cdf(1 - alpha / 2))


def normal_p_value(z):
    return 2 * (1 - statistics.NormalDist().cdf(abs(z)))


def validate_rate_group(name, group):
    n = group["n"]
    success = group["success"]
    if n <= 0:
        raise ValidationError(f"{name}.n must be positive")
    if success < 0:
        raise ValidationError(f"{name}.success cannot be negative")
    if success > n:
        raise ValidationError(f"{name}.success cannot exceed {name}.n")


def analyze_ab_rate(payload):
    alpha = alpha_value(payload)
    control = require_group(payload, "control", ["n", "success"])
    treatment = require_group(payload, "treatment", ["n", "success"])
    validate_rate_group("control", control)
    validate_rate_group("treatment", treatment)

    control_rate = control["success"] / control["n"]
    treatment_rate = treatment["success"] / treatment["n"]
    lift = treatment_rate - control_rate
    relative_lift = lift / control_rate if control_rate else None
    pooled = (control["success"] + treatment["success"]) / (control["n"] + treatment["n"])
    pooled_se = math.sqrt(pooled * (1 - pooled) * (1 / control["n"] + 1 / treatment["n"]))
    z = lift / pooled_se if pooled_se else 0.0
    p_value = normal_p_value(z)
    unpooled_se = math.sqrt(
        control_rate * (1 - control_rate) / control["n"]
        + treatment_rate * (1 - treatment_rate) / treatment["n"]
    )
    margin = z_for_alpha(alpha) * unpooled_se

    return {
        "ok": True,
        "analysis_type": "ab_rate",
        "control_rate": rounded(control_rate),
        "treatment_rate": rounded(treatment_rate),
        "absolute_lift": rounded(lift),
        "relative_lift": rounded(relative_lift),
        "p_value": rounded(p_value),
        "alpha": alpha,
        "significant": p_value < alpha,
        "confidence_interval": {
            "lower": rounded(lift - margin),
            "upper": rounded(lift + margin),
        },
        "warnings": [],
    }


def validate_mean_group(name, group):
    if group["n"] <= 1:
        raise ValidationError(f"{name}.n must be greater than 1")
    if group["stddev"] < 0:
        raise ValidationError(f"{name}.stddev cannot be negative")


def analyze_ab_mean(payload):
    alpha = alpha_value(payload)
    control = require_group(payload, "control", ["n", "mean", "stddev"])
    treatment = require_group(payload, "treatment", ["n", "mean", "stddev"])
    validate_mean_group("control", control)
    validate_mean_group("treatment", treatment)

    diff = treatment["mean"] - control["mean"]
    relative = diff / control["mean"] if control["mean"] else None
    se = math.sqrt((control["stddev"] ** 2) / control["n"] + (treatment["stddev"] ** 2) / treatment["n"])
    z = diff / se if se else 0.0
    p_value = normal_p_value(z)
    margin = z_for_alpha(alpha) * se

    return {
        "ok": True,
        "analysis_type": "ab_mean",
        "control_mean": rounded(control["mean"]),
        "treatment_mean": rounded(treatment["mean"]),
        "mean_difference": rounded(diff),
        "relative_difference": rounded(relative),
        "p_value": rounded(p_value),
        "alpha": alpha,
        "significant": p_value < alpha,
        "confidence_interval": {
            "lower": rounded(diff - margin),
            "upper": rounded(diff + margin),
        },
        "warnings": ["均值检验使用正态近似；小样本或重尾分布建议做专项检验。"],
    }


def analyze_did(payload):
    treatment_before = require_number(payload, "treatment_before")
    treatment_after = require_number(payload, "treatment_after")
    control_before = require_number(payload, "control_before")
    control_after = require_number(payload, "control_after")
    treatment_change = treatment_after - treatment_before
    control_change = control_after - control_before
    effect = treatment_change - control_change
    relative = effect / treatment_before if treatment_before else None

    return {
        "ok": True,
        "analysis_type": "did",
        "treatment_change": rounded(treatment_change),
        "control_change": rounded(control_change),
        "did_effect": rounded(effect),
        "relative_did_effect": rounded(relative),
        "warnings": ["DID 计算不自动证明平行趋势；仍需检查干预前趋势和业务可比性。"],
    }


def analyze_roi(payload):
    benefit = require_number(payload, "benefit")
    cost = require_number(payload, "cost")
    if cost <= 0:
        raise ValidationError("cost must be positive")
    net_benefit = benefit - cost
    roi = net_benefit / cost
    result = {
        "ok": True,
        "analysis_type": "roi",
        "benefit": rounded(benefit),
        "cost": rounded(cost),
        "net_benefit": rounded(net_benefit),
        "roi": rounded(roi),
        "profitable": net_benefit > 0,
        "warnings": [],
    }

    if "gross_margin_rate" in payload:
        margin_rate = require_number(payload, "gross_margin_rate")
        if not 0 <= margin_rate <= 1:
            raise ValidationError("gross_margin_rate must be between 0 and 1")
        margin_benefit = benefit * margin_rate
        result["margin_adjusted_benefit"] = rounded(margin_benefit)
        result["margin_adjusted_net_benefit"] = rounded(margin_benefit - cost)
        result["margin_adjusted_roi"] = rounded((margin_benefit - cost) / cost)
        result["margin_adjusted_profitable"] = margin_benefit > cost

    if "incremental_margin" in payload:
        incremental_margin = require_number(payload, "incremental_margin")
        result["incremental_margin"] = rounded(incremental_margin)
        result["incremental_margin_roi"] = rounded((incremental_margin - cost) / cost)
        result["incremental_margin_profitable"] = incremental_margin > cost

    return result


def analyze_sample_size_rate(payload):
    baseline = require_number(payload, "baseline_rate")
    mde = require_number(payload, "minimum_detectable_effect")
    alpha = alpha_value(payload)
    power = float(payload.get("power", 0.8))
    if not 0 < baseline < 1:
        raise ValidationError("baseline_rate must be between 0 and 1")
    if mde <= 0 or baseline + mde >= 1:
        raise ValidationError("minimum_detectable_effect must be positive and keep treatment rate below 1")
    if not 0 < power < 1:
        raise ValidationError("power must be between 0 and 1")

    treatment = baseline + mde
    pooled = (baseline + treatment) / 2
    z_alpha = z_for_alpha(alpha)
    z_power = Z_BY_POWER.get(round(power, 2), statistics.NormalDist().inv_cdf(power))
    numerator = (
        z_alpha * math.sqrt(2 * pooled * (1 - pooled))
        + z_power * math.sqrt(baseline * (1 - baseline) + treatment * (1 - treatment))
    ) ** 2
    sample_size = math.ceil(numerator / (mde ** 2))

    return {
        "ok": True,
        "analysis_type": "sample_size_rate",
        "baseline_rate": rounded(baseline),
        "minimum_detectable_effect": rounded(mde),
        "alpha": alpha,
        "power": power,
        "sample_size_per_group": sample_size,
        "warnings": ["样本量估算为近似值；真实实验还需考虑分流、触达率、周期性和护栏指标。"],
    }


ANALYZERS = {
    "ab_rate": analyze_ab_rate,
    "ab_mean": analyze_ab_mean,
    "did": analyze_did,
    "roi": analyze_roi,
    "sample_size_rate": analyze_sample_size_rate,
}


def run(payload):
    analysis_type = payload.get("analysis_type")
    if analysis_type not in ANALYZERS:
        raise ValidationError(f"Unknown analysis_type: {analysis_type}")
    return ANALYZERS[analysis_type](payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate lightweight impact analysis JSON.")
    parser.add_argument("input", help="Path to input JSON file")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = run(payload)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 2: Run tests to verify the CLI passes**

Run: `python -m pytest evaluating-impact/tests/test_impact.py -q`

Expected: PASS for all tests.

## Task 3: Add Chinese Skill Entry Point

**Files:**
- Create: `evaluating-impact/SKILL.md`

- [x] **Step 1: Create `SKILL.md`**

```markdown
---
name: evaluating-impact
description: 效果评估与实验检验方法论。用于判断产品上线、运营活动、Push、发券、投放、AB 实验、DID 试点等动作是否有效、是否达到预期、ROI 是否为正、是否可以全量或加码；指导 agent 完成评估问题澄清、方法选择、显著性/效果量/护栏/ROI 判断、结论强度表达和决策建议。
---

# 效果评估与实验检验

本技能提供效果评估、实验检验和业务动作复盘的方法论，不直接负责取数或生成报告。执行中按需调用 `retrieving-context` 明确指标定义，调用 `querying-via-powerbi` 或 `querying-via-sql` 获取实验、活动、成本和指标数据，调用 `diagnosing-anomalies` 排查评估窗口内的异常干扰，调用 `predicting_trends` 判断效果是否可能延续，调用 `visualizing-data` 生成精确图表，调用 `building-report` 承接报告交付。

## 核心原则

- 先明确“评估什么动作”和“要支持什么决策”，再选择统计方法。
- 先复现指标、分流、曝光、归因窗口和成本口径，再计算效果。
- 有随机对照优先按 A/B 实验判断；没有随机对照时，不把相关性包装成强因果。
- 主指标、护栏指标和业务收益要一起看，不能只看一个提升数字。
- ROI 必须说明收入、毛利、补贴、投放、库存、退款、复购或蚕食等口径限制。
- 结论必须标注强度：强因果、较可信但依赖假设、仅方向性、无法判断。

## 触发场景

当用户问题围绕“做的事情到底有没有用”时使用本技能，例如：

- 新功能上线后点击率、转化率、留存、北极星指标有没有改善。
- A/B 实验是否显著、样本量是否够、是否可以全量。
- 发券、补贴、大促、Push、投放、线下活动的核销率、转化、ROI 是否达标。
- 城市试点、渠道策略、人群策略是否带来增量效果。
- 没有随机实验时，能不能用 DID 或可比组做更可信的评估。

如果用户只是问“为什么指标变了”，优先使用 `diagnosing-anomalies`。如果用户问“未来会怎样”或“目标怎么定”，优先使用 `predicting_trends`。如果用户问“动作有效且未来能贡献多少”，先用本技能评估历史效果，再按需进入预测。

## 默认流程

### 1. 明确评估问题

确认以下信息，缺失但不影响大方向时先做合理假设并说明；缺失会改变结论时追问。

| 项目 | 要点 |
| --- | --- |
| 动作 | 上线、实验、Push、券、活动、投放、策略、试点等 |
| 时间 | 开始时间、结束时间、观察窗口、归因窗口 |
| 人群 | 实验组/对照组、触达人群、曝光人群、可比人群 |
| 指标 | 主指标、护栏指标、成本收益指标 |
| 预期 | 预期提升方向、最小可接受效果、目标值 |
| 成本 | 补贴、投放、资源、人力、库存、机会成本 |
| 决策 | 全量、停止、继续观察、加码、复盘、分人群推进 |

### 2. 复现评估口径

计算前必须确认：

- 指标定义、分子分母、过滤条件、去重逻辑。
- 实验分流、曝光、触达和实际处理口径是否一致。
- 观察窗口是否完整，是否存在数据延迟或补数。
- 成本和收益是否同一口径，收入、毛利、净收益是否混用。
- 是否存在同期活动、节假日、投放变化、数据链路变更或产品事故。

### 3. 选择评估方法

按数据条件选择最轻量且可信的方法：

| 数据条件 | 推荐方法 | 结论强度 |
| --- | --- | --- |
| 有随机实验组和对照组 | A/B 实验检验 | 设计健康时可支持强因果 |
| 无随机，但有处理组/对照组和干预前后数据 | DID | 较可信但依赖平行趋势等假设 |
| 有处理组/对照组，但只有干预后数据 | 可比组差异 | 方向性或弱因果支持 |
| 只有处理组前后数据 | 前后对比、同比环比、漏斗、ROI | 仅方向性 |
| 样本、口径或处理定义不清 | 停止强结论 | 无法判断 |

详细路由读取 `references/method-routing.md`。

### 4. 执行对应分析

A/B 实验读取 `references/ab-testing.md`，重点检查随机性、样本量、SRM、主指标、护栏指标、效果量、置信区间、p 值、提前停止风险和业务显著性。

DID 读取 `references/did.md`，重点检查处理组/对照组可比性、干预前趋势、干预时间、同期干扰和计算双重差分。

业务动作和 ROI 读取 `references/roi-and-business-actions.md`，重点计算前后变化、可比周期变化、漏斗节点、分层效果、成本、收益、ROI 和护栏风险。

### 5. 输出决策建议

推荐结构：

```text
评估结论：<动作> 对 <主指标> 的观察效果为 <提升/下降> <幅度>。
证据：使用 <A/B/DID/前后对比/ROI>，关键结果为 <统计结果或业务结果>。
业务判断：ROI <为正/为负/无法判断>，护栏指标 <稳定/有风险/缺失>。
结论强度：<强因果/较可信但依赖假设/仅方向性/无法判断>。
建议：<全量/继续观察/扩大样本/停止/补充数据/分人群推进>。
限制：<样本量、非随机、同期干扰、数据口径、观察窗口、成本口径>。
```

最终输出前读取 `references/output-checklist.md` 做自检。

## 内置脚本

当已经拿到结构化聚合数据时，可用本地脚本做确定性轻量计算：

```bash
python evaluating-impact/scripts/impact.py <input.json>
```

支持类型：

- `ab_rate`：点击率、转化率、核销率、留存率等二项率。
- `ab_mean`：客单价、人均收入、人均时长等均值。
- `did`：处理组/对照组在干预前后的双重差分。
- `roi`：收益、成本、净收益、ROI、毛利口径 ROI。
- `sample_size_rate`：二项率 A/B 实验的粗略样本量估算。

脚本只负责计算和输入校验。业务口径、实验设计、平行趋势、护栏指标、ROI 成本完整性和最终决策仍由 agent 判断。

## 与其他技能协作

- 需要指标定义、业务层级、表名、实验命名：调用 `retrieving-context`。
- 需要 Power BI 语义模型取数：调用 `querying-via-powerbi`。
- 需要 SQL 明细或聚合取数：调用 `querying-via-sql`。
- 发现评估窗口内存在异常波动或数据质量问题：调用 `diagnosing-anomalies`。
- 需要判断效果延续、目标影响或未来收益：调用 `predicting_trends`。
- 需要精确图表：调用 `visualizing-data`。
- 需要沉淀成报告：调用 `building-report`。
```

- [x] **Step 2: Verify skill frontmatter is readable**

Run: `Get-Content -Raw evaluating-impact/SKILL.md`

Expected: File begins with YAML frontmatter containing `name: evaluating-impact`.

## Task 4: Add Chinese Reference Guides

**Files:**
- Create: `evaluating-impact/references/method-routing.md`
- Create: `evaluating-impact/references/ab-testing.md`
- Create: `evaluating-impact/references/did.md`
- Create: `evaluating-impact/references/roi-and-business-actions.md`
- Create: `evaluating-impact/references/output-checklist.md`

- [x] **Step 1: Create `method-routing.md`**

```markdown
# 方法选择路由

效果评估先判断数据条件，再选择方法。不要因为知道某个模型名字就硬套。

## 决策树

1. 是否有明确动作？
   - 没有：不是效果评估，优先走异动归因或需求对齐。
   - 有：继续。

2. 是否有随机分配的实验组和对照组？
   - 有：走 A/B 实验。
   - 没有：继续。

3. 是否有处理组、可比对照组，以及干预前后数据？
   - 有：优先 DID。
   - 没有：继续。

4. 是否至少有处理组和对照组的干预后数据？
   - 有：做可比组差异，但结论强度较弱。
   - 没有：继续。

5. 是否只有处理组前后数据？
   - 有：做前后对比、同比环比、漏斗和 ROI，结论标注为方向性。
   - 没有：停止强结论，说明缺什么数据。

## 方法和结论强度

| 数据条件 | 推荐方法 | 可以支持的结论 |
| --- | --- | --- |
| 随机实验，分流健康，样本足够 | A/B 实验 | 强因果证据 |
| 非随机，但有可比对照和前后数据 | DID | 较可信但依赖假设 |
| 只有处理组和对照组后验数据 | 组间差异 | 方向性或弱因果 |
| 只有处理组前后数据 | 前后对比/同比环比 | 方向性 |
| 只有收益和成本 | ROI | 投入产出判断，不证明因果 |

## 必问问题

- 这个动作影响了谁，没有影响谁？
- 对照组是随机来的，还是自然形成的？
- 干预前两组是否已经不同？
- 是否存在同期活动、节假日、投放、价格、库存或数据口径变化？
- 主指标提升时，护栏指标是否变差？
- 当前数据是否足够支持用户要做的决策？
```

- [x] **Step 2: Create `ab-testing.md`**

```markdown
# A/B 实验检验

A/B 实验用于随机分流条件下判断处理是否带来指标变化。它既要看统计显著，也要看业务显著和护栏风险。

## 分析前检查

- 实验组和对照组是否随机分配。
- 分流比例是否符合预期，是否存在 SRM。
- 用户是否可能跨组污染。
- 主指标是否提前定义，是否存在事后挑指标。
- 观察窗口是否完整，是否提前停止。
- 样本量、成功数或事件数是否足够。
- 护栏指标是否覆盖留存、收入质量、投诉、退款、性能等关键风险。

## 比率指标

适合点击率、转化率、核销率、留存率等。

关注：

- 对照组率值。
- 实验组率值。
- 绝对提升。
- 相对提升。
- p 值和置信区间。
- 最小业务可接受提升。

## 均值指标

适合客单价、人均收入、人均时长、人均次数等。

关注：

- 均值差。
- 标准差和样本量。
- 是否有极端值或重尾分布。
- 是否需要分位数、截尾均值或专项检验辅助解释。

## 不显著时怎么说

不显著不等于没有效果，常见含义包括：

- 样本量不足。
- 真实效果小于当前可检测范围。
- 指标噪声大。
- 实验周期太短。
- 处理确实没有明显效果。

如果业务急着上线，应给出决策选项：继续实验、扩大样本、只对低风险人群放量、基于护栏小流量灰度、或停止。

## CUPED

CUPED 是 A/B 实验中的方差降低方法。它利用实验前就存在、且不受实验影响的用户级协变量，对实验后指标做校正，从而提高检验灵敏度。

适合条件：

- 有用户级或样本级实验前指标。
- 实验前指标和实验后主指标相关。
- 协变量不受实验影响。
- 缺失值、异常值和分组口径可控。

第一版 `impact.py` 不实现 CUPED。遇到需要 CUPED 的高价值实验，应作为专项明细数据分析处理。
```

- [x] **Step 3: Create `did.md`**

```markdown
# 双重差分法 DID

DID 用于没有随机实验，但存在处理组、对照组、干预前和干预后数据的场景。它估计的是处理组变化扣除对照组同期变化后的增量。

## 四格结构

| 组别 | 干预前 | 干预后 |
| --- | --- | --- |
| 处理组 | treatment_before | treatment_after |
| 对照组 | control_before | control_after |

计算：

```text
处理组变化 = treatment_after - treatment_before
对照组变化 = control_after - control_before
DID 效果 = 处理组变化 - 对照组变化
```

## 适用场景

- 城市试点策略。
- 分区域活动。
- 渠道政策变化。
- 分批上线功能。
- 某类用户受到策略影响，另一类相近用户未受影响。

## 关键假设

最重要的是平行趋势：如果没有干预，处理组和对照组本应保持相近走势。

不能只靠公式证明平行趋势，需要检查：

- 干预前多期趋势是否接近。
- 两组业务结构是否相似。
- 同期是否有只影响某一组的活动或事故。
- 是否存在用户迁移、污染或组成变化。

## 何时降低结论强度

- 干预前趋势已经明显分叉。
- 对照组业务上不可比。
- 干预时间不清楚。
- 同期存在重大活动、价格、库存或投放差异。
- 只有一个前置周期，无法观察趋势。
- 处理组和对照组样本构成变化明显。
```

- [x] **Step 4: Create `roi-and-business-actions.md`**

```markdown
# 业务动作和 ROI 评估

业务动作评估不仅看指标涨没涨，还要看收益是否覆盖成本，以及有没有伤害长期价值。

## 通用框架

- 动作：做了什么，影响谁，什么时候发生。
- 主指标：希望提升什么。
- 护栏指标：不能伤害什么。
- 成本：补贴、投放、人力、库存、机会成本。
- 收益：收入、毛利、净收益、留存、复购、长期价值。
- 增量：哪些收益可能本来就会发生。
- 决策：继续、停止、加码、全量、分人群推进。

## 发券和补贴

关注：

- 发券数、领取数、使用数、核销率。
- 被券带动的订单和 GMV。
- 补贴成本。
- 毛利和净收益。
- 原本会购买用户的蚕食。
- 券后复购和价格敏感风险。

## Push 和消息

关注：

- 发送、送达、打开、点击、转化。
- 次日留存、退订、投诉、卸载。
- 频控和疲劳。
- 是否只提升短期点击，伤害长期活跃。

## 产品上线

关注：

- 曝光和使用率。
- 漏斗转化。
- 北极星指标。
- 留存和收入质量。
- 性能、投诉、退款、客服等护栏。
- 新老用户、渠道、设备、版本分层。

## ROI 口径

```text
净收益 = 收益 - 成本
ROI = 净收益 / 成本
毛利口径收益 = 收入 * 毛利率
毛利口径 ROI = (毛利口径收益 - 成本) / 成本
```

最终必须说明 ROI 使用的是收入、毛利、贡献毛利还是净利润口径。
```

- [x] **Step 5: Create `output-checklist.md`**

```markdown
# 输出自检清单

最终回答前逐项检查。

## 口径

- 是否说明了动作、时间、人群和指标。
- 是否说明了分子、分母、去重、曝光、归因窗口。
- 是否说明了成本和收益口径。

## 方法

- 是否根据数据条件选择方法。
- 是否说明为什么用 A/B、DID、可比组、前后对比或 ROI。
- 是否没有把相关性说成强因果。
- DID 是否提醒平行趋势和可比性。
- A/B 是否检查样本、显著性、效果量和护栏。

## 结论

- 是否给出效果大小，而不只说涨跌。
- 是否区分统计显著和业务显著。
- 是否标注结论强度。
- 是否说明护栏指标是否安全。
- ROI 是否为正，以及是否说明口径限制。

## 决策

- 是否给出可执行建议。
- 是否说明继续观察、扩大样本、停止、全量或分人群推进的条件。
- 是否列出还需要补充的数据。
```

- [x] **Step 6: Verify all reference files exist**

Run: `Get-ChildItem evaluating-impact/references -Name`

Expected: Shows five markdown files.

## Task 5: Update Root Routing

**Files:**
- Modify: `AGENTS.md`

- [x] **Step 1: Update architecture and routing text**

Modify `AGENTS.md` so the architecture block includes:

```text
evaluating-impact/              效果评估与实验检验方法论
```

Add `evaluating-impact` to horizontal services:

```markdown
- `evaluating-impact`：产品上线、运营活动、Push、发券、投放、AB 实验、DID 试点等需要判断“动作是否有效、ROI 是否为正、是否可以全量/加码/停止”时使用。
```

Add it to the three-core-capabilities note:

```markdown
互联网数据分析三大能力：
- `diagnosing-anomalies`：异动归因，回答“为什么变了”。
- `predicting_trends`：趋势预测和目标制定，回答“未来会怎样 / 目标怎么定”。
- `evaluating-impact`：效果评估和实验检验，回答“做的事情有没有用 / 是否值得继续”。
```

- [x] **Step 2: Verify routing text is present**

Run: `Select-String -Path AGENTS.md -Pattern 'evaluating-impact|互联网数据分析三大能力'`

Expected: Finds the new routing entries.

## Task 6: Full Verification

**Files:**
- Test: `evaluating-impact/tests/test_impact.py`
- Inspect: `evaluating-impact/SKILL.md`
- Inspect: `evaluating-impact/references/*.md`
- Inspect: `AGENTS.md`

- [x] **Step 1: Run focused tests**

Run: `python -m pytest evaluating-impact/tests/test_impact.py -q`

Expected: all tests pass.

- [x] **Step 2: Run script smoke tests manually**

Create a temporary JSON file:

```json
{
  "analysis_type": "roi",
  "benefit": 1200000,
  "cost": 300000,
  "gross_margin_rate": 0.4
}
```

Run: `python evaluating-impact/scripts/impact.py <temp-json-path>`

Expected: JSON contains `"ok": true`, `"roi": 3.0`, and `"margin_adjusted_roi": 0.6`.

- [x] **Step 3: Check git diff scope**

Run: `git diff -- evaluating-impact AGENTS.md docs/superpowers/plans/2026-06-17-evaluating-impact.md`

Expected: diff only contains the new skill, root routing update, and this implementation plan.

- [x] **Step 4: Commit implementation**

```bash
git add evaluating-impact AGENTS.md docs/superpowers/plans/2026-06-17-evaluating-impact.md
git commit -m "feat: add evaluating-impact skill"
```

Expected: commit succeeds and does not include unrelated `predicting_trends` changes.

## Self-Review

- Spec coverage: plan covers skill entry point, five references, script, tests, and root routing.
- Scope control: first version supports only aggregate A/B, DID, ROI, and sample-size calculations. CUPED is documented but not implemented.
- Placeholder scan: no placeholder tasks remain; each implementation task names exact files, commands, and expected outcomes.
- Type consistency: analysis types are consistently named `ab_rate`, `ab_mean`, `did`, `roi`, and `sample_size_rate`.
