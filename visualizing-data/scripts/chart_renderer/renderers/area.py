from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..labels import add_point_labels, axis_label, enabled
from ..theme import PRIMARY, ZERO, clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    frame = pd.DataFrame(spec.data)
    positions = range(len(frame))
    values = frame[y].astype(float)
    labels = frame[x].astype(str)

    fig, ax = prepare_axes(spec, dpi)
    ax.plot(list(positions), values, color=PRIMARY, linewidth=2.2, marker="o")
    ax.fill_between(list(positions), values, 0, color=PRIMARY, alpha=0.22)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels)
    ax.set_xlabel(axis_label(spec.options, "x", x))
    ax.set_ylabel(axis_label(spec.options, "y", y))
    ax.axhline(0, color=ZERO, linewidth=0.9)
    if enabled(spec.options, len(frame), auto=False):
        add_point_labels(ax, range(len(frame)), values.tolist())
    clean_axes(ax)
    return fig
