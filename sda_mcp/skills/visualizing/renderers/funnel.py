from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..labels import axis_label, enabled
from ..theme import LABEL, PRIMARY, WHITE, clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    stage = spec.encoding["stage"]
    value = spec.encoding["value"]
    frame = pd.DataFrame(spec.data)
    values = frame[value].astype(float).tolist()
    labels = frame[stage].astype(str).tolist()
    positions = list(range(len(frame)))

    fig, ax = prepare_axes(spec, dpi)
    fig.subplots_adjust(left=0.24)
    ax.barh(positions, values, color=PRIMARY, edgecolor=WHITE, linewidth=0.9)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(axis_label(spec.options, "value", value))
    ax.set_ylabel(axis_label(spec.options, "stage", stage))

    span = max(values) - min(values) if values else 0
    offset = span * 0.015 if span else (max(values) * 0.015 if values else 0.5)
    if enabled(spec.options, len(values), auto=True):
        for position, amount in zip(positions, values):
            ax.text(amount + offset, position, f"{amount:g}", ha="left", va="center", fontsize=9, color=LABEL)

    clean_axes(ax)
    return fig
