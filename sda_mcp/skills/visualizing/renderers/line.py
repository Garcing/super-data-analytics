from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from ..contract import ChartSpec
from ..labels import add_point_labels, axis_label, enabled
from ..theme import PALETTE, clean_axes, prepare_axes


def render(spec: ChartSpec, dpi: int):
    x = spec.encoding["x"]
    y = spec.encoding["y"]
    series = spec.encoding.get("series") or spec.encoding.get("color")
    markers = spec.options.get("markers", True)
    smooth = spec.options.get("smooth", False)
    frame = pd.DataFrame(spec.data)
    fig, ax = prepare_axes(spec, dpi)

    def draw_line(positions: list[int], values: list[float], color: str, label: str | None = None) -> None:
        if smooth:
            if len(positions) < 3 or len(set(positions)) != len(positions):
                raise ValueError("options.smooth requires at least 3 distinct x values for each line")
            smooth_positions = np.linspace(positions[0], positions[-1], num=max(100, len(positions) * 40))
            smooth_values = PchipInterpolator(positions, values)(smooth_positions)
            ax.plot(smooth_positions, smooth_values, marker="None", linewidth=2.2, color=color, label=label)
            if markers:
                ax.scatter(positions, values, color=color, s=30, zorder=3)
            if enabled(spec.options, len(values), auto=False):
                add_point_labels(ax, positions, values)
            return
        ax.plot(
            positions,
            values,
            marker="o" if markers else "None",
            linewidth=2.2,
            color=color,
            label=label,
        )
        if enabled(spec.options, len(values), auto=False):
            add_point_labels(ax, positions, values)

    if series:
        labels = frame[x].astype(str).tolist()
        positions_by_label = dict.fromkeys(labels)
        positions_by_label = {label: index for index, label in enumerate(positions_by_label)}
        for index, (series_value, group) in enumerate(frame.groupby(series, sort=False)):
            group_labels = group[x].astype(str).tolist()
            positions = [positions_by_label[label] for label in group_labels]
            values = group[y].astype(float).tolist()
            draw_line(positions, values, PALETTE[index % len(PALETTE)], str(series_value))
        ax.set_xticks(list(positions_by_label.values()))
        ax.set_xticklabels(list(positions_by_label.keys()))
        ax.legend(title=str(series), frameon=False, loc="best")
    else:
        positions = list(range(len(frame)))
        values = frame[y].astype(float).tolist()
        labels = frame[x].astype(str).tolist()
        draw_line(positions, values, PALETTE[0])
        ax.set_xticks(positions)
        ax.set_xticklabels(labels)

    ax.set_xlabel(axis_label(spec.options, "x", x))
    ax.set_ylabel(axis_label(spec.options, "y", y))
    clean_axes(ax)
    return fig
