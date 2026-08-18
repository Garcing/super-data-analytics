from __future__ import annotations

import pandas as pd
import seaborn as sns

from ..contract import ChartSpec
from ..labels import add_vertical_bar_labels, axis_label, enabled
from ..theme import PRIMARY, WHITE, clean_axes, option_int, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    frame = pd.DataFrame(spec.data)
    bins = option_int(spec.options, "bins", 10)

    fig, ax = prepare_axes(spec, dpi)
    sns.histplot(data=frame, x=x, bins=bins, ax=ax, color=PRIMARY, edgecolor=WHITE, linewidth=0.8)
    if enabled(spec.options, len(ax.patches), auto=False):
        add_vertical_bar_labels(ax, ax.patches, [patch.get_height() for patch in ax.patches])
    ax.set_xlabel(axis_label(spec.options, "x", x))
    ax.set_ylabel(axis_label(spec.options, "y", "count"))
    clean_axes(ax)
    return fig
