"""Plotly 图表薄封装：统一配色、字体、留白、hover，让所有报告视觉一致。

每个函数返回 ``plotly.graph_objects.Figure``，调用方用
``st.plotly_chart(fig, use_container_width=True)`` 展示。
``table`` 例外：直接走 ``st.dataframe``，返回 None。
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

COLORWAY = ["#5B8FF9", "#5AD8A6", "#F6BD16", "#E86452", "#6DC8EC", "#945FB9"]

_LAYOUT_DEFAULTS = dict(
    font=dict(family="Source Sans 3, Segoe UI, sans-serif", size=13, color="#2b2b2b"),
    margin=dict(l=8, r=8, t=44, b=8),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    hovermode="x unified",
    legend=dict(orientation="h", y=-0.15),
)


def _apply(fig, title=None):
    """统一应用主题。"""
    fig.update_layout(**_LAYOUT_DEFAULTS, colorway=COLORWAY)
    if title:
        fig.update_layout(title=dict(text=title, x=0))
    fig.update_xaxes(showgrid=False, linecolor="#ddd")
    fig.update_yaxes(gridcolor="#eee", linecolor="#ddd")
    return fig


def bar(df: pd.DataFrame, x: str, y: str, color: str | None = None, title: str | None = None):
    return _apply(px.bar(df, x=x, y=y, color=color), title)


def line(df: pd.DataFrame, x: str, y: str, color: str | None = None, title: str | None = None):
    return _apply(px.line(df, x=x, y=y, color=color), title)


def area(df: pd.DataFrame, x: str, y: str, color: str | None = None, title: str | None = None):
    return _apply(px.area(df, x=x, y=y, color=color), title)


def pie(df: pd.DataFrame, names: str, values: str, title: str | None = None):
    return _apply(
        px.pie(df, names=names, values=values, color_discrete_sequence=COLORWAY),
        title,
    )


def scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    size: str | None = None,
    title: str | None = None,
):
    return _apply(px.scatter(df, x=x, y=y, color=color, size=size), title)


def heatmap(df: pd.DataFrame, title: str | None = None):
    """df 为矩阵：index=行标签，columns=列标签，单元格为数值。"""
    fig = go.Figure(
        data=go.Heatmap(
            z=df.values,
            x=[str(c) for c in df.columns],
            y=[str(i) for i in df.index],
            colorscale="Blues",
        )
    )
    return _apply(fig, title)


def table(df: pd.DataFrame) -> None:
    """直接走 st.dataframe，统一样式。返回 None。"""
    st.dataframe(df, width="stretch", hide_index=True)
