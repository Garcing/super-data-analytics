"""指标异动贡献度计算内核（从 diagnosing-anomalies/scripts/contribution.py 剥离）。

去掉了 CLI/argparse/文件读/{ok} 信封；出参 dataclass；失败抛 ValidationError。
算法与原脚本一致，仅修 require_number 拒绝 bool 的 bug。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from sda_mcp.errors import ValidationError

EPS = 1e-12


@dataclass
class ContributionSummary:
    baseline_total: float
    current_total: float
    delta: float
    relative_change: float | None


@dataclass
class ContributionChecks:
    sum_contribution: float
    residual: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContributionResult:
    method: str
    summary: ContributionSummary
    rows: list[dict[str, Any]]
    checks: ContributionChecks


def safe_div(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < EPS:
        return None
    return numerator / denominator


def round_float(value: Any, digits: int = 12) -> Any:
    if isinstance(value, float):
        return round(value, digits) if math.isfinite(value) else value
    if isinstance(value, list):
        return [round_float(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: round_float(item, digits) for key, item in value.items()}
    return value


def classify_direction(value: float, total_delta: float) -> str:
    if abs(value) < EPS:
        return "无明显贡献"
    if abs(total_delta) < EPS:
        return "总变化接近0，方向不解释"
    return "同向解释" if value * total_delta > 0 else "反向抵消"


def require_number(row: Mapping[str, Any], key: str, context: str) -> float:
    """校验数字字段。bugfix：显式拒绝 bool（原实现 float(True)==1.0 会放行）。"""
    if key not in row:
        raise ValidationError(f"{context} 缺少字段: {key}")
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{context}.{key} 必须是数字")
    return float(value)


def contribution_metrics(value, total_delta, baseline_total):
    return {
        "contribution_value": value,
        "contribution_share": safe_div(value, total_delta),
        "relative_contribution": safe_div(value, baseline_total),
    }


def additive(payload: Mapping[str, Any]):
    baseline_total = float(payload.get("baseline_total", 0))
    current_total = float(payload.get("current_total", 0))
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValidationError("add 输入需要非空 items 数组")
    total_delta = current_total - baseline_total
    rows, contribution_sum = [], 0.0
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError(f"items[{idx}] 必须是对象")
        name = str(item.get("name", f"item_{idx + 1}"))
        baseline = require_number(item, "baseline", name)
        current = require_number(item, "current", name)
        value = current - baseline
        contribution_sum += value
        rows.append({
            "name": name, "baseline": baseline, "current": current, "delta": value,
            **contribution_metrics(value, total_delta, baseline_total),
            "direction": classify_direction(value, total_delta),
        })
    residual = total_delta - contribution_sum
    warnings = ["分项贡献量之和不等于总体变化，请检查分项是否互斥且完整。"] if abs(residual) > 1e-9 else []
    return _build("add", baseline_total, current_total, rows, contribution_sum, residual, warnings)


def multiplicative(payload: Mapping[str, Any]):
    factors = payload.get("factors")
    if not isinstance(factors, list) or not factors:
        raise ValidationError("multiply 输入需要非空 factors 数组")
    parsed, baseline_total, current_total = [], 1.0, 1.0
    for idx, factor in enumerate(factors):
        if not isinstance(factor, dict):
            raise ValidationError(f"factors[{idx}] 必须是对象")
        name = str(factor.get("name", f"factor_{idx + 1}"))
        baseline = require_number(factor, "baseline", name)
        current = require_number(factor, "current", name)
        if baseline <= 0 or current <= 0:
            raise ValidationError(f"{name} 的 baseline/current 必须为正数，log 拆解不能处理 0 或负数")
        baseline_total *= baseline
        current_total *= current
        parsed.append((name, baseline, current))
    total_delta = current_total - baseline_total
    log_total_delta = math.log(current_total) - math.log(baseline_total)
    log_mean_weight = None if abs(log_total_delta) < EPS else total_delta / log_total_delta
    rows, contribution_sum, warnings = [], 0.0, []
    if log_mean_weight is None:
        warnings.append("总体对数变化接近0，仅输出因子 log 变化，不计算贡献率。")
    for name, baseline, current in parsed:
        log_delta = math.log(current) - math.log(baseline)
        value = 0.0 if log_mean_weight is None else log_mean_weight * log_delta
        contribution_sum += value
        rows.append({
            "name": name, "baseline": baseline, "current": current,
            "factor_ratio": current / baseline, "log_delta": log_delta,
            "log_contribution_share": safe_div(log_delta, log_total_delta),
            **contribution_metrics(value, total_delta, baseline_total),
            "direction": classify_direction(value, total_delta),
        })
    residual = total_delta - contribution_sum if log_mean_weight is not None else total_delta
    return _build("multiply", baseline_total, current_total, rows, contribution_sum, residual, warnings)


def ratio(payload: Mapping[str, Any]):
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValidationError("ratio 输入需要非空 groups 数组")
    parsed, b_num_t, b_den_t, c_num_t, c_den_t = [], 0.0, 0.0, 0.0, 0.0
    for idx, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValidationError(f"groups[{idx}] 必须是对象")
        name = str(group.get("name", f"group_{idx + 1}"))
        b_num = require_number(group, "baseline_numerator", name)
        b_den = require_number(group, "baseline_denominator", name)
        c_num = require_number(group, "current_numerator", name)
        c_den = require_number(group, "current_denominator", name)
        if b_den <= 0 or c_den <= 0:
            raise ValidationError(f"{name} 的分母必须大于 0")
        b_num_t += b_num; b_den_t += b_den; c_num_t += c_num; c_den_t += c_den
        parsed.append((name, b_num, b_den, c_num, c_den))
    if b_den_t <= 0 or c_den_t <= 0:
        raise ValidationError("总体分母必须大于 0")
    baseline_total = b_num_t / b_den_t
    current_total = c_num_t / c_den_t
    total_delta = current_total - baseline_total
    rows, contribution_sum = [], 0.0
    for name, b_num, b_den, c_num, c_den in parsed:
        y0, y1 = b_num / b_den, c_num / c_den
        w0, w1 = b_den / b_den_t, c_den / c_den_t
        within = w0 * (y1 - y0)
        mix = (w1 - w0) * (y0 - baseline_total)
        interaction = (w1 - w0) * (y1 - y0)
        value = within + mix + interaction
        contribution_sum += value
        rows.append({
            "name": name, "baseline_numerator": b_num, "baseline_denominator": b_den,
            "current_numerator": c_num, "current_denominator": c_den,
            "baseline_rate": y0, "current_rate": y1, "baseline_weight": w0, "current_weight": w1,
            "within_contribution": within, "mix_contribution": mix, "interaction_contribution": interaction,
            **contribution_metrics(value, total_delta, baseline_total),
            "direction": classify_direction(value, total_delta),
        })
    residual = total_delta - contribution_sum
    warnings = ["比率型贡献未完全加总到总体变化，请检查分组是否互斥且分母完整。"] if abs(residual) > 1e-9 else []
    return _build("ratio", baseline_total, current_total, rows, contribution_sum, residual, warnings)


_METHODS = {"add": additive, "multiply": multiplicative, "ratio": ratio}


def _build(method, baseline_total, current_total, rows, contribution_sum, residual, warnings) -> ContributionResult:
    total_delta = current_total - baseline_total
    # 与原 build_result 一致：round_float(12 位) 作用于 summary/checks/rows 全部数值，
    # 保证对照测试与原 CLI 严格相等。
    summary_d = round_float({
        "baseline_total": baseline_total, "current_total": current_total,
        "delta": total_delta, "relative_change": safe_div(total_delta, baseline_total),
    })
    checks_d = round_float({
        "sum_contribution": contribution_sum, "residual": residual, "warnings": warnings,
    })
    return ContributionResult(
        method=method,
        summary=ContributionSummary(**summary_d),
        rows=round_float(rows),
        checks=ContributionChecks(**checks_d),
    )


def contribute(method: str, payload: Mapping[str, Any]) -> ContributionResult:
    """贡献度归因入口。method ∈ {add, multiply, ratio}。"""
    if method not in _METHODS:
        raise ValidationError(f"unknown method '{method}', expected add/multiply/ratio")
    return _METHODS[method](payload)
