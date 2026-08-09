from __future__ import annotations

import pandas as pd
import seaborn as sns

from ..contract import ChartSpec
from ..labels import add_point_labels, axis_label, enabled
from ..theme import PRIMARY, WHITE, clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    frame = pd.DataFrame(spec.data)
    fig, ax = prepare_axes(spec, dpi)
    sns.scatterplot(data=frame, x=x, y=y, ax=ax, color=PRIMARY, s=64, edgecolor=WHITE, linewidth=0.7)
    if enabled(spec.options, len(frame), auto=False):
        add_point_labels(ax, frame[x].astype(float).tolist(), frame[y].astype(float).tolist())
    ax.set_xlabel(axis_label(spec.options, "x", x))
    ax.set_ylabel(axis_label(spec.options, "y", y))
    clean_axes(ax)
    return fig
