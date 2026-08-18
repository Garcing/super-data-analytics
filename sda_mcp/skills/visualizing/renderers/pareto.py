from __future__ import annotations

import pandas as pd
from matplotlib.ticker import PercentFormatter

from ..contract import ChartSpec
from ..labels import axis_label, enabled
from ..theme import AXIS, LABEL, NEGATIVE, PRIMARY, TICK, WHITE, clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    frame = pd.DataFrame(spec.data).sort_values(y, ascending=False, kind="mergesort")
    values = frame[y].astype(float).tolist()
    labels = frame[x].astype(str).tolist()
    positions = list(range(len(frame)))
    total = sum(values)
    cumulative = []
    running = 0.0
    for amount in values:
        running += amount
        cumulative.append(running / total if total else 0.0)

    fig, ax = prepare_axes(spec, dpi)
    bars = ax.bar(positions, values, color=PRIMARY, edgecolor=WHITE, linewidth=0.9)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel(axis_label(spec.options, "x", x))
    ax.set_ylabel(axis_label(spec.options, "y", y))

    span = max(values) - min(values) if values else 0
    offset = span * 0.015 if span else (max(values) * 0.015 if values else 0.5)
    if enabled(spec.options, len(values), auto=True):
        for bar, amount in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, amount + offset, f"{amount:g}", ha="center", va="bottom", fontsize=9, color=LABEL)

    secondary = ax.twinx()
    cumulative_label = axis_label(spec.options, "cumulative", "Cumulative share")
    secondary.plot(positions, cumulative, color=NEGATIVE, marker="o", linewidth=2.0, label=cumulative_label)
    secondary.set_ylim(0, 1.05)
    secondary.set_ylabel(cumulative_label)
    secondary.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    secondary.grid(False)
    secondary.spines["top"].set_visible(False)
    secondary.spines["right"].set_color(AXIS)
    secondary.tick_params(axis="y", colors=TICK)
    ax.figure.subplots_adjust(right=0.8)
    secondary.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0)
    if len(labels) > 6 or max(map(len, labels), default=0) > 6:
        ax.tick_params(axis="x", labelrotation=18)
        ax.figure.subplots_adjust(bottom=0.21)

    clean_axes(ax)
    return fig
