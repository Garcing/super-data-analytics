from __future__ import annotations

import pandas as pd
import seaborn as sns

from ..contract import ChartSpec
from ..theme import prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    value = spec.encoding["value"]
    frame = pd.DataFrame(spec.data)
    matrix = frame.pivot_table(index=y, columns=x, values=value, aggfunc="sum", sort=False)

    fig, ax = prepare_axes(spec, dpi)
    sns.heatmap(
        matrix,
        ax=ax,
        annot=True,
        fmt=spec.options.get("value_format", ".2g"),
        cmap="Blues",
        linewidths=0.8,
        linecolor="white",
        cbar_kws={"shrink": 0.82, "label": value},
        annot_kws={"fontsize": 9},
    )
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.tick_params(axis="x", labelrotation=0)
    ax.tick_params(axis="y", labelrotation=0)
    return fig
