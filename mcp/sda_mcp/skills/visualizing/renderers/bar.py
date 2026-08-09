from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..labels import add_stacked_bar_labels, add_vertical_bar_labels, axis_label, enabled
from ..theme import LABEL, PALETTE, PRIMARY, ZERO, clean_axes, prepare_axes


def _sorted_frame(spec: ChartSpec, x: str, y: str) -> pd.DataFrame:
    frame = pd.DataFrame(spec.data)
    sort = spec.options.get("sort")
    if sort in {"asc", "ascending"}:
        return frame.sort_values(y, ascending=True, kind="mergesort")
    if sort in {"desc", "descending"}:
        return frame.sort_values(y, ascending=False, kind="mergesort")
    return frame


def _should_label(spec: ChartSpec, row_count: int) -> bool:
    return enabled(spec.options, row_count, auto=True)


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
        ax.text(x_pos, y_pos, f"{value:g}", ha="center", va=va, fontsize=9, color=LABEL)


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
        ax.text(x_pos, y_pos, f"{value:g}", ha=ha, va="center", fontsize=9, color=LABEL)


def _render_series_bars(ax, frame: pd.DataFrame, x: str, y: str, series: str, mode: str, options: dict) -> None:
    matrix = frame.pivot_table(index=x, columns=series, values=y, aggfunc="sum", fill_value=0, sort=False)
    positions = list(range(len(matrix)))
    if mode == "percent_stacked":
        matrix = matrix.div(matrix.sum(axis=1), axis=0).fillna(0) * 100

    if mode == "grouped":
        width = 0.8 / len(matrix.columns)
        offset = -0.4 + width / 2
        for index, column in enumerate(matrix.columns):
            values = matrix[column].astype(float).tolist()
            centers = [position + offset + index * width for position in positions]
            ax.bar(centers, values, width=width, label=str(column), color=PALETTE[index % len(PALETTE)])
    else:
        bottom = [0.0] * len(matrix)
        for index, column in enumerate(matrix.columns):
            values = matrix[column].astype(float).tolist()
            ax.bar(
                positions,
                values,
                bottom=bottom,
                label=str(column),
                color=PALETTE[index % len(PALETTE)],
                edgecolor="white",
                linewidth=0.8,
            )
            bottom = [base + amount for base, amount in zip(bottom, values)]

    if enabled(options, len(ax.patches), auto=True):
        if mode == "grouped":
            add_vertical_bar_labels(ax, ax.patches, [patch.get_height() for patch in ax.patches])
        else:
            add_stacked_bar_labels(ax, ax.patches, [patch.get_height() for patch in ax.patches], percent=mode == "percent_stacked")

    ax.set_xticks(positions)
    ax.set_xticklabels([str(item) for item in matrix.index])
    ax.set_xlabel(axis_label(options, "x", x))
    ax.set_ylabel(axis_label(options, "y", f"{y} (%)" if mode == "percent_stacked" else y))
    if mode == "percent_stacked":
        ax.set_ylim(0, 100)
        ax.set_yticks(range(0, 101, 20))
        ax.set_yticklabels([f"{tick}%" for tick in range(0, 101, 20)])
    ax.figure.subplots_adjust(right=0.8)
    ax.legend(title=series, frameon=False, loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0)


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
        ax.barh(positions, values, color=PRIMARY)
        ax.set_yticks(positions)
        ax.set_yticklabels(labels)
        ax.axvline(0, color=ZERO, linewidth=0.9)
        ax.set_xlabel(axis_label(spec.options, "y", y))
        ax.set_ylabel(axis_label(spec.options, "x", x))
        if _should_label(spec, len(frame)):
            _add_horizontal_labels(ax, values)
    elif spec.encoding.get("series"):
        _render_series_bars(ax, frame, x, y, spec.encoding["series"], spec.options.get("series_mode", "grouped"), spec.options)
        ax.axhline(0, color=ZERO, linewidth=0.9)
    else:
        ax.bar(positions, values, color=PRIMARY)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels)
        ax.axhline(0, color=ZERO, linewidth=0.9)
        ax.set_xlabel(axis_label(spec.options, "x", x))
        ax.set_ylabel(axis_label(spec.options, "y", y))
        if _should_label(spec, len(frame)):
            _add_vertical_labels(ax, values)

    clean_axes(ax)
    return fig
