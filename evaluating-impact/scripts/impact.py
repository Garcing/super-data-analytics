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


def wilson_interval(success, n, alpha):
    if n <= 0:
        raise ValidationError("n must be positive")
    p = success / n
    z = z_for_alpha(alpha)
    z2 = z**2
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half_width = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n) / denominator
    return {
        "lower": rounded(max(0.0, center - half_width)),
        "upper": rounded(min(1.0, center + half_width)),
    }


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
        "control_rate_ci": wilson_interval(control["success"], control["n"], alpha),
        "treatment_rate_ci": wilson_interval(treatment["success"], treatment["n"], alpha),
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
    sample_size = math.ceil(numerator / (mde**2))

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
        payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        result = run(payload)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

