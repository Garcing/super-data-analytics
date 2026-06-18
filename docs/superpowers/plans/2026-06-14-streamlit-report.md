# Streamlit 交互式报告 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `generating-insights-report/scripts/streamlit/` 下交付一个可本地运行的 Streamlit 多页应用——一个 app 托管多份报告，每份报告是独立 `.py`，由 agent 按指引编写；Plotly 交互图表，结论驱动结构。

**Architecture:** 入口 `app.py` 用 `ast` 扫描 `reports/*.py` 提取 `META`（不执行报告代码），按 `group` 分组构建 `st.Page`，交 `st.navigation` 渲染。共享框架 `lib/`（components/charts/data）让所有报告视觉一致、代码精简。git-backed：加报告 = 丢一个 `.py`。

**Tech Stack:** Python · Streamlit (≥1.36) · Plotly · pandas

**Testing note:** 本项目无测试框架（spec §1 明确范围外）。验证策略 = `lib/` 纯函数用 `python -c` REPL 校验 + `streamlit run app.py` 冒烟测试。不写 pytest。

**Spec:** `docs/superpowers/specs/2026-06-14-streamlit-report-design.md`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `scripts/streamlit/app.py` | 入口：ast 提取 META + st.navigation 建页 + 公共标题 |
| `scripts/streamlit/lib/__init__.py` | 包标记 |
| `scripts/streamlit/lib/data.py` | `cached` 装饰器、`load_df` |
| `scripts/streamlit/lib/charts.py` | plotly.express 薄封装（bar/line/area/pie/scatter/heatmap/table），统一主题 |
| `scripts/streamlit/lib/components.py` | kpi_strip/section/insight_card/conclusion_block/metric_badge |
| `scripts/streamlit/reports/_template.py` | 报告模板（标准结构 + META） |
| `scripts/streamlit/.streamlit/config.toml` | 主题 |
| `scripts/streamlit/requirements.txt` | 依赖 |
| `scripts/streamlit/README.md` | 运行/冒烟/加报告 |
| `references/report_to_streamlit.md` | agent 指引（核心交付物） |
| `generating-insights-report/SKILL.md` | 接线：补 Streamlit 行 |
| `CLAUDE.md`（根） | 接线：补 Streamlit 说明 |

所有路径相对仓库根 `c:\Users\Administrator\.agents\skills\super-data-analyst`。

---

## Task 1: 脚手架 + 清理 typo 目录

**Files:**
- Create: `generating-insights-report/scripts/streamlit/`（目录）
- Create: `generating-insights-report/scripts/streamlit/requirements.txt`
- Remove: `generating-insights-report/scripts/stremlit/`（空 typo 目录）

- [ ] **Step 1: 删除空的 typo 目录**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
rmdir generating-insights-report/scripts/stremlit
```
Expected: 目录删除（为空，rmdir 直接成功）。若非空则报错——停下检查，不要强删。

- [ ] **Step 2: 建正确目录结构**

```bash
mkdir -p generating-insights-report/scripts/streamlit/lib
mkdir -p generating-insights-report/scripts/streamlit/reports/data
mkdir -p generating-insights-report/scripts/streamlit/.streamlit
```

- [ ] **Step 3: 写 requirements.txt**

文件：`generating-insights-report/scripts/streamlit/requirements.txt`

```
streamlit>=1.36.0
pandas>=2.0
plotly>=5.20
```

- [ ] **Step 4: 安装依赖**

```bash
pip install -r generating-insights-report/scripts/streamlit/requirements.txt
```
Expected: 三个包安装成功。验证 `streamlit --version` 输出 ≥1.36。

- [ ] **Step 5: 验证基础导入可用**

```bash
python -c "import streamlit, plotly, pandas; print(streamlit.__version__, plotly.__version__, pandas.__version__)"
```
Expected: 打印三个版本号，无 ImportError。

- [ ] **Step 6: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/scripts/streamlit/requirements.txt generating-insights-report/scripts/stremlit
git commit -m "feat(streamlit): scaffold directory + requirements; remove typo stremlit/ dir"
```

---

## Task 2: lib/data.py — 数据加载 + 缓存

