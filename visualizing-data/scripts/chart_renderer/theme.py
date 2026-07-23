from __future__ import annotations

import textwrap
from typing import Any

import matplotlib.pyplot as plt
from matplotlib import rcParams
import seaborn as sns

from .contract import ChartSpec


PALETTE = [
    "#4C78A8",
    "#F58518",
    "#54A24B",
    "#B279A2",
    "#E45756",
    "#72B7B2",
    "#FF9DA6",
    "#9D755D",
]
PRIMARY = PALETTE[0]
SECONDARY = PALETTE[1]
POSITIVE = PALETTE[2]
NEGATIVE = PALETTE[4]
INK = "#1F2937"
LABEL = "#374151"
MUTED = "#6B7280"
AXIS = "#D8DEE9"
GRID = "#E5E9F0"
TICK = "#4C566A"
ZERO = "#9CA3AF"
WHITE = "white"
TABLE_ALT = "#F8FAFC"
BOX_FILL = "#A0CBE8"


def apply_theme() -> None:
    font_sans_serif = list(rcParams["font.sans-serif"])
    font_family = rcParams["font.family"]
    unicode_minus = rcParams["axes.unicode_minus"]
    sns.set_theme(
        context="notebook",
        style="whitegrid",
        palette=PALETTE,
        rc={
            "axes.edgecolor": AXIS,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "figure.facecolor": WHITE,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": TICK,
            "ytick.color": TICK,
            "font.sans-serif": font_sans_serif,
            "font.family": font_family,
            "axes.unicode_minus": unicode_minus,
        },
    )


def option_int(options: dict[str, Any], key: str, default: int) -> int:
    value = options.get(key, default)
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def create_figure(spec: ChartSpec, dpi: int):
    width = option_int(spec.options, "width", 1200)
    height = option_int(spec.options, "height", 720)
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.subplots_adjust(top=0.80, left=0.10, right=0.97, bottom=0.16)
    return fig, ax


def _wrap_header_text(text: str, width: int) -> str:
    lines: list[str] = []
    for source_line in text.splitlines() or [text]:
        lines.extend(
            textwrap.wrap(
                source_line,
                width=width,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    return "\n".join(lines)


def add_header(fig, spec: ChartSpec):
    title = fig.text(
        0.10,
        0.955,
        _wrap_header_text(spec.title, width=56),
        ha="left",
        va="top",
        fontsize=16,
        fontweight="bold",
        color=INK,
    )
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    title_box = title.get_window_extent(renderer).transformed(fig.transFigure.inverted())
    subtitle = fig.text(
        0.10,
        title_box.y0 - 0.014,
        _wrap_header_text(spec.subtitle, width=86),
        ha="left",
        va="top",
        fontsize=10.5,
        color=MUTED,
    )
    fig.canvas.draw()
    subtitle_box = subtitle.get_window_extent(renderer).transformed(fig.transFigure.inverted())
    fig.subplots_adjust(top=max(0.30, subtitle_box.y0 - 0.045))
    return title, subtitle


def clean_axes(ax) -> None:
    sns.despine(ax=ax, left=False, bottom=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(AXIS)
    ax.spines["bottom"].set_color(AXIS)
    ax.set_axisbelow(True)


def prepare_axes(spec: ChartSpec, dpi: int):
    fig, ax = create_figure(spec, dpi)
    add_header(fig, spec)
    return fig, ax
