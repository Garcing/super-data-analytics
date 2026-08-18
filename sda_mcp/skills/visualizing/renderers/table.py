from __future__ import annotations

import pandas as pd

from ..contract import ChartSpec
from ..theme import AXIS, GRID, INK, LABEL, TABLE_ALT, WHITE, add_header, create_figure


def _columns(rows: list[dict]) -> list[str]:
    names: list[str] = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    return names


def render(spec: ChartSpec, dpi: int):
    frame = pd.DataFrame(spec.data, columns=_columns(spec.data))
    fig, ax = create_figure(spec, dpi)
    add_header(fig, spec)
    ax.axis("off")

    table = ax.table(
        cellText=frame.fillna("").astype(str).values.tolist(),
        colLabels=[str(column) for column in frame.columns],
        cellLoc="left",
        colLoc="left",
        loc="center",
        bbox=[0, 0, 1, 1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.35)

    for (row, _column), cell in table.get_celld().items():
        cell.set_edgecolor(AXIS)
        cell.set_linewidth(0.7)
        if row == 0:
            cell.set_facecolor(GRID)
            cell.set_text_props(weight="bold", color=INK)
        else:
            cell.set_facecolor(WHITE if row % 2 else TABLE_ALT)
            cell.set_text_props(color=LABEL)
    return fig
