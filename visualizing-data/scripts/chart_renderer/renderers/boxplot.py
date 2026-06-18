from __future__ import annotations

import pandas as pd
import seaborn as sns

from ..contract import ChartSpec
from ..theme import clean_axes, prepare_axes


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
    sns.boxplot(data=frame, x=x, y=y, ax=ax, color="#A0CBE8", width=0.55, fliersize=3)
    if _option_bool(spec.options.get("strip"), False):
        sns.stripplot(data=frame, x=x, y=y, ax=ax, color="#374151", size=4, jitter=False, alpha=0.72)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    clean_axes(ax)
    return fig
