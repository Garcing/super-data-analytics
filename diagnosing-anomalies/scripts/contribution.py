#!/usr/bin/env python
"""指标异动贡献度计算器。

支持三类稳定、常用的拆解：
1. add：加法型 Delta 法
2. multiply：乘法型 log/LMDI 拆解
3. ratio：比率型组间组内拆解
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


EPS = 1e-12


def safe_div(numerator: float, denominator: float) -> float | None:
    """安全除法：分母接近 0 时返回 None，避免制造伪精确。"""
    if abs(denominator) < EPS:
        return None
    return numerator / denominator


def round_float(value: Any, digits: int = 12) -> Any:
    """统一输出精度，让 JSON 更易读，同时保留足够计算精度。"""
    if isinstance(value, float):
        if math.isfinite(value):
            return round(value, digits)
        return value
    if isinstance(value, list):
        return [round_float(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: round_float(item, digits) for key, item in value.items()}
    return value


def classify_direction(value: float, total_delta: float) -> str:
    """解释贡献方向：同向是解释/拉动，反向是抵消。"""
    if abs(value) < EPS:
        return "无明显贡献"
    if abs(total_delta) < EPS:
        return "总变化接近0，方向不解释"
    return "同向解释" if value * total_delta > 0 else "反向抵消"


def require_number(row: dict[str, Any], key: str, context: str) -> float:
    if key not in row:
        raise ValueError(f"{context} 缺少字段: {key}")
    try:
        return float(row[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context}.{key} 必须是数字") from exc


def contribution_metrics(value: float, total_delta: float, baseline_total: float) -> dict[str, float | None]:
    """计算三类核心口径：贡献量、贡献率、相对贡献。"""
    return {
        "contribution_value": value,
        "contribution_share": safe_div(value, total_delta),
        "relative_contribution": safe_div(value, baseline_total),
    }


def additive(payload: dict[str, Any]) -> dict[str, Any]:
    baseline_total = float(payload.get("baseline_total", 0))
    current_total = float(payload.get("current_total", 0))
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("add 输入需要非空 items 数组")

    total_delta = current_total - baseline_total
    rows = []
    contribution_sum = 0.0

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"items[{idx}] 必须是对象")
        name = str(item.get("name", f"item_{idx + 1}"))
        baseline = require_number(item, "baseline", name)
        current = require_number(item, "current", name)
        value = current - baseline
        contribution_sum += value

        rows.append(
            {
                "name": name,
                "baseline": baseline,
                "current": current,
                "delta": value,
                **contribution_metrics(value, total_delta, baseline_total),
                "direction": classify_direction(value, total_delta),
            }
        )

    residual = total_delta - contribution_sum
    warnings = []
    if abs(residual) > 1e-9:
        warnings.append("分项贡献量之和不等于总体变化，请检查分项是否互斥且完整。")

    return build_result("add", baseline_total, current_total, rows, contribution_sum, residual, warnings)


def multiplicative(payload: dict[str, Any]) -> dict[str, Any]:
    factors = payload.get("factors")
    if not isinstance(factors, list) or not factors:
        raise ValueError("multiply 输入需要非空 factors 数组")

    parsed = []
    baseline_total = 1.0
    current_total = 1.0
    for idx, factor in enumerate(factors):
        if not isinstance(factor, dict):
            raise ValueError(f"factors[{idx}] 必须是对象")
        name = str(factor.get("name", f"factor_{idx + 1}"))
        baseline = require_number(factor, "baseline", name)
        current = require_number(factor, "current", name)
        if baseline <= 0 or current <= 0:
            raise ValueError(f"{name} 的 baseline/current 必须为正数，log 拆解不能处理 0 或负数")
        baseline_total *= baseline
        current_total *= current
        parsed.append((name, baseline, current))

    total_delta = current_total - baseline_total
    log_total_delta = math.log(current_total) - math.log(baseline_total)

    # LMDI 的对数平均权重，把 log 贡献换回原指标单位。
    if abs(log_total_delta) < EPS:
        log_mean_weight = None
    else:
        log_mean_weight = total_delta / log_total_delta

    rows = []
    contribution_sum = 0.0
    warnings = []
    if log_mean_weight is None:
        warnings.append("总体对数变化接近0，仅输出因子 log 变化，不计算贡献率。")

    for name, baseline, current in parsed:
        log_delta = math.log(current) - math.log(baseline)
        value = 0.0 if log_mean_weight is None else log_mean_weight * log_delta
        contribution_sum += value

        row = {
            "name": name,
            "baseline": baseline,
            "current": current,
            "factor_ratio": current / baseline,
            "log_delta": log_delta,
            "log_contribution_share": safe_div(log_delta, log_total_delta),
            **contribution_metrics(value, total_delta, baseline_total),
            "direction": classify_direction(value, total_delta),
        }
        rows.append(row)

    residual = total_delta - contribution_sum if log_mean_weight is not None else total_delta
    return build_result("multiply", baseline_total, current_total, rows, contribution_sum, residual, warnings)


def ratio(payload: dict[str, Any]) -> dict[str, Any]:
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("ratio 输入需要非空 groups 数组")

    parsed = []
    baseline_num_total = 0.0
    baseline_den_total = 0.0
    current_num_total = 0.0
    current_den_total = 0.0

    for idx, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"groups[{idx}] 必须是对象")
        name = str(group.get("name", f"group_{idx + 1}"))
        b_num = require_number(group, "baseline_numerator", name)
        b_den = require_number(group, "baseline_denominator", name)
        c_num = require_number(group, "current_numerator", name)
        c_den = require_number(group, "current_denominator", name)
        if b_den <= 0 or c_den <= 0:
            raise ValueError(f"{name} 的分母必须大于 0")

        baseline_num_total += b_num
        baseline_den_total += b_den
        current_num_total += c_num
        current_den_total += c_den
        parsed.append((name, b_num, b_den, c_num, c_den))

    if baseline_den_total <= 0 or current_den_total <= 0:
        raise ValueError("总体分母必须大于 0")

    baseline_total = baseline_num_total / baseline_den_total
    current_total = current_num_total / current_den_total
    total_delta = current_total - baseline_total

    rows = []
    contribution_sum = 0.0

    for name, b_num, b_den, c_num, c_den in parsed:
        y0 = b_num / b_den
        y1 = c_num / c_den
        w0 = b_den / baseline_den_total
        w1 = c_den / current_den_total

        # 基期权重拆解：
        # 组内贡献看“结构不变时，分组自身率值变化的影响”。
        within = w0 * (y1 - y0)
        # 结构贡献看“分组占比变化时，该组相对大盘基准率的高低”。
        mix = (w1 - w0) * (y0 - baseline_total)
        # 交叉项处理率值和占比同时变化的共同影响。
        interaction = (w1 - w0) * (y1 - y0)
        value = within + mix + interaction
        contribution_sum += value

        rows.append(
            {
                "name": name,
                "baseline_numerator": b_num,
                "baseline_denominator": b_den,
                "current_numerator": c_num,
                "current_denominator": c_den,
                "baseline_rate": y0,
                "current_rate": y1,
                "baseline_weight": w0,
                "current_weight": w1,
                "within_contribution": within,
                "mix_contribution": mix,
                "interaction_contribution": interaction,
                **contribution_metrics(value, total_delta, baseline_total),
                "direction": classify_direction(value, total_delta),
            }
        )

    residual = total_delta - contribution_sum
    warnings = []
    if abs(residual) > 1e-9:
        warnings.append("比率型贡献未完全加总到总体变化，请检查分组是否互斥且分母完整。")

    return build_result("ratio", baseline_total, current_total, rows, contribution_sum, residual, warnings)


def build_result(
    method: str,
    baseline_total: float,
    current_total: float,
    rows: list[dict[str, Any]],
    contribution_sum: float,
    residual: float,
    warnings: list[str],
) -> dict[str, Any]:
    total_delta = current_total - baseline_total
    return round_float(
        {
            "ok": True,
            "method": method,
            "summary": {
                "baseline_total": baseline_total,
                "current_total": current_total,
                "delta": total_delta,
                "relative_change": safe_div(total_delta, baseline_total),
            },
            "rows": rows,
            "checks": {
                "sum_contribution": contribution_sum,
                "residual": residual,
                "warnings": warnings,
            },
        }
    )


METHODS = {
    "add": additive,
    "multiply": multiplicative,
    "ratio": ratio,
}


def load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("输入 JSON 顶层必须是对象")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="指标异动贡献度计算器")
    parser.add_argument("method", choices=sorted(METHODS), help="计算方法：add / multiply / ratio")
    parser.add_argument("input", type=Path, help="输入 JSON 文件路径")
    args = parser.parse_args(argv)

    try:
        payload = load_payload(args.input)
        result = METHODS[args.method](payload)
    except Exception as exc:  # noqa: BLE001 - CLI 需要把错误转成稳定 JSON。
        error = {"ok": False, "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
