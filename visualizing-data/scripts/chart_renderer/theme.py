from __future__ import annotations

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


def apply_theme() -> None:
    font_sans_serif = list(rcParams["font.sans-serif"])
    font_family = rcParams["font.family"]
    unicode_minus = rcParams["axes.unicode_minus"]
    sns.set_theme(
        context="notebook",
        style="whitegrid",
        palette=PALETTE,
        rc={
            "axes.edgecolor": "#D8DEE9",
            "axes.labelcolor": "#2E3440",
            "axes.titlecolor": "#2E3440",
            "figure.facecolor": "white",
            "grid.color": "#E5E9F0",
            "grid.linewidth": 0.8,
            "xtick.color": "#4C566A",
            "ytick.color": "#4C566A",
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


def add_header(fig, spec: ChartSpec) -> None:
    fig.text(
        0.10,
        0.955,
        spec.title,
        ha="left",
        va="top",
        fontsize=16,
        fontweight="bold",
        color="#1F2937",
    )
    fig.text(
        0.10,
        0.905,
        spec.subtitle,
        ha="left",
        va="top",
        fontsize=10.5,
        color="#6B7280",
    )


def clean_axes(ax) -> None:
    sns.despine(ax=ax, left=False, bottom=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D8DEE9")
    ax.spines["bottom"].set_color("#D8DEE9")
    ax.tick_params(axis="x", labelrotation=0)
    ax.set_axisbelow(True)


def prepare_axes(spec: ChartSpec, dpi: int):
    fig, ax = create_figure(spec, dpi)
    add_header(fig, spec)
    return fig, ax
