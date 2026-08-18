from __future__ import annotations

from typing import Iterable


from .theme import LABEL

LABEL_COLOR = LABEL
LABEL_SIZE = 9


def enabled(options: dict, count: int, *, auto: bool) -> bool:
    value = options.get("data_labels", "auto")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "off", "none", "no"}:
            return False
        if normalized in {"true", "on", "yes"}:
            return True
    return auto and count <= 20


def format_value(value: float) -> str:
    return f"{value:g}"


def axis_label(options: dict, role: str, fallback: str) -> str:
    labels = options.get("axis_labels", {})
    return labels.get(role, fallback)


def add_point_labels(ax, xs: Iterable[float], ys: Iterable[float], *, x_offset: float = 0.0, y_offset: float = 6.0) -> None:
    for x, y in zip(xs, ys):
        ax.annotate(format_value(y), (x + x_offset, y), xytext=(0, y_offset), textcoords="offset points", ha="center", va="bottom", fontsize=LABEL_SIZE, color=LABEL_COLOR)


def add_vertical_bar_labels(ax, patches, values: Iterable[float], *, x_offset: float = 0.0) -> None:
    values = list(values)
    if not values:
        return
    span = max(values) - min(values)
    offset = span * 0.015 if span else max(abs(values[0]) * 0.015, 0.5)
    for patch, value in zip(patches, values):
        y = patch.get_y() + patch.get_height()
        direction = 1 if value >= 0 else -1
        ax.text(patch.get_x() + patch.get_width() / 2 + x_offset, y + direction * offset, format_value(value), ha="center", va="bottom" if direction > 0 else "top", fontsize=LABEL_SIZE, color=LABEL_COLOR)


def add_stacked_bar_labels(ax, patches, values: Iterable[float], *, percent: bool = False) -> None:
    for patch, value in zip(patches, values):
        text = f"{value:.1f}%" if percent else format_value(value)
        ax.text(patch.get_x() + patch.get_width() / 2, patch.get_y() + patch.get_height() / 2, text, ha="center", va="center", fontsize=LABEL_SIZE, color=LABEL_COLOR)
