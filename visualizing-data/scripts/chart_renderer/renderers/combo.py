from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..labels import add_point_labels, add_vertical_bar_labels, axis_label, enabled
from ..theme import AXIS, PALETTE, TICK, ZERO, clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    bar = spec.encoding["bar"]
    line = spec.encoding["line"]
    frame = pd.DataFrame(spec.data)
    positions = list(range(len(frame)))

    fig, left = prepare_axes(spec, dpi)
    bar_label = axis_label(spec.options, "bar", bar)
    line_label = axis_label(spec.options, "line", line)
    bars = left.bar(positions, frame[bar].astype(float).tolist(), color=PALETTE[0], label=bar_label)
    bar_values = frame[bar].astype(float).tolist()
    left.set_xticks(positions)
    left.set_xticklabels(frame[x].astype(str).tolist())
    left.set_xlabel(axis_label(spec.options, "x", x))
    left.set_ylabel(axis_label(spec.options, "bar", bar))
    left.axhline(0, color=ZERO, linewidth=0.9)

    right = left.twinx()
    line_plot = right.plot(
        positions,
        frame[line].astype(float).tolist(),
        color=PALETTE[1],
        marker="o",
        linewidth=2.2,
        label=line_label,
    )
    line_values = frame[line].astype(float).tolist()
    right.set_ylabel(axis_label(spec.options, "line", line))
    right.grid(False)
    right.spines["top"].set_visible(False)
    right.spines["right"].set_color(AXIS)
    right.tick_params(axis="y", colors=TICK)

    if enabled(spec.options, len(frame), auto=False):
        add_vertical_bar_labels(left, bars, bar_values, x_offset=-0.12)
        add_point_labels(right, positions, line_values, x_offset=0.12, y_offset=18)

    fig.subplots_adjust(right=0.70)
    fig.legend(
        [bars, line_plot[0]],
        [bar_label, line_label],
        frameon=False,
        loc="center left",
        bbox_to_anchor=(0.79, 0.50),
        borderaxespad=0,
    )
    clean_axes(left)
    return fig
