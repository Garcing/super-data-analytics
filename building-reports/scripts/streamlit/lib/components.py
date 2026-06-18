"""报告布局组件：KPI 条、章节、洞察卡、结论块、标签。

约定：组件函数都直接渲染到当前 Streamlit 上下文，返回 None。
"""
from __future__ import annotations

import streamlit as st

_IMPORTANCE_COLOR = {
    "high": "#E86452",
    "medium": "#F6BD16",
    "low": "#5B8FF9",
}


def kpi_strip(items: list[dict]) -> None:
    """渲染一行 KPI 卡片。

    items: [{"label","value","delta"(可选数值或字符串),"delta_color"(可选 normal/inverse/off),"delta_label"(可选,作为 help tooltip)}]
    """
    if not items:
        return
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        col.metric(
            label=it["label"],
            value=it["value"],
            delta=it.get("delta"),
            delta_color=it.get("delta_color", "normal"),
            help=it.get("delta_label"),
        )


def section(title: str) -> None:
    """章节标题 + 分隔线。"""
    st.markdown(f"#### {title}")
    st.divider()


def insight_card(title: str, body: str, importance: str = "medium") -> None:
    """带左侧色条的洞察卡。importance: high/medium/low 决定色条颜色。"""
    color = _IMPORTANCE_COLOR.get(importance, "#999")
    st.markdown(
        f'<div style="border-left:4px solid {color};padding:8px 12px;'
        f'background:#f3eee5;border-radius:4px;margin:8px 0;">'
        f"<b>{title}</b><br>{body}</div>",
        unsafe_allow_html=True,
    )


def conclusion_block(summary: str, actions: list[str] | None = None) -> None:
    """高亮结论框 + 可选行动项列表。"""
    st.success(f"**结论：** {summary}")
    if actions:
        st.markdown("**建议下一步：**")
        for a in actions:
            st.markdown(f"- {a}")


def metric_badge(text: str, level: str = "medium") -> None:
    """行内小标签。level: high/medium/low。"""
    color = _IMPORTANCE_COLOR.get(level, "#999")
    st.markdown(
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:8px;font-size:12px;">{text}</span>',
        unsafe_allow_html=True,
    )
