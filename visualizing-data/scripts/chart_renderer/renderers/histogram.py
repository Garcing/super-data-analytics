from __future__ import annotations

import pandas as pd
import seaborn as sns

from ..contract import ChartSpec
from ..theme import clean_axes, option_int, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    frame = pd.DataFrame(spec.data)
    bins = option_int(spec.options, "bins", 10)

    fig, ax = prepare_axes(spec, dpi)
    sns.histplot(data=frame, x=x, bins=bins, ax=ax, color="#4C78A8", edgecolor="white", linewidth=0.8)
    ax.set_xlabel(x)
    ax.set_ylabel("count")
    clean_axes(ax)
    return fig
