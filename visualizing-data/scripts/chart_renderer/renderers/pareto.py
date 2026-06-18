from __future__ import annotations

import pandas as pd
from matplotlib.ticker import PercentFormatter

from ..contract import ChartSpec
from ..theme import clean_axes, prepare_axes


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
    bars = ax.bar(positions, values, color="#4C78A8", edgecolor="white", linewidth=0.9)
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel(x)
    ax.set_ylabel(y)

    span = max(values) - min(values) if values else 0
    offset = span * 0.015 if span else (max(values) * 0.015 if values else 0.5)
    for bar, amount in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            amount + offset,
            f"{amount:g}",
            ha="center",
            va="bottom",
            fontsize=9,
            color="#374151",
        )

    secondary = ax.twinx()
    secondary.plot(positions, cumulative, color="#E45756", marker="o", linewidth=2.0, label="Cumulative share")
    secondary.set_ylim(0, 1.05)
    secondary.set_ylabel("Cumulative share")
    secondary.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    secondary.grid(False)
    secondary.spines["top"].set_visible(False)
    secondary.spines["right"].set_color("#D8DEE9")
    secondary.tick_params(axis="y", colors="#4C566A")
    secondary.legend(frameon=False, loc="upper right")

    clean_axes(ax)
    return fig
