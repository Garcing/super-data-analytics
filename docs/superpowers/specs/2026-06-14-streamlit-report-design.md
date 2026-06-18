---
title: Streamlit 交互式报告（report → streamlit）设计
status: draft
date: 2026-06-14
---

# Streamlit 交互式报告（report → streamlit）

## 1. 目标与范围

在 `generating-insights-report/scripts/streamlit/` 下实现一个 Streamlit 多页应用：**一个 app 托管多份报告**，每份报告是一个独立 `.py` 文件，由 agent 按指引编写。报告是「结论驱动」的交互式呈现（区别于 HTML 静态报告，也区别于开放式仪表盘）。

### 定位：报告 ≠ 仪表盘 ≠ HTML 镜像

- **不复用 HTML 报告的 JSON schema**。HTML schema 后续会持续升级，未必适合 Streamlit。两套数据格式解耦。
- **不是仪表盘**。仪表盘是「探索工具」（重筛选、开放式）；报告是「呈现已得出的结论」（重叙事、有结论段）。框架强调结论驱动结构，而不是一堆筛选器 + 自由探索。
- **是交互式丰富报告**：Plotly 图表（hover/缩放/图例切换）、图表类型多样、可选侧边栏筛选。比 HTML 静态报告更丰富，比仪表盘更聚焦结论。

### 范围内（本阶段：本地）

- `app.py` 入口：扫描 `reports/*.py`，用 `ast` 提取每份报告的 `META`，按 `group` 分组，`st.navigation` + `st.Page` 动态建页
- `lib/` 共享框架（薄、专一）：
  - `components.py`：KPI 条、洞察卡、章节标题、结论块等布局组件
  - `charts.py`：对 `plotly.express` 的薄封装，统一配色/字体/margin/hover，覆盖常见图表类型
  - `data.py`：`@st.cache_data` 封装、数据加载、loading/empty/error 状态 helper
- `reports/_template.py`：复制即用的报告模板（含标准结构骨架）
- `.streamlit/config.toml`：统一主题（light，warm parchment 配色与 HTML 报告呼应）
- `requirements.txt`：streamlit、pandas、plotly
- `README.md`：本地运行 + 冒烟测试；云部署留占位
- `references/report_to_streamlit.md`：**核心指引**——何时用、多页机制、报告标准结构、lib API 清单、交互模式、缓存、冒烟测试、加报告步骤

### 范围外（明确不做，本阶段）

- **云服务打通**：GitHub 仓库创建、Streamlit Community Cloud 接入、agent 自动 push / 取公网 URL。本阶段不做，但目录结构与启动方式已对齐部署要求，为后续预留路径。
- **不实现真实业务报告**。本阶段交付框架 + 模板 + 指引；真实报告由 agent 后续按指引编写。
- **不引入测试框架**（项目无现成 test 体系）。靠 lib 函数可测性 + 模板报告冒烟（`streamlit run` 跑通）验证。

---

## 2. 技术选型与依据

### 图表库：Plotly（非 Streamlit 原生）

| 维度 | Plotly（选定） | Streamlit 原生 `st.bar_chart`（Altair） |
|------|---|---|
| 交互 | hover/缩放/图例切换/框选 | 基础 hover/缩放 |
| 图表类型 | 散点/热力/雷达/地图/瀑布… | 柱/线/面积/条，类型少 |
| 依赖 | 自包含，无 Arrow 顾虑 | Altair 底层，部分环境 pyarrow 渲染问题 |
| 定制 | 深度可定制 | 难定制 |

Streamlit 官方内置 `st.plotly_chart(fig)` 原生支持展示 Plotly 图，是文档/例子最多的图表方案。选定 Plotly。

### 多页机制：st.navigation + st.Page

- `st.navigation`（≥1.36.0）接收 `Mapping[str, Sequence[page]]` 时自动按 key 分组生成分区导航
- `st.Page("reports/xxx.py", title=, icon=)` 把每个报告 .py 注册为一页
- 入口 `app.py` 是路由器 + 公共元素框架（标题/logo 在入口画，所有页可见）

### 数据获取

报告 .py 自行决定数据来源。常见来源（指引会列出）：
- 内联数据（小数据集直接写在 .py 里）
- 仓库内 CSV/Parquet（放 `reports/data/`）
- 运行时调 SQL/Power BI（`querying-data-via-*` 板块产出）

本阶段模板用内联数据，确保零外部依赖即可冒烟。

---

## 3. 目录结构

