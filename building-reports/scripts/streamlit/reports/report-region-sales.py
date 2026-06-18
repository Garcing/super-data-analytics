"""示例报告一：区域销售分析（演示柱状图 + 折线图 + KPI）。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import charts
from lib import components as C
from lib.data import cached

META = {
    "title": "区域销售分析",
    "icon": "🛒",
    "group": "销售",
    "summary": "各区域 GMV 与同比、月度趋势对比。",
}


@cached
def _region_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "区域": ["华东", "华南", "华北", "西部", "华中"],
            "GMV": [4500, 2100, 1800, 900, 1200],
            "同比": [0.12, -0.03, 0.08, 0.25, 0.05],
        }
    )


@cached
def _monthly_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "月份": ["1月", "2月", "3月", "4月", "5月", "6月"],
            "GMV": [1200, 1500, 1700, 1600, 1900, 2200],
            "目标": [1300, 1400, 1600, 1700, 1800, 2000],
        }
    )


st.header("区域销售分析")
st.caption("示例数据 · 2026 上半年 · 数据来源：Power BI 语义模型")

C.kpi_strip(
    [
        {"label": "GMV", "value": "¥10,500万", "delta": "+9.8%", "delta_label": "同比"},
        {"label": "达成率", "value": "94%", "delta": "-6%", "delta_color": "inverse"},
        {"label": "TOP 区域", "value": "华东", "delta": "占比 43%"},
    ]
)
st.write("结论先行：上半年 GMV 同比 +9.8%，华东贡献近半；西部增速最高（+25%）但基数小。")

C.section("各区域 GMV 与同比")
region = _region_df()
st.plotly_chart(charts.bar(region, x="区域", y="GMV", color="区域"), width="stretch")
C.insight_card("华东一骑绝尘", "华东 GMV 4500 万，是第二名华南的两倍多。", importance="high")

C.section("月度 GMV vs 目标")
monthly = _monthly_df()
st.plotly_chart(charts.line(monthly, x="月份", y="GMV", color="月份"), width="stretch")
C.insight_card("二季度加速", "4-6 月连续超目标，6 月环比 +16%。", importance="medium")

with st.expander("数据口径"):
    st.write("GMV 按成交口径（含已发货未退款）；同比与去年同期对比。")

C.conclusion_block(
    "华东打法可复制到西部，华南下滑需专项排查。",
    actions=["复盘华东获客与转化渠道", "调研华南 GMV 下滑原因"],
)
