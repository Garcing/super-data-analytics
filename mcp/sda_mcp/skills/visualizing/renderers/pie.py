from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..labels import enabled
from ..theme import LABEL, PALETTE, WHITE, add_header, create_figure


def render(spec: ChartSpec, dpi: int):
    label = spec.encoding["label"]
    value = spec.encoding["value"]
    frame = pd.DataFrame(spec.data).sort_values(value, ascending=False, kind="mergesort")

    fig, ax = create_figure(spec, dpi)
    add_header(fig, spec)
    ax.pie(
        frame[value].astype(float),
        labels=frame[label].astype(str),
        autopct="%1.1f%%" if enabled(spec.options, len(frame), auto=True) else None,
        startangle=90,
        counterclock=False,
        colors=PALETTE,
        textprops={"fontsize": 9, "color": LABEL},
        wedgeprops={"linewidth": 1, "edgecolor": WHITE},
    )
    ax.axis("equal")
    return fig
