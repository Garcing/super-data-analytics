"""报告模板 —— 复制此文件、改名、改 META、改内容，即得一份新报告。

标准结构（结论驱动）：
  0. 标题 + 元信息
  1. 摘要 + KPI（结论先行）
  2. 洞察章节（叙事 + 交互图，可重复 N 段）
  3.（可选）侧边栏筛选
  4. 方法论 / 数据说明（折叠）
  5. 结论与下一步

注意：文件名以 _ 开头会被 app.py 跳过（不进导航）。复制后改名为
report-xxx.py 即自动出现在导航里。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import charts
from lib import components as C
from lib.data import cached

META = {
    "title": "报告模板（示例）",
    "icon": "📋",
    "group": "示例",
    "summary": "报告结构示例（文件名以 _ 开头，不进导航）。",
}


@cached
def _sample_region_df() -> pd.DataFrame:
    """示例数据。真实报告从 SQL/Power BI/CSV 取数，见 references/report_to_streamlit.md。"""
    return pd.DataFrame(
        {
            "区域": ["华东", "华南", "华北", "西部"],
            "GMV": [4500, 2100, 1800, 900],
            "同比": [0.12, -0.03, 0.08, 0.25],
        }
    )


@cached
def _sample_trend_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "月份": ["1月", "2月", "3月", "4月", "5月", "6月"],
            "GMV": [1200, 1500, 1700, 1600, 1900, 2200],
        }
    )


# 0. 标题 + 元信息
st.header("报告模板：2026 上半年销售概览")
st.caption("数据来源：示例数据 · 生成于 2026-06-14 · 仅供结构参考")

# 1. 摘要 + KPI（结论先行）
C.kpi_strip(
    [
        {"label": "GMV", "value": "¥9,300万", "delta": "+9.8%", "delta_label": "同比"},
        {"label": "订单数", "value": "48万", "delta": "-3%", "delta_color": "inverse"},
        {"label": "客单价", "value": "¥194", "delta": "+13%"},
    ]
)
st.write(
    "一句话结论：上半年 GMV 同比 +9.8%，主要由华东与西部高增长拉动；"
    "华南小幅下滑、订单数微降需关注。"
)

# 2. 洞察章节一：趋势
C.section("月度趋势")
trend = _sample_trend_df()
st.plotly_chart(charts.line(trend, x="月份", y="GMV"), width="stretch")
C.insight_card(
    "GMV 稳步上行",
    "6 月环比 +16%，二季度增速快于一季度，处于健康增长通道。",
    importance="high",
)

# 2. 洞察章节二：区域拆解
C.section("区域贡献拆解")
region = _sample_region_df()
st.plotly_chart(
    charts.bar(region, x="区域", y="GMV", color="区域"),
    width="stretch",
)
C.insight_card(
    "华东贡献近半",
    "华东占 48%，西部增速最高（+25%）但基数小，是潜力增长点。",
    importance="medium",
)

# 3.（可选）页内筛选器 —— 侧边栏留给导航，筛选器放页面内
show_table = st.toggle("显示区域明细表", value=False)
if show_table:
    charts.table(region)

# 4. 方法论 / 数据说明（折叠）
with st.expander("数据口径与计算方法"):
    st.write(
        "- GMV：成交口径，含已发货未退款订单。\n"
        "- 同比：与去年同期对比。\n"
        "- 区域：按收货地址归类。"
    )

# 5. 结论与下一步
C.conclusion_block(
    "华东打法可复制到西部，华南下滑需专项排查；整体增长健康。",
    actions=["复盘华东获客与转化渠道", "调研华南 GMV 下滑原因", "制定西部扩量计划"],
)
