from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..theme import PALETTE, add_header, create_figure


def render(spec: ChartSpec, dpi: int):
    label = spec.encoding["label"]
    value = spec.encoding["value"]
    frame = pd.DataFrame(spec.data).sort_values(value, ascending=False, kind="mergesort")

    fig, ax = create_figure(spec, dpi)
    add_header(fig, spec)
    ax.pie(
        frame[value].astype(float),
        labels=frame[label].astype(str),
        autopct="%1.1f%%",
        startangle=90,
        counterclock=False,
        colors=PALETTE,
        textprops={"fontsize": 9, "color": "#374151"},
        wedgeprops={"linewidth": 1, "edgecolor": "white"},
    )
    ax.axis("equal")
    return fig
