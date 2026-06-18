---
name: report-to-streamlit
description: 把分析结论做成可分享的 Streamlit 交互式报告（多报告看板），每份报告一个 .py，部署后发链接
---

# Streamlit 报告（report → streamlit）

把分析结论做成**交互式**分析报告，挂在线上看板里。一份报告 = `reports/` 下一个 `.py`，由你（agent）编写。Plotly 图表，结论驱动结构。线上看板：**https://super-data-analytics.streamlit.app/**

## 何时用 Streamlit 报告

| 场景 | 选 |
|---|---|
| 要交互（hover、筛选、tab 切换）、图表类型多、像轻量 BI | **Streamlit** |
| 要静态、可链接、最快分享 | HTML（`report_to_html.md`） |
| 要图（海报式、单图） | Image（`report_to_image.md`） |

定位：**报告 = 呈现已得出的结论**（结论先行 + 叙事），不是开放式仪表盘。

## META 约定（报告 .py 顶部必填）

```python
META = {
    "title": "2026Q1 销售分析",   # 必填：导航名 + URL 路径（直达链接 = 线上地址/<title>）
    "icon": "📊",                  # 必填：emoji 图标
    "group": "销售",               # 必填：分区，同 group 聚一起
    "summary": "一句话摘要。",     # 选填：显示在主页报告卡上
}
```

- `title` 会同时作为该报告的 **URL 路径**，所以直达链接就是 `https://super-data-analytics.streamlit.app/<title>`（如 `…/区域销售分析`）。**避免 title 里出现空格和斜杠**。
- 把报告 `.py` 丢进 `reports/`（文件名不要以 `_` 开头）即自动进导航；主页会按 `group` 列出全部报告卡，无需手建。

## 报告 .py 标准结构（结论驱动）

照这个骨架写，**顺序就是叙事顺序**：

```python
from __future__ import annotations
import pandas as pd
import streamlit as st
from lib import charts
from lib import components as C
from lib.data import cached

META = {"title": "...", "icon": "📊", "group": "...", "summary": "..."}

@cached
def load_xxx() -> pd.DataFrame:
    ...  # 取数，缓存

# 0. 标题 + 元信息
st.header("标题")
st.caption("数据来源 · 生成日期")

# 1. 摘要 + KPI（结论先行）
C.kpi_strip([{"label":"GMV","value":"¥1.2亿","delta":"+12%","delta_label":"同比"}])
st.write("一句话结论。")

# 2. 洞察章节（重复 N 段：标题 → 图 → 洞察卡）
C.section("章节标题")
df = load_xxx()
st.plotly_chart(charts.bar(df, x="区域", y="GMV"), width="stretch")
C.insight_card("小标题","论证。", importance="high")

# 3.（可选）页内筛选器（侧边栏留给导航，筛选器放页面内）
region = st.multiselect("区域", df["区域"].unique(), df["区域"].unique())

# 4. 方法论（折叠）
with st.expander("数据口径与计算方法"):
    st.write("...")

# 5. 结论与下一步
C.conclusion_block("结论句。", actions=["行动1","行动2"])
```

## lib API 速查

### components（直接渲染，返回 None）

| 函数 | 参数 | 说明 |
|---|---|---|
| `C.kpi_strip(items)` | `items=[{"label","value","delta"(可选),"delta_color"(normal/inverse/off,可选),"delta_label"(可选,作tooltip)}]` | 一行 KPI 卡 |
| `C.section(title)` | `title:str` | 章节标题 + 分隔线 |
| `C.insight_card(title, body, importance)` | `importance:"high"/"medium"/"low"` | 带色条洞察卡 |
| `C.conclusion_block(summary, actions=None)` | `summary:str, actions:list[str]` | 高亮结论框 + 行动项 |
| `C.metric_badge(text, level)` | `level:"high"/"medium"/"low"` | 行内标签 |

### charts（返回 Figure，用 `st.plotly_chart(fig, width="stretch")` 展示）

| 函数 | 参数 | 返回 |
|---|---|---|
| `charts.bar(df, x, y, color=None, title=None)` | | Figure |
| `charts.line(df, x, y, color=None, title=None)` | | Figure |
| `charts.area(df, x, y, color=None, title=None)` | | Figure |
| `charts.pie(df, names, values, title=None)` | | Figure |
| `charts.scatter(df, x, y, color=None, size=None, title=None)` | | Figure |
| `charts.heatmap(df, title=None)` | df 为矩阵(index=行,columns=列) | Figure |
| `charts.table(df)` | | None（直接走 st.dataframe） |

配色/字体/hover 已统一，不要在报告里散写主题。

### data

| 函数 | 说明 |
|---|---|
| `@cached`（装饰器） | 等价 `@st.cache_data`，给取数/变换函数加缓存 |
| `load_df(path)` | 按 csv/parquet/xlsx 读 `reports/data/` 下的文件（相对路径）或绝对路径 |

## 写报告的要点

**数据从哪来**：内联 `pd.DataFrame({...})`（小数据集，零依赖）/ 仓库内 `reports/data/xxx.csv` 用 `load_df` 读 / 跨板块调 `querying-data-via-sql` 或 `querying-data-via-powerbi`。取数逻辑包进 `@cached` 函数。

**交互**：页内筛选器 `st.multiselect / selectbox / date_input / toggle`（放图表上方）；Plotly 原生 hover/缩放/图例切换默认就有；分段 `st.tabs`；折叠 `st.expander`。

**缓存**：只给确定性函数（同样输入同样输出）加 `@cached`；不给带副作用/依赖时间/依赖 session_state 的函数加。

## 交付流程

> 以下命令默认在 **`generating-insights-report/`** 目录下执行（skill 仓库根的子目录）。

1. 复制模板：`scripts/streamlit/reports/_template.py` → `scripts/streamlit/reports/report-<主题>.py`，填 `META` + 正文
2. 本地冒烟：
   ```bash
   streamlit run scripts/streamlit/app.py
   ```
   逐项确认——默认页/主页正常、新报告进导航、至少一张 Plotly 图（hover 可用）+ KPI 条 + 表格渲染、筛选/rerun 不抛异常。**不要止步于「app 能启动」**，必须点进你写的那页确认图真的画出来
3. commit 到 skill 仓库 main（**只 add 新报告文件，不要 `git add -A`**）：
   ```bash
   git add scripts/streamlit/reports/report-<主题>.py
   git commit -m "feat(streamlit): add <报告title> 报告"
   ```
4. 部署上线：
   ```bash
   bash scripts/streamlit/deploy.sh
   ```
   脚本会自动 cd 到仓库根，subtree push 到 `Garcing/streamlit-reports`，Cloud 约 1-2 分钟自动重新部署
5. 把**直达链接**发给用户：`https://super-data-analytics.streamlit.app/<报告title>`

## 备注

- 报告若要连数据库/带密钥，密钥走 Streamlit Cloud 的 Secrets manager（`.streamlit/secrets.toml`，已被 `.gitignore` 忽略，不进 git）
- `deploy.sh` 是 fast-forward push；若远端分叉（一般不会，这是 deploy 专用仓库）会报错，需人工排查
