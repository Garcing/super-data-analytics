from __future__ import annotations

import pandas as pd
import seaborn as sns

from ..contract import ChartSpec
from ..theme import clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    frame = pd.DataFrame(spec.data)
    fig, ax = prepare_axes(spec, dpi)
    sns.scatterplot(data=frame, x=x, y=y, ax=ax, color="#4C78A8", s=64, edgecolor="white", linewidth=0.7)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    clean_axes(ax)
    return fig
