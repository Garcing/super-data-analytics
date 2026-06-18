from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..theme import clean_axes, prepare_axes


def _sorted_frame(spec: ChartSpec, x: str, y: str) -> pd.DataFrame:
    frame = pd.DataFrame(spec.data)
    sort = spec.options.get("sort")
    if sort in {"asc", "ascending"}:
        return frame.sort_values(y, ascending=True, kind="mergesort")
    if sort in {"desc", "descending"}:
        return frame.sort_values(y, ascending=False, kind="mergesort")
    return frame


def _should_label(spec: ChartSpec, row_count: int) -> bool:
    value = spec.options.get("value_labels", "auto")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "off", "none", "no"}:
            return False
        if normalized in {"true", "on", "yes"}:
            return True
    return row_count <= 20


def _add_vertical_labels(ax, values: list[float]) -> None:
    if not values:
        return
    span = max(values) - min(values)
    offset = span * 0.015 if span else max(abs(values[0]) * 0.015, 0.5)
    for patch, value in zip(ax.patches, values):
        x_pos = patch.get_x() + patch.get_width() / 2
        if value >= 0:
            y_pos = value + offset
            va = "bottom"
        else:
            y_pos = value - offset
            va = "top"
        ax.text(x_pos, y_pos, f"{value:g}", ha="center", va=va, fontsize=9, color="#374151")


def _add_horizontal_labels(ax, values: list[float]) -> None:
    if not values:
        return
    span = max(values) - min(values)
    offset = span * 0.015 if span else max(abs(values[0]) * 0.015, 0.5)
    for patch, value in zip(ax.patches, values):
        y_pos = patch.get_y() + patch.get_height() / 2
        if value >= 0:
            x_pos = value + offset
            ha = "left"
        else:
            x_pos = value - offset
            ha = "right"
        ax.text(x_pos, y_pos, f"{value:g}", ha=ha, va="center", fontsize=9, color="#374151")


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    frame = _sorted_frame(spec, x, y)
    positions = list(range(len(frame)))
    labels = frame[x].astype(str).tolist()
    values = frame[y].astype(float).tolist()
    fig, ax = prepare_axes(spec, dpi)

    if spec.chart_type == "horizontal_bar":
        fig.subplots_adjust(left=0.24)
        ax.barh(positions, values, color="#4C78A8")
        ax.set_yticks(positions)
        ax.set_yticklabels(labels)
        ax.axvline(0, color="#9CA3AF", linewidth=0.9)
        ax.set_xlabel(y)
        ax.set_ylabel(x)
        if _should_label(spec, len(frame)):
            _add_horizontal_labels(ax, values)
    else:
        ax.bar(positions, values, color="#4C78A8")
        ax.set_xticks(positions)
        ax.set_xticklabels(labels)
        ax.axhline(0, color="#9CA3AF", linewidth=0.9)
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        if _should_label(spec, len(frame)):
            _add_vertical_labels(ax, values)

    clean_axes(ax)
    return fig
