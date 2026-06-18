from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..theme import clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    stage = spec.encoding["stage"]
    value = spec.encoding["value"]
    frame = pd.DataFrame(spec.data)
    values = frame[value].astype(float).tolist()
    labels = frame[stage].astype(str).tolist()
    positions = list(range(len(frame)))

    fig, ax = prepare_axes(spec, dpi)
    fig.subplots_adjust(left=0.24)
    ax.barh(positions, values, color="#4C78A8", edgecolor="white", linewidth=0.9)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(value)
    ax.set_ylabel(stage)

    span = max(values) - min(values) if values else 0
    offset = span * 0.015 if span else (max(values) * 0.015 if values else 0.5)
    for position, amount in zip(positions, values):
        ax.text(amount + offset, position, f"{amount:g}", ha="left", va="center", fontsize=9, color="#374151")

    clean_axes(ax)
    return fig
