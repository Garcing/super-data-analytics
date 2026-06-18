"""示例报告三：财务概览（演示热力图 + 表格）。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import charts
from lib import components as C
from lib.data import cached

META = {
    "title": "财务概览",
    "icon": "💰",
    "group": "财务",
    "summary": "各业务线季度营收热力图 + 明细表。",
}


@cached
def _kpi_matrix() -> pd.DataFrame:
    """行=业务线，列=季度，值=营收（万元）。"""
    return pd.DataFrame(
        {
            "Q1": [1200, 800, 450, 300],
            "Q2": [1500, 920, 520, 360],
            "Q3": [1700, 1100, 600, 410],
            "Q4": [2100, 1300, 720, 480],
        },
        index=["电商", "广告", "会员", "增值服务"],
    )


@cached
def _detail_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "业务线": ["电商", "广告", "会员", "增值服务"],
            "全年营收(万)": [6500, 4120, 2290, 1550],
            "同比": ["+18%", "+9%", "+31%", "+24%"],
            "毛利率": ["22%", "68%", "85%", "60%"],
        }
    )


st.header("财务概览")
st.caption("示例数据 · 2026 全年 · 单位：万元")

C.kpi_strip(
    [
        {"label": "全年营收", "value": "¥1.45亿", "delta": "+16%"},
        {"label": "综合毛利率", "value": "41%", "delta": "+3pt"},
        {"label": "增长王", "value": "会员", "delta": "+31%"},
    ]
)
st.write("结论先行：全年营收同比 +16%，会员与增值服务增速领先；电商仍是营收基本盘。")

C.section("各业务线 × 季度 营收热力")
st.plotly_chart(charts.heatmap(_kpi_matrix()), width="stretch")
C.insight_card("Q4 全面冲高", "电商 Q4 营收 2100 万为全年峰值，季节性明显。", importance="high")

C.section("业务线明细")
charts.table(_detail_df())

with st.expander("口径说明"):
    st.write("营收按权责发生制；毛利率=（营收-直接成本）/营收。")

C.conclusion_block(
    "会员/增值服务高毛利高增长，是利润提升重点；电商稳盘。",
    actions=["会员体系升级方案", "增值服务产品线扩充"],
)
