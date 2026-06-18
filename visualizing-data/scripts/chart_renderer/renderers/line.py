from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..theme import clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    frame = pd.DataFrame(spec.data)
    positions = list(range(len(frame)))
    values = frame[y].astype(float).tolist()
    labels = frame[x].astype(str).tolist()
    fig, ax = prepare_axes(spec, dpi)
    ax.plot(positions, values, marker="o", linewidth=2.2, color="#4C78A8")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    clean_axes(ax)
    return fig
