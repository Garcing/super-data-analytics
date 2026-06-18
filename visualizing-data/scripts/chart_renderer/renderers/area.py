from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..theme import clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    frame = pd.DataFrame(spec.data)
    positions = range(len(frame))
    values = frame[y].astype(float)
    labels = frame[x].astype(str)

    fig, ax = prepare_axes(spec, dpi)
    ax.plot(list(positions), values, color="#4C78A8", linewidth=2.2, marker="o")
    ax.fill_between(list(positions), values, 0, color="#4C78A8", alpha=0.22)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.axhline(0, color="#9CA3AF", linewidth=0.9)
    clean_axes(ax)
    return fig
