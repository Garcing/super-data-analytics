"""示例报告二：用户增长分析（演示面积图 + 饼图 + 散点图 + 侧边栏筛选）。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import charts
from lib import components as C
from lib.data import cached

META = {
    "title": "用户增长分析",
    "icon": "👥",
    "group": "用户",
    "summary": "新增用户趋势、渠道占比、获客成本 vs 留存。",
}


@cached
def _cohort_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "月份": ["1月", "2月", "3月", "4月", "5月", "6月"],
            "新增用户": [3200, 4100, 5200, 6800, 8500, 10200],
        }
    )


@cached
def _channel_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "渠道": ["自然搜索", "信息流投放", "私域裂变", "应用市场", "KOL"],
            "用户数": [8200, 6100, 4500, 3300, 2100],
        }
    )


@cached
def _scatter_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "渠道": ["自然搜索", "信息流投放", "私域裂变", "应用市场", "KOL"] * 2,
            "获客成本": [12, 38, 8, 15, 55, 14, 42, 9, 16, 60],
            "7日留存": [0.42, 0.28, 0.55, 0.38, 0.22, 0.45, 0.30, 0.58, 0.40, 0.25],
            "批次": ["A"] * 5 + ["B"] * 5,
        }
    )


st.header("用户增长分析")
st.caption("示例数据 · 2026 上半年")

C.kpi_strip(
    [
        {"label": "累计新增", "value": "3.8万", "delta": "+62%"},
        {"label": "CAC", "value": "¥24", "delta": "-18%", "delta_color": "inverse"},
        {"label": "7日留存", "value": "38%", "delta": "+4pt"},
    ]
)
st.write("结论先行：新增用户逐月加速，私域裂变获客成本最低（¥8）且留存最高（55%）。")

# 页内筛选器：侧边栏留给导航，筛选器放页面内
channels = _channel_df()
all_ch = channels["渠道"].tolist()

C.section("新增用户累计趋势")
st.plotly_chart(charts.area(_cohort_df(), x="月份", y="新增用户"), width="stretch")
C.insight_card("二季度获客提速", "6 月单月新增破万，环比 +20%。", importance="high")

C.section("各渠道用户占比")
picked = st.multiselect("选择渠道", all_ch, all_ch)
chan_view = channels[channels["渠道"].isin(picked)] if picked else channels
st.plotly_chart(charts.pie(chan_view, names="渠道", values="用户数"), width="stretch")

C.section("获客成本 vs 7日留存")
st.plotly_chart(
    charts.scatter(_scatter_df(), x="获客成本", y="7日留存", color="渠道", size="7日留存"),
    width="stretch",
)
C.insight_card(
    "私域裂变性价比最高",
    "左上角象限：低成本 + 高留存，应加大投入；KOL（右下）成本高留存低，需重评。",
    importance="medium",
)

with st.expander("数据口径"):
    st.write("新增用户按首次成单计；留存按 7 日内再次活跃；CAC 按渠道投放费用/新增。")

C.conclusion_block(
    "建议向私域裂变倾斜预算，KOL 投放降权。",
    actions=["设计私域裂变激励方案", "KOL 渠道做 A/B 重评"],
)
