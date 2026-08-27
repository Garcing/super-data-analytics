from __future__ import annotations

import numpy as np
import pandas as pd
import seaborn as sns

from ..contract import ChartSpec
from ..labels import axis_label, enabled
from ..theme import prepare_axes


def _default_cell_text(value) -> str:
    """智能默认标注:整数带千分位、小数两位。

    旧默认 ".2g" 会把 120 渲染成 1.2e+02(QA 2026-08-26),业务热力图不可读。"""
    number = float(value)
    if number.is_integer() and abs(number) < 1e15:
        return f"{number:,.0f}"
    return f"{number:,.2f}"


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    value = spec.encoding["value"]
    frame = pd.DataFrame(spec.data)
    matrix = frame.pivot_table(index=y, columns=x, values=value, aggfunc="sum", sort=False)

    show = enabled(spec.options, matrix.size, auto=True)
    custom = spec.options.get("value_format")
    if show and not custom:
        annot = pd.DataFrame(np.vectorize(_default_cell_text)(matrix.values),
                             index=matrix.index, columns=matrix.columns)
        fmt = ""
    else:
        annot = show
        fmt = custom or ".2g"

    fig, ax = prepare_axes(spec, dpi)
    sns.heatmap(
        matrix,
        ax=ax,
        annot=annot,
        fmt=fmt,
        cmap="Blues",
        linewidths=0.8,
        linecolor="white",
        cbar_kws={"shrink": 0.82, "label": value},
        annot_kws={"fontsize": 9},
    )
    ax.set_xlabel(axis_label(spec.options, "x", x))
    ax.set_ylabel(axis_label(spec.options, "y", y))
    ax.tick_params(axis="x", labelrotation=0)
    ax.tick_params(axis="y", labelrotation=0)
    return fig
