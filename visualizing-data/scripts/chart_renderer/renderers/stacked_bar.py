from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..theme import PALETTE, clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    series = spec.encoding["series"]
    value = spec.encoding["value"]
    frame = pd.DataFrame(spec.data)
    matrix = frame.pivot_table(index=x, columns=series, values=value, aggfunc="sum", fill_value=0, sort=False)

    fig, ax = prepare_axes(spec, dpi)
    bottom = [0.0] * len(matrix)
    positions = list(range(len(matrix)))
    for index, column in enumerate(matrix.columns):
        values = matrix[column].astype(float).tolist()
        ax.bar(
            positions,
            values,
            bottom=bottom,
            label=str(column),
            color=PALETTE[index % len(PALETTE)],
            edgecolor="white",
            linewidth=0.8,
        )
        bottom = [base + amount for base, amount in zip(bottom, values)]

    ax.set_xticks(positions)
    ax.set_xticklabels([str(item) for item in matrix.index])
    ax.set_xlabel(x)
    ax.set_ylabel(value)
    ax.legend(title=series, frameon=False, loc="best")
    clean_axes(ax)
    return fig