```
generating-insights-report/scripts/streamlit/
├── app.py                  # 入口：扫描 reports/ → ast 提取 META → st.navigation 建页 → run
├── lib/
│   ├── __init__.py
│   ├── components.py       # kpi_strip / section / insight_card / conclusion_block / metric_badge
│   ├── charts.py           # bar/line/area/pie/scatter/heatmap/table（统一主题的 plotly.express 封装）
│   └── data.py             # cached（@st.cache_data 封装）/ load_df / loading_empty_error
├── reports/
│   ├── _template.py        # 报告模板（标准结构骨架 + META）
│   └── data/               # （可选）报告引用的数据文件
├── .streamlit/
│   └── config.toml         # 主题/布局
├── requirements.txt
└── README.md
```

指引文档：`generating-insights-report/references/report_to_streamlit.md`

---

## 4. app.py 多页机制

### META 约定

每份报告 .py 顶部声明一个模块级 `META` 字典：

```python
META = {
    "title": "2026Q1 销售分析",   # 导航显示名
    "icon": "📊",                  # 导航图标（emoji）
    "group": "销售",               # 分区；同 group 聚在一起
}
```

### ast 提取（不执行报告代码）

`app.py` 用 `ast` 解析 `reports/*.py`，定位 `META = {...}` 赋值节点，`ast.literal_eval` 取值。这样读取报告元信息**不会触发报告 .py 顶层 st 调用**（否则会渲染）。

- 文件名以 `_` 开头的（如 `_template.py`）跳过
- META 缺失 → 用文件名兜底，group 默认 "其他"

### 导航构建

```python
import ast, glob, os
import streamlit as st

st.set_page_config(page_title="数据分析报告", page_icon="📈", layout="wide")

reports_dir = os.path.join(os.path.dirname(__file__), "reports")
pages_by_group = {}  # {"销售": [StreamlitPage, ...], ...}

for path in sorted(glob.glob(os.path.join(reports_dir, "*.py"))):
    if os.path.basename(path).startswith("_"):
        continue
    meta = extract_meta(path)  # ast 解析；失败兜底
    page = st.Page(path, title=meta["title"], icon=meta.get("icon", "📄"))
    pages_by_group.setdefault(meta.get("group", "其他"), []).append(page)

st.title("数据分析报告")
pg = st.navigation(pages_by_group if pages_by_group else ["reports/_template.py"])
pg.run()
```

### 空状态

`reports/` 无报告时，导航指向 `_template.py` 作为占位首页，提示「暂无报告，参考 `_template.py` 添加」。

---

## 5. lib/ 框架 API

### components.py

```python
kpi_strip(items: list[dict]) -> None
    # items: [{"label","value","delta"(可负,自动红绿),"delta_label"(可选)}]
    # 渲染一行 st.metric 卡片

section(title: str, anchor: str | None = None) -> None
    # 章节标题 + 分隔线

insight_card(title, body, importance: "high"|"medium"|"low") -> None
    # 带左侧色条的洞察卡，importance 决定颜色

conclusion_block(summary: str, actions: list[str] | None = None) -> None
    # 高亮的结论框 + 行动项列表

metric_badge(text: str, level: str) -> None
    # 行内标签
```

### charts.py

对 `plotly.express` 的薄封装，统一 `COLORWAY`、字体、margin、hovertemplate、`use_container_width` 习惯：

```python
bar(df, x, y, color=None, title=None) -> Figure
line(df, x, y, color=None, title=None) -> Figure
area(df, x, y, color=None, title=None) -> Figure
pie(df, names, values, title=None) -> Figure
scatter(df, x, y, color=None, size=None, title=None) -> Figure
heatmap(df, title=None) -> Figure   # df 为矩阵
table(df) -> None                    # 走 st.dataframe，统一样式
```

所有函数返回 `plotly.graph_objects.Figure`，调用方用 `st.plotly_chart(fig, use_container_width=True)` 展示。

### data.py

```python
cached(func, *args, **kwargs)
    # 包一层 @st.cache_data；对确定性读取/变换缓存

load_df(path: str) -> pd.DataFrame
    # 读 CSV/Parquet/Excel（按扩展名）

show_state(loading: str, empty: str, error: str | None) -> 装饰器/helper
    # 统一 loading/empty/error 占位渲染
```

---

## 6. 报告 .py 标准结构（指引核心）

结论驱动，summary-first：