**Files:**
- Create: `generating-insights-report/scripts/streamlit/lib/__init__.py`
- Create: `generating-insights-report/scripts/streamlit/lib/data.py`

- [ ] **Step 1: 写 lib/__init__.py**

文件：`generating-insights-report/scripts/streamlit/lib/__init__.py`

```python
"""Streamlit 报告共享框架。"""
```

- [ ] **Step 2: 写 lib/data.py**

文件：`generating-insights-report/scripts/streamlit/lib/data.py`

```python
"""数据加载与缓存 helper。

- cached：装饰器，等价于 @st.cache_data，给报告一个统一入口。
- load_df：按扩展名读 CSV/Parquet/Excel，相对路径基于 reports/data/。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

# reports/data/ 的绝对根（lib/ 的上一级再下到 reports/data）
_DATA_ROOT = Path(__file__).resolve().parent.parent / "reports" / "data"


def cached(func):
    """装饰器：等价于 ``@st.cache_data``，供报告统一使用。

    用法::

        @cached
        def load_region_df():
            return pd.read_csv(...)
    """
    return st.cache_data(func)


def load_df(path: str) -> pd.DataFrame:
    """读取 CSV / Parquet / Excel。

    相对路径基于 ``reports/data/``，也接受绝对路径。
    """
    p = Path(path)
    if not p.is_absolute():
        p = _DATA_ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"找不到数据文件: {p}")
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    if ext in (".parquet", ".pq"):
        return pd.read_parquet(p)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(p)
    raise ValueError(f"不支持的文件类型: {ext}（仅支持 csv/parquet/xlsx）")
```

- [ ] **Step 3: REPL 校验（load_df 报错路径，cached 返回可调用对象）**

```bash
cd generating-insights-report/scripts/streamlit
python -c "from lib.data import load_df, cached; \
try:
    load_df('nonexistent.csv')
except FileNotFoundError as e:
    print('OK load_df raises:', e); \
print('cached is decorator:', callable(cached(lambda: 1)))"
```
Expected: 打印 `OK load_df raises: 找不到数据文件: ...` 与 `cached is decorator: True`。
（`cached` 在无 streamlit 运行上下文时调用 `st.cache_data` 装饰函数本身不会报错；只有被装饰函数被调用时才需要 ScriptRun 上下文。这里只验证装饰阶段。）

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/scripts/streamlit/lib/
git commit -m "feat(streamlit): add lib/data.py (cached + load_df)"
```

---

## Task 3: lib/charts.py — Plotly 统一封装

**Files:**
- Create: `generating-insights-report/scripts/streamlit/lib/charts.py`

- [ ] **Step 1: 写 lib/charts.py**

文件：`generating-insights-report/scripts/streamlit/lib/charts.py`

```python
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
    st.dataframe(df, use_container_width=True, hide_index=True)
```

- [ ] **Step 2: REPL 校验（各图表返回 Figure）**

```bash
cd generating-insights-report/scripts/streamlit
python -c "import pandas as pd; from lib import charts; \
df = pd.DataFrame({'m':['1','2','3'],'v':[10,20,15]}); \
import plotly.graph_objects as go; \
assert isinstance(charts.bar(df,'m','v'), go.Figure); \
assert isinstance(charts.line(df,'m','v'), go.Figure); \
assert isinstance(charts.pie(df,names='m',values='v'), go.Figure); \
hm = pd.DataFrame([[1,2],[3,4]], index=['a','b'], columns=['x','y']); \
assert isinstance(charts.heatmap(hm), go.Figure); \
print('OK all charts return Figure')"
```
Expected: 打印 `OK all charts return Figure`。（`table` 走 st，不在无上下文下校验。）

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/scripts/streamlit/lib/charts.py
git commit -m "feat(streamlit): add lib/charts.py (plotly wrappers with unified theme)"
```

---

## Task 4: lib/components.py — 布局组件

**Files:**
- Create: `generating-insights-report/scripts/streamlit/lib/components.py`

- [ ] **Step 1: 写 lib/components.py**

文件：`generating-insights-report/scripts/streamlit/lib/components.py`

```python
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
```

- [ ] **Step 2: REPL 校验（函数可导入、签名正确）**

