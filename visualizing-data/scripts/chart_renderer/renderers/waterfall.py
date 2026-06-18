from __future__ import annotations

import pandas as pd
from matplotlib.patches import Patch

from ..contract import ChartSpec
from ..theme import clean_axes, prepare_axes


POSITIVE_COLOR = "#54A24B"
NEGATIVE_COLOR = "#E45756"
TOTAL_COLOR = "#4C78A8"
CONNECTOR_COLOR = "#9CA3AF"


def _option_float(options: dict, key: str, default: float) -> float:
    value = options.get(key, default)
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _label_bar(ax, index: int, value: float, top: float, minimum: float, maximum: float) -> None:
    span = maximum - minimum
    offset = span * 0.015 if span else max(abs(value) * 0.015, 0.5)
    if value >= 0:
        y_pos = top + offset
        va = "bottom"
    else:
        y_pos = top - offset
        va = "top"
    ax.text(index, y_pos, f"{value:g}", ha="center", va=va, fontsize=9, color="#374151")


def render(spec: ChartSpec, dpi: int):
    label = spec.encoding["label"]
    delta = spec.encoding["delta"]
    frame = pd.DataFrame(spec.data)

    start_value = _option_float(spec.options, "start_value", 0.0)
    start_label = str(spec.options.get("start_label") or "Start")
    end_label = str(spec.options.get("end_label") or "End")
    deltas = frame[delta].astype(float).tolist()
    labels = [start_label, *frame[label].astype(str).tolist(), end_label]

    running = start_value
    bottoms = [0.0]
    heights = [start_value]
    colors = [TOTAL_COLOR]
    tops = [start_value]
    connectors: list[float] = [start_value]

    for amount in deltas:
        next_total = running + amount
        bottoms.append(min(running, next_total))
        heights.append(abs(amount))
        colors.append(POSITIVE_COLOR if amount >= 0 else NEGATIVE_COLOR)
        tops.append(next_total if amount >= 0 else running)
        connectors.append(next_total)
        running = next_total

    bottoms.append(0.0)
    heights.append(running)
    colors.append(TOTAL_COLOR)
    tops.append(running)

    positions = list(range(len(labels)))
    fig, ax = prepare_axes(spec, dpi)
    ax.bar(positions, heights, bottom=bottoms, color=colors, edgecolor="white", linewidth=0.9)

    for index, y_value in enumerate(connectors):
        ax.plot([index + 0.38, index + 0.62], [y_value, y_value], color=CONNECTOR_COLOR, linewidth=1.0)

    values_for_scale = [*bottoms, *[base + height for base, height in zip(bottoms, heights)]]
    minimum = min(values_for_scale)
    maximum = max(values_for_scale)
    label_values = [start_value, *deltas, running]
    for index, value in enumerate(label_values):
        _label_bar(ax, index, value, tops[index], minimum, maximum)

    ax.axhline(0, color="#9CA3AF", linewidth=0.9)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel(label)
    ax.set_ylabel(delta)
    ax.legend(
        handles=[
            Patch(facecolor=TOTAL_COLOR, label="Start / End"),
            Patch(facecolor=POSITIVE_COLOR, label="Positive"),
            Patch(facecolor=NEGATIVE_COLOR, label="Negative"),
        ],
        frameon=False,
        loc="best",
    )
    clean_axes(ax)
    return fig
