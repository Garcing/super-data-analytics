from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ContractError(ValueError):
    pass


SUPPORTED_TYPES = {
    "area",
    "bar",
    "boxplot",
    "funnel",
    "heatmap",
    "histogram",
    "horizontal_bar",
    "line",
    "pareto",
    "pie",
    "scatter",
    "stacked_bar",
    "table",
    "waterfall",
}


@dataclass(frozen=True)
class ChartSpec:
    chart_type: str
    title: str
    subtitle: str
    data: list[dict[str, Any]]
    encoding: dict[str, Any]
    options: dict[str, Any]


def _require_text(spec: dict[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{key} is required and must be a non-empty string")
    return value.strip()


def _require_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    data = spec.get("data")
    if not isinstance(data, list):
        raise ContractError("data is required and must be a list of objects")
    if not data:
        raise ContractError("data is required and must be a non-empty list of objects")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(data):
        if not isinstance(row, dict):
            raise ContractError(f"data[{index}] must be an object")
        rows.append(row)
    return rows


def _require_encoding(spec: dict[str, Any]) -> dict[str, Any]:
    encoding = spec.get("encoding")
    if not isinstance(encoding, dict):
        raise ContractError("encoding is required and must be an object")
    return encoding


def _validate_dimension_option(options: dict[str, Any], key: str) -> None:
    if key not in options:
        return
    value = options[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"options.{key} must be a positive integer")


def _field_name(encoding: dict[str, Any], role: str, *, required: bool = True) -> str | None:
    value = encoding.get(role)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"encoding.{role} is required")
    return value.strip()


def _require_field(rows: list[dict[str, Any]], field: str, role: str) -> None:
    for index, row in enumerate(rows):
        if field not in row:
            raise ContractError(f"encoding.{role} field '{field}' is missing from data row {index}")


def _ensure_numeric(rows: list[dict[str, Any]], field: str, role: str) -> None:
    for index, row in enumerate(rows):
        if field not in row:
            continue
        value = row.get(field)
        if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ContractError(f"encoding.{role} field '{field}' must contain numeric values; row {index} has {value!r}")


def validate(spec: dict[str, Any]) -> ChartSpec:
    chart_type = spec.get("type")
    if not isinstance(chart_type, str) or chart_type.strip() not in SUPPORTED_TYPES:
        raise ContractError(f"type must be one of {sorted(SUPPORTED_TYPES)}")

    title = _require_text(spec, "title")
    subtitle = _require_text(spec, "subtitle")
    rows = _require_rows(spec)
    encoding = _require_encoding(spec)
    options = spec.get("options", {})
    if not isinstance(options, dict):
        raise ContractError("options must be an object when present")
    _validate_dimension_option(options, "width")
    _validate_dimension_option(options, "height")

    required_roles = {
        "area": ["x", "y"],
        "bar": ["x", "y"],
        "boxplot": ["x", "y"],
        "funnel": ["stage", "value"],
        "heatmap": ["x", "y", "value"],
        "histogram": ["x"],
        "horizontal_bar": ["x", "y"],
        "line": ["x", "y"],
        "pareto": ["x", "y"],
        "pie": ["label", "value"],
        "scatter": ["x", "y"],
        "stacked_bar": ["x", "series", "value"],
        "table": [],
        "waterfall": ["label", "delta"],
    }[chart_type.strip()]

    encoded_roles = [role for role, value in encoding.items() if isinstance(value, str) and value.strip()]
    for role in sorted(set(required_roles).union(encoded_roles)):
        field = _field_name(encoding, role)
        assert field is not None
        _require_field(rows, field, role)

    for role in {
        "area": ["y"],
        "bar": ["y"],
        "boxplot": ["y"],
        "funnel": ["value"],
        "heatmap": ["value"],
        "histogram": ["x"],
        "horizontal_bar": ["y"],
        "line": ["y"],
        "pareto": ["y"],
        "pie": ["value"],
        "scatter": ["x", "y"],
        "stacked_bar": ["value"],
        "waterfall": ["delta"],
    }.get(chart_type.strip(), []):
        field = _field_name(encoding, role)
        assert field is not None
        _ensure_numeric(rows, field, role)

    return ChartSpec(
        chart_type=chart_type.strip(),
        title=title,
        subtitle=subtitle,
        data=rows,
        encoding=encoding,
        options=options,
    )