```bash
cd generating-insights-report/scripts/streamlit
python -c "from lib import components as C; \
import inspect; \
assert list(inspect.signature(C.kpi_strip).parameters)[0]=='items'; \
assert _IM_ok := C._IMPORTANCE_COLOR['high']=='#E86452'; \
print('OK components importable')"
```
Expected: 打印 `OK components importable`。

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/scripts/streamlit/lib/components.py
git commit -m "feat(streamlit): add lib/components.py (kpi_strip/section/insight_card/conclusion_block/metric_badge)"
```

---

## Task 5: app.py — 入口 + ast META 提取 + st.navigation

**Files:**
- Create: `generating-insights-report/scripts/streamlit/app.py`

- [ ] **Step 1: 写 app.py**

文件：`generating-insights-report/scripts/streamlit/app.py`

```python
"""Streamlit 报告看板入口。

扫描 reports/*.py，用 ast 提取每份报告的 META（不执行报告代码），
按 group 分组，用 st.navigation + st.Page 动态建页。
"""
from __future__ import annotations

import ast
import glob
import os
import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
# 让报告 .py 里的 `from lib import ...` 可解析
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

REPORTS_DIR = _HERE / "reports"

st.set_page_config(page_title="数据分析报告", page_icon="📈", layout="wide")


def extract_meta(path: Path) -> dict:
    """从报告 .py 顶层 META = {...} 字典提取元信息，不执行代码。"""
    defaults = {
        "title": path.stem,
        "icon": "📄",
        "group": "其他",
    }
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id == "META":
                try:
                    val = ast.literal_eval(node.value)
                    if isinstance(val, dict):
                        defaults.update(val)
                except Exception:
                    pass
                break
    return defaults


def build_pages() -> dict[str, list]:
    """扫描 reports/，返回 {group: [st.Page, ...]}。"""
    pages_by_group: dict[str, list] = {}
    for py in sorted(REPORTS_DIR.glob("*.py")):
        if py.name.startswith("_"):
            continue
        meta = extract_meta(py)
        # st.Page 接受相对入口文件所在目录的路径
        page = st.Page(str(py), title=meta["title"], icon=meta.get("icon", "📄"))
        pages_by_group.setdefault(meta.get("group", "其他"), []).append(page)
    return pages_by_group


def main() -> None:
    st.title("📈 数据分析报告")
    st.caption("交互式分析报告看板")

    pages_by_group = build_pages()

    if not pages_by_group:
        st.info("暂无报告。把报告 .py 放到 `reports/` 目录（参考 `reports/_template.py`），重启即可。")
        # 占位页：模板
        template = REPORTS_DIR / "_template.py"
        if template.exists():
            pg = st.navigation([st.Page(str(template), title="模板", icon="📄")])
        else:
            pg = st.navigation([])
        pg.run()
        return

    pg = st.navigation(pages_by_group)
    pg.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: REPL 校验 ast 提取逻辑（不依赖 streamlit 运行上下文）**

```bash
cd generating-insights-report/scripts/streamlit
python -c "
import ast, sys
from pathlib import Path
sys.path.insert(0, '.')
# 复制 extract_meta 逻辑做独立校验（app.py 顶层会触发 st.set_page_config，不能整体 import）
code = Path('app.py').read_text(encoding='utf-8')
tree = ast.parse(code)
src = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='extract_meta'][0]
# 验证函数体里出现 'META' 与 'literal_eval'
assert 'META' in ast.unparse(src) and 'literal_eval' in ast.unparse(src)
print('OK extract_meta defined and parses META via literal_eval')
"
```
Expected: 打印 `OK extract_meta defined and parses META via literal_eval`。

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/scripts/streamlit/app.py
git commit -m "feat(streamlit): add app.py entrypoint (ast META extraction + st.navigation)"
```

---

## Task 6: reports/_template.py — 报告模板

**Files:**
- Create: `generating-insights-report/scripts/streamlit/reports/_template.py`

- [ ] **Step 1: 写 _template.py**

文件：`generating-insights-report/scripts/streamlit/reports/_template.py`

```python
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
import plotly.express as px
import streamlit as st

from lib import charts
from lib import components as C
from lib.data import cached