```python
import streamlit as st
import pandas as pd
import plotly.express as px
from lib import components as C
from lib import charts
from lib.data import cached

META = {"title": "2026Q1 销售分析", "icon": "📊", "group": "销售"}

# 0. 标题 + 元信息
st.header("2026Q1 销售分析")
st.caption("数据来源：Power BI 语义模型 · 生成于 2026-04-15")

# 1. 摘要 + KPI（结论先行）
C.kpi_strip([
    {"label": "GMV", "value": "¥1.2亿", "delta": 0.12, "delta_label": "同比"},
    {"label": "订单数", "value": "48万", "delta": -0.03},
])
st.write("一句话结论：本季 GMV 同比 +12%，主要由华东区拉动；华南小幅下滑需关注。")

# 2. 洞察章节（叙事 + 交互图，可重复 N 段）
C.section("区域贡献拆解")
df = cached(load_region_df)
fig = charts.bar(df, x="区域", y="GMV", color="同比")
st.plotly_chart(fig, use_container_width=True)
C.insight_card("华东贡献 38%", "主要由新客增长驱动，客单价持平。", importance="high")

# 3.（可选）侧边栏筛选
region = st.sidebar.multiselect("区域", df["区域"].unique(), df["区域"].unique())

# 4. 方法论 / 数据说明（折叠）
with st.expander("数据口径与计算方法"):
    st.write("GMV 按成交口径，不含退款……")

# 5. 结论与下一步
C.conclusion_block(
    "华东打法可复制到华南，建议下季加大对华南的投放。",
    actions=["复盘华东获客渠道", "调研华南下滑原因"],
)
```

---

## 7. references/report_to_streamlit.md 大纲

1. **何时用 Streamlit 报告**（vs HTML / vs 仪表盘）
2. **多页机制**：app.py 如何扫描、META 约定、加报告步骤
3. **报告 .py 标准结构**（第 6 节）
4. **lib API 清单**（第 5 节，带示例）
5. **交互模式**：侧边栏筛选、Plotly hover/缩放、`st.tabs` 分段、`st.expander` 折叠
6. **缓存**：何时用 `cached`/`@st.cache_data`，避免缓存带副作用的函数
7. **冒烟测试**：交付前 `streamlit run app.py` → 切换每页 → 验证 loading/empty/error 状态
8. **加报告清单**：写 `reports/xxx.py`（含 META）→ 本地跑通 → commit（云阶段再 push）
9. **云部署（占位，后续补）**：GitHub repo、Streamlit Community Cloud、secrets、start command

---

## 8. .streamlit/config.toml（主题）

```toml
[theme]
base = "light"
backgroundColor = "#faf7f2"        # warm parchment，与 HTML 报告呼应
secondaryBackgroundColor = "#f3eee5"
textColor = "#2b2b2b"
font = "sans serif"
```

---

## 9. requirements.txt

```
streamlit>=1.36.0
pandas>=2.0
plotly>=5.20
```

---

## 10. 验证（本阶段）

无单测框架。验证靠：

1. **lib 纯函数可测性**：charts/data 函数输入输出明确，可在 REPL 验证返回类型正确
2. **冒烟测试**：`streamlit run app.py` →
   - 默认页（_template）正常渲染
   - 导航分组正确
   - 至少一张 Plotly 图、一个 KPI 条、一个表格的渲染路径跑通
   - rerun 不抛异常
3. **加报告流程验证**：复制 `_template.py` → 改 META → 重启确认出现在导航

---

## 11. 云部署路径（后续阶段，预留）

后续阶段实现「agent 写报告 .py → push GitHub → Streamlit Cloud 自动部署 → 返回 URL」：

- 目录结构已对齐（`app.py` 在根、`requirements.txt` 齐全、`.streamlit/config.toml` 就位）——Streamlit Cloud 直接可用
- 需补：GitHub repo 命名/初始化约定、`streamlit run app.py` 作为 start command、secrets 管理（若报告连数据库）、agent 的 git push + 取 URL 脚本
- 设计原则：报告数据 git-backed，加报告 = commit + push，Streamlit Cloud 监听 main 自动重新部署

---

## 12. 待办（落地步骤，转 writing-plans）

1. 建 `scripts/streamlit/` 目录，删/弃用空的 `scripts/stremlit/`（typo）
2. 写 `lib/`（components / charts / data）
3. 写 `app.py`（ast META 提取 + st.navigation）
4. 写 `reports/_template.py`
5. 写 `.streamlit/config.toml`、`requirements.txt`、`README.md`
6. 本地 `streamlit run app.py` 冒烟
7. 写 `references/report_to_streamlit.md`
8. 更新 `generating-insights-report/SKILL.md` + 根 `CLAUDE.md`（接线说明）
