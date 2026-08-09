from __future__ import annotations

import pandas as pd
import seaborn as sns

from ..contract import ChartSpec
from ..labels import add_point_labels, axis_label, enabled
from ..theme import BOX_FILL, LABEL, clean_axes, prepare_axes


def _option_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "on", "yes", "1"}:
            return True
        if normalized in {"false", "off", "no", "0"}:
            return False
    return default


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    frame = pd.DataFrame(spec.data)

    fig, ax = prepare_axes(spec, dpi)
    sns.boxplot(data=frame, x=x, y=y, ax=ax, color=BOX_FILL, width=0.55, fliersize=3)
    if _option_bool(spec.options.get("strip"), False):
        sns.stripplot(data=frame, x=x, y=y, ax=ax, color=LABEL, size=4, jitter=False, alpha=0.72)
    if enabled(spec.options, frame[x].nunique(), auto=False):
        medians = frame.groupby(x, sort=False)[y].median().astype(float).tolist()
        add_point_labels(ax, range(len(medians)), medians)
    ax.set_xlabel(axis_label(spec.options, "x", x))
    ax.set_ylabel(axis_label(spec.options, "y", y))
    clean_axes(ax)
    return fig