META = {
    "title": "报告模板（示例）",
    "icon": "📋",
    "group": "示例",
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
st.plotly_chart(charts.line(trend, x="月份", y="GMV"), use_container_width=True)
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
    use_container_width=True,
)
C.insight_card(
    "华东贡献近半",
    "华东占 48%，西部增速最高（+25%）但基数小，是潜力增长点。",
    importance="medium",
)

# 3.（可选）侧边栏筛选 —— 这里仅演示，不影响上面已渲染的图
st.sidebar.markdown("### 筛选器（示例）")
show_table = st.sidebar.checkbox("显示区域明细表", value=False)
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
```

- [ ] **Step 2: 静态校验（ast 能解析、META 存在）**

```bash
cd generating-insights-report/scripts/streamlit
python -c "
import ast
from pathlib import Path
t = ast.parse(Path('reports/_template.py').read_text(encoding='utf-8'))
names = {n.targets[0].id for n in t.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
assert 'META' in names, 'META missing'
print('OK _template.py parses, META present')
"
```
Expected: 打印 `OK _template.py parses, META present`。

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/scripts/streamlit/reports/_template.py
git commit -m "feat(streamlit): add reports/_template.py (standard report skeleton)"
```

---

## Task 7: .streamlit/config.toml — 主题

**Files:**
- Create: `generating-insights-report/scripts/streamlit/.streamlit/config.toml`

- [ ] **Step 1: 写 config.toml**

文件：`generating-insights-report/scripts/streamlit/.streamlit/config.toml`

```toml
[theme]
base = "light"
backgroundColor = "#faf7f2"
secondaryBackgroundColor = "#f3eee5"
textColor = "#2b2b2b"
font = "sans serif"

[client]
toolbarMode = "minimal"

[server]
runOnSave = true
```

- [ ] **Step 2: 校验 TOML 可解析**

```bash
cd generating-insights-report/scripts/streamlit
python -c "import tomllib; d=tomllib.loads(open('.streamlit/config.toml','rb').read().decode()); assert d['theme']['backgroundColor']=='#faf7f2'; print('OK config.toml parses')"
```
Expected: 打印 `OK config.toml parses`。（Python 3.11+ 自带 tomllib；若报 ModuleNotFoundError，改用 `python -c "import tomli as t; ..."` 或跳过此步——toml 语法肉眼可核。）

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/scripts/streamlit/.streamlit/config.toml
git commit -m "feat(streamlit): add .streamlit/config.toml (warm parchment theme)"
```

---

## Task 8: 本地冒烟测试

**Files:** 无（验证步骤）

- [ ] **Step 1: 启动 app**

```bash
cd generating-insights-report/scripts/streamlit
streamlit run app.py
```
Expected: 浏览器自动打开 `http://localhost:8501`，页面显示「📈 数据分析报告」标题。因为 `reports/` 下只有 `_template.py`（被跳过），应显示空状态提示「暂无报告…」+ 模板占位页。

- [ ] **Step 2: 手动验证空状态 + 模板占位页**

在浏览器确认：
- 侧边栏/导航出现「模板」页
- 点进模板页：KPI 条、月度趋势折线图、区域柱状图（Plotly，hover 有提示）、洞察卡、结论块均渲染
- 调侧边栏「显示区域明细表」勾选 → 出现 table
- 展开「数据口径与计算方法」expander

Expected: 全部正常，无报错；图表 hover 交互可用。

- [ ] **Step 3: 验证「加报告」流程**

复制模板为一个真实报告并验证导航自动出现：

```bash
cd generating-insights-report/scripts/streamlit
cp reports/_template.py reports/report-demo.py
```
手动编辑 `reports/report-demo.py` 的 META：
```python
META = {
    "title": "Demo 报告",
    "icon": "✨",
    "group": "示例",
}
```
（用 Edit 工具改 META 三行即可，正文不用动。）
保存后 Streamlit 自动 rerun（`runOnSave=true`）。

Expected: 导航出现「示例」分组下两个页（「报告模板（示例）」+「Demo 报告」），点进 Demo 报告正常渲染。

- [ ] **Step 4: 验证 ast 提取不执行报告代码**

在 `reports/report-demo.py` 正文顶部（META 之后、函数之前）临时插入一行 `raise RuntimeError("should not run during nav build")`，保存。预期：导航仍正常构建（因为 ast 只解析不执行），页面不崩；点进 Demo 报告页时才会触发该 RuntimeError。验证后**删除这行**。

Expected: 插入后导航正常；删除后恢复。这证明 ast 提取 META 不执行报告体。

- [ ] **Step 5: 清理 demo 文件**

```bash
cd generating-insights-report/scripts/streamlit
rm reports/report-demo.py
```

- [ ] **Step 6: 停止 streamlit，Commit（模板已就绪，app 可跑）**

Ctrl+C 停止 streamlit。

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add -A generating-insights-report/scripts/streamlit/reports
git commit --allow-empty -m "chore(streamlit): smoke test passed locally (nav build, template render, add-report flow, ast-no-exec)"
```
（`--allow-empty` 因为 demo 文件已删，此 commit 仅记录冒烟通过这一节点。）

---

## Task 9: README.md

**Files:**
- Create: `generating-insights-report/scripts/streamlit/README.md`

- [ ] **Step 1: 写 README.md**

文件：`generating-insights-report/scripts/streamlit/README.md`

````markdown
# Streamlit 交互式报告

一个 app 托管多份报告。每份报告是 `reports/` 下一个 `.py` 文件，由 agent 按 [`../../references/report_to_streamlit.md`](../../references/report_to_streamlit.md) 编写。Plotly 交互图表，结论驱动结构。

## 本地运行

```bash
cd generating-insights-report/scripts/streamlit
pip install -r requirements.txt      # 首次
streamlit run app.py                 # 浏览器自动开 http://localhost:8501
```

## 目录

```
scripts/streamlit/
├── app.py            # 入口：扫描 reports/，ast 提取 META，st.navigation 建页
├── lib/              # 共享框架（components / charts / data）
├── reports/          # 每份报告一个 .py；_template.py 是模板（不进导航）
│   └── data/         # 报告引用的数据文件（CSV/Parquet/Excel）
├── .streamlit/config.toml
└── requirements.txt
```

## 加一份报告

1. 复制 `reports/_template.py` → `reports/report-<主题>.py`（文件名不要以 `_` 开头）
2. 改顶部 `META = {"title","icon","group"}`
3. 按模板里的注释结构填内容（调 `lib.components` / `lib.charts`）
4. 保存，`runOnSave=true` 会自动重新加载，导航出现新页

`META` 由 `app.py` 用 `ast` 静态提取（不执行报告代码），所以报告顶层可以放心写 `st.*` 调用。

## 冒烟测试（交付前必做）

```bash
streamlit run app.py
```

逐项确认：
- 默认页渲染正常
- 导航分组正确
- 至少一张 Plotly 图渲染（hover 可用）、一个 KPI 条、一个表格
- rerun 不抛异常
- loading / empty / error 状态可读

## 云部署（占位，后续阶段）

目录结构已对齐 Streamlit Community Cloud 要求（`app.py` 在根、`requirements.txt` 齐全、`.streamlit/config.toml` 就位）。后续接入 GitHub + Community Cloud，start command = `streamlit run app.py`。
````

- [ ] **Step 2: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/scripts/streamlit/README.md
git commit -m "docs(streamlit): add scripts/streamlit/README.md"
```

---

## Task 10: references/report_to_streamlit.md — agent 指引（核心交付物）

**Files:**
- Create: `generating-insights-report/references/report_to_streamlit.md`

- [ ] **Step 1: 写指引文档**

文件：`generating-insights-report/references/report_to_streamlit.md`

````markdown
---
name: report-to-streamlit
description: 把分析结论做成可分享的 Streamlit 交互式报告（多报告看板），每份报告一个 .py
---

# Streamlit 报告（report → streamlit）

把分析结论做成**交互式**分析报告，挂在一个多页 app 里。一份报告 = `reports/` 下一个 `.py`，由你（agent）编写。Plotly 图表，结论驱动结构。

## 何时用 Streamlit 报告

| 场景 | 选 |
|---|---|
| 要交互（hover、筛选、tab 切换）、图表类型多、像轻量 BI | **Streamlit** |
| 要静态、可链接、最快分享 | HTML（`report_to_html.md`） |
| 要图（海报式、单图） | Image（`report_to_image.md`） |
| 要开放式自由探索、强筛选 | （这不是报告定位，考虑 BI 平台） |

定位：**报告 = 呈现已得出的结论**（结论先行 + 叙事），不是开放式仪表盘。

## 多页机制（你只需关心报告 .py）

入口 `app.py` 用 `ast` 扫描 `reports/*.py`，从每份的顶层 `META` 字典提取标题/图标/分组，用 `st.navigation` 按分组建页。**你不用碰 `app.py`**。

加报告 = 复制 `reports/_template.py` → `reports/report-<主题>.py`，改 `META` + 正文，保存即可出现在导航。

### META 约定（报告 .py 顶部必填）

```python
META = {
    "title": "2026Q1 销售分析",  # 导航显示名
    "icon": "📊",                 # emoji 图标
    "group": "销售",              # 分区，同 group 聚一起
}
```

`app.py` 用 `ast.literal_eval` 静态读取 META（**不执行报告代码**），所以报告顶层可放心写 `st.*`。

## 报告 .py 标准结构（结论驱动）

照这个骨架写，**顺序就是叙事顺序**：

```python
from __future__ import annotations
import pandas as pd
import streamlit as st
from lib import charts
from lib import components as C
from lib.data import cached

META = {"title": "...", "icon": "📊", "group": "..."}

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
st.plotly_chart(charts.bar(df, x="区域", y="GMV"), use_container_width=True)
C.insight_card("小标题","论证。", importance="high")

# 3.（可选）侧边栏筛选
region = st.sidebar.multiselect("区域", df["区域"].unique(), df["区域"].unique())

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

### charts（返回 Figure，用 `st.plotly_chart(fig, use_container_width=True)` 展示）

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

## 数据从哪来

报告 .py 自行取数，常见来源：

- **内联**：小数据集直接 `pd.DataFrame({...})`（模板就是这么做的，零依赖）
- **仓库内文件**：放 `reports/data/xxx.csv`，`load_df("xxx.csv")` 读
- **SQL**：调 `querying-data-via-sql` 产出的数据
- **Power BI**：调 `querying-data-via-powerbi` 产出的数据

跨板块取数时，把取数逻辑包进 `@cached` 函数。

## 交互模式

- **侧边栏筛选**：`st.sidebar.multiselect / selectbox / date_input`，用返回值过滤 df 再画图
- **Plotly 原生交互**：hover 提示、缩放、图例点击开关系列，默认就有
- **分段**：`st.tabs(["总览","明细"])` 放多个视图
- **折叠**：`with st.expander("..."):` 放方法论/明细，默认收起

## 缓存注意事项

- 只给**确定性**函数（同样输入同样输出）加 `@cached`：读静态文件、跑固定 SQL
- **不要**给带副作用、依赖时间、依赖 session_state 的函数加缓存
- 缓存数据变了，在 app 右上「菜单 → Clear cache」或重启

## 冒烟测试（交付前必做）

```bash
cd generating-insights-report/scripts/streamlit
streamlit run app.py
```

逐项确认：
- 默认页渲染正常，导航分组正确
- 你新加的报告页出现在导航，点进去能渲染
- 至少一张 Plotly 图（hover 可用）、一个 KPI 条、一个表格渲染路径跑通
- 操作筛选器 / rerun 不抛异常
- loading / empty / error 状态可读

**不要止步于「app 能启动」**，必须点进你写的那页、确认图真的画出来。

## 加报告清单

- [ ] 复制 `reports/_template.py` → `reports/report-<主题>.py`
- [ ] 改 `META`（title/icon/group）
- [ ] 按标准结构填正文，调 lib 组件/图表
- [ ] `streamlit run app.py` 冒烟通过
- [ ] git commit（云阶段再 push GitHub）

## 云部署（占位，后续阶段）

目录已对齐 Streamlit Community Cloud。后续：写报告 → push GitHub main → Community Cloud 自动重新部署 → 返回公网 URL 发给用户。本指引在云打通后补「push + 取 URL」步骤。
````

- [ ] **Step 2: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/references/report_to_streamlit.md
git commit -m "docs(streamlit): add references/report_to_streamlit.md agent guide"
```

---

## Task 11: 接线 SKILL.md + 根 CLAUDE.md

**Files:**
- Modify: `generating-insights-report/SKILL.md`
- Modify: `CLAUDE.md`（根）

- [ ] **Step 1: 更新 SKILL.md 的格式说明表 + 参考文档段**

当前 SKILL.md 表格 Streamlit 行是 `| Streamlit | Streamlit App URL | 骨架 |`，参考文档段是空的 `- Streamlit`。

把表格那行改为：

```
| Streamlit | 每份报告一个 reports/*.py（遵循指引） | 多页 app（本地 / Community Cloud URL） |
```

把参考文档段那行改为：

```
- Streamlit：`scripts/streamlit/`，接口与编写规范见 `references/report_to_streamlit.md`
```

（用 Edit 工具，old_string 精确匹配现有行。）

- [ ] **Step 2: 更新根 CLAUDE.md 的「关键注意事项」段**

在根 CLAUDE.md 的「关键注意事项」列表里，HTML 报告 / 图片报告 那两条之后，新增一条：

```
- **Streamlit 报告**：用 `scripts/streamlit/`（`streamlit run app.py` 本地预览）；一份报告 = `reports/*.py`，遵循 `references/report_to_streamlit.md`；app.py 用 ast 扫描 META 动态建页，加报告只需丢 .py
```

（用 Edit 工具，anchor 选图片报告那条结尾，在其后插入。）

- [ ] **Step 3: Commit**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git add generating-insights-report/SKILL.md CLAUDE.md
git commit -m "docs(streamlit): wire streamlit report into SKILL.md and root CLAUDE.md"
```

---

## Task 12: 全量验证 + 收尾

**Files:** 无（验证）

- [ ] **Step 1: 全量本地冒烟**

```bash
cd generating-insights-report/scripts/streamlit
streamlit run app.py
```

确认：
- 标题、空状态/模板占位页正常
- 模板页 KPI / 折线 / 柱状 / 洞察卡 / 结论块 / table / expander 全部渲染
- rerun 无异常

- [ ] **Step 2: 加一份 demo 报告验证完整流程，再删**

```bash
cp reports/_template.py reports/report-verify.py
# 用 Edit 把 META.title 改为 "验证报告"、icon 改为 "✅"
```
浏览器确认导航出现「示例 → 验证报告」，渲染正常。然后：

```bash
rm reports/report-verify.py
```

- [ ] **Step 3: 检查 git 状态干净**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst"
git status
```
Expected: `reports/` 下只剩 `_template.py`（+ `data/` 空目录，可保留），工作区其他 streamlit 文件均已提交。

- [ ] **Step 4: 最终 commit（若有清理）**

```bash
git add -A
git commit -m "chore(streamlit): final verification complete" --allow-empty
```

---

## Self-Review 记录

**Spec coverage：**
- §1 定位/范围 → Task 1-12 全覆盖；云服务明确范围外（README/指引占位）
- §2 Plotly 选型 → Task 3 + requirements（Task 1）
- §3 目录结构 → Task 1
- §4 app.py 多页机制（ast META + st.navigation + 空状态）→ Task 5（含 ast 校验 Task 5 Step 2、空状态 Task 8）
- §5 lib API → Task 2/3/4
- §6 报告标准结构 → Task 6 模板
- §7 指引 MD 大纲 → Task 10
- §8 config.toml → Task 7
- §9 requirements → Task 1
- §10 验证策略 → Task 8 / Task 12（REPL + 冒烟，无 pytest）
- §11 云部署路径 → README/指引占位（明确后续）

**Placeholder scan：** 无 TBD/TODO；每步含完整代码或确切命令。

**Type consistency：** `charts.*` 签名在 Task 3 定义、Task 6 模板、Task 10 指引表一致；`cached` 在 Task 2 定义为装饰器、Task 6/10 用 `@cached` 一致；`C.kpi_strip`/`C.section`/`C.insight_card`/`C.conclusion_block` 在 Task 4/6/10 三处签名一致。
