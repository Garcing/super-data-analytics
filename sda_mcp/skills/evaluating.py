"""效果评估内核（从 evaluating-impact/scripts/impact.py 剥离）。

去 CLI/文件读/{ok} 信封；复用 sda_mcp.errors.ValidationError；
alpha/power 解析失败显式抛 ValidationError；出参扁平 dict（去 ok）。
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Mapping

from sda_mcp.errors import ValidationError

Z_BY_ALPHA = {0.1: 1.6448536269514722, 0.05: 1.959963984540054, 0.01: 2.5758293035489004}
Z_BY_POWER = {0.8: 0.8416212335729143, 0.85: 1.0364333894937898,
              0.9: 1.2815515655446004, 0.95: 1.6448536269514722}


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
    try:
        alpha = float(payload.get("alpha", 0.05))
    except (TypeError, ValueError) as exc:
        raise ValidationError("alpha must be numeric") from exc
    if not 0 < alpha < 1:
        raise ValidationError("alpha must be between 0 and 1")
    return alpha


def z_for_alpha(alpha):
    return Z_BY_ALPHA.get(round(alpha, 2), statistics.NormalDist().inv_cdf(1 - alpha / 2))


def normal_p_value(z):
    return 2 * (1 - statistics.NormalDist().cdf(abs(z)))


def wilson_interval(success, n, alpha):
    if n <= 0:
        raise ValidationError("n must be positive")
    p = success / n
    z = z_for_alpha(alpha)
    z2 = z**2
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half_width = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n) / denominator
    return {"lower": rounded(max(0.0, center - half_width)),
            "upper": rounded(min(1.0, center + half_width))}


def validate_rate_group(name, group):
    n, success = group["n"], group["success"]
    if n <= 0:
        raise ValidationError(f"{name}.n must be positive")
    if success < 0:
        raise ValidationError(f"{name}.success cannot be negative")
    if success > n:
        raise ValidationError(f"{name}.success cannot exceed {name}.n")


def validate_mean_group(name, group):
    if group["n"] <= 1:
        raise ValidationError(f"{name}.n must be greater than 1")
    if group["stddev"] < 0:
        raise ValidationError(f"{name}.stddev cannot be negative")


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
        "control_rate_ci": wilson_interval(control["success"], control["n"], alpha),
        "treatment_rate_ci": wilson_interval(treatment["success"], treatment["n"], alpha),
        "warnings": [],
    }


def analyze_ab_mean(payload):
    alpha = alpha_value(payload)
    control = require_group(payload, "control", ["n", "mean", "stddev"])
    treatment = require_group(payload, "treatment", ["n", "mean", "stddev"])
    validate_mean_group("control", control)
    validate_mean_group("treatment", treatment)

    diff = treatment["mean"] - control["mean"]
    relative = diff / control["mean"] if control["mean"] else None
    pooled_variance = (
        (control["n"] - 1) * control["stddev"] ** 2
        + (treatment["n"] - 1) * treatment["stddev"] ** 2
    ) / (control["n"] + treatment["n"] - 2)
    pooled_stddev = math.sqrt(pooled_variance)
    cohens_d = diff / pooled_stddev if pooled_stddev else None
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
        "cohens_d": rounded(cohens_d),
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
    try:
        power = float(payload.get("power", 0.8))
    except (TypeError, ValueError) as exc:
        raise ValidationError("power must be numeric") from exc
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
    sample_size = math.ceil(numerator / (mde**2))

    return {
        "ok": True,
        "analysis_type": "sample_size_rate",
        "baseline_rate": rounded(baseline),
        "minimum_detectable_effect": rounded(mde),
        # QA 2026-08-26:MDE 语义(绝对百分点差)未披露也不回显 p1,按相对提升
        # 理解样本量会差约 93 倍——显式回显推导用处理组率并在 warnings 说明口径。
        "assumed_treatment_rate": rounded(treatment),
        "alpha": alpha,
        "power": power,
        "sample_size_per_group": sample_size,
        "warnings": [
            "样本量估算为近似值；真实实验还需考虑分流、触达率、周期性和护栏指标。",
            f"minimum_detectable_effect 按绝对百分点差解释：假设处理组率 = baseline_rate + "
            f"minimum_detectable_effect = {rounded(treatment)}。",
        ],
    }


ANALYZERS = {
    "ab_rate": analyze_ab_rate, "ab_mean": analyze_ab_mean, "did": analyze_did,
    "roi": analyze_roi, "sample_size_rate": analyze_sample_size_rate,
}


def evaluate(payload: Mapping[str, Any]) -> dict[str, Any]:
    """效果评估入口。按 payload['analysis_type'] 分发，返回扁平 dict（无 ok）。"""
    analysis_type = payload.get("analysis_type")
    if analysis_type not in ANALYZERS:
        raise ValidationError(f"Unknown analysis_type: {analysis_type}")
    result = ANALYZERS[analysis_type](payload)
    result.pop("ok", None)  # 去信封（双保险：analyzer 内部若带了 ok 也清掉）
    return result
