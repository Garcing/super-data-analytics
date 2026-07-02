---
name: report-to-streamlit
description: 把分析结论做成可分享的 Streamlit 交互式报告；框架部署一次，报告 .py 推到 Vercel Blob 运行时加载
---

# Streamlit 报告（report → streamlit）

把分析结论做成**交互式**分析报告，挂在线上看板里。Plotly 图表，结论驱动结构。线上看板：**https://super-data-analytics.streamlit.app/**

## 动静分离（与 html/image 一致）

- **静态（仓库，部署一次）**：`app.py` + `store.py` + `lib/` + `requirements.txt` —— 框架。
- **动态（Vercel Blob，按报告推）**：每份报告 = 一个 `.py` 源码，经 `streamlit.js publish` 推到 Blob；`app.py` 运行时 `fetch + exec` 渲染。**加报告不动 git、不重新部署。**
- 报告源码存 `streamlit-reports/<id>.py`，meta（title/summary/tags + 时间）随发布写进单文件索引 `streamlit-reports-index.json` 供线上 app 公开读。

## 何时用 Streamlit 报告

| 场景 | 选 |
|---|---|
| 要交互（hover、筛选、tab 切换）、图表类型多、像轻量 BI、用整个 streamlit 库灵活写 py | **Streamlit** |
| 要静态、可链接、最快分享（按既定模板填数据结论） | HTML（`report_to_html.md`） |
| 要图（海报式、单图） | Image（`report_to_image.md`） |

定位：**报告 = 呈现已得出的结论**（结论先行 + 叙事），不是开放式仪表盘。

## CLI（从 `building-reports/` 目录运行）

```bash
# 发布（--report 三种来源，同 querying-data 的 --query / html 的 --report）
node scripts/streamlit/streamlit.js publish --id <id> \
  [--title --summary --tags] \
  [--report "<py>" | --report @<file> | --report -]
node scripts/streamlit/streamlit.js list                  # 列出全部报告
node scripts/streamlit/streamlit.js get <id>               # 打印某份报告源码
node scripts/streamlit/streamlit.js delete <id>            # 删除
```

- meta flag（除时间外由 agent 填）：`--title`（默认 = id）、`--summary`（一句话）、`--tags "销售,区域,GMV"`（逗号分隔 → 数组）。时间（`created_at` / `updated_at`）由 CLI 自动写。
- 已去掉 `--icon`、`--group`：导航按**首个 tag** 分组（无 tag 归"其他"），不再有侧栏 icon。
- 同 id 重发即覆盖，但 `created_at` 保留首次值（稳定），`updated_at` 每次刷新（与 html 一致）。
- `title` 同时是 **URL 路径**，直达链接 = `https://super-data-analytics.streamlit.app/<title>`（如 `…/区域销售分析`）。**避免 title 出现空格和斜杠**，且全库唯一。
- 索引是单文件 `streamlit-reports-index.json`，条目 schema = `{ id, title, created_at, updated_at, summary, tags }`（与 html 共用）。CLI 用 **ifMatch 乐观锁 + 重试**写（head 强一致校验 + 公开读对比，防并发/陈旧读丢失更新）。所有 blob 设 `cacheControlMaxAge=60`，新报告对线上 app 约 1 分钟可见。

> 凭证 `BLOB_READ_WRITE_TOKEN` 来自 `~/.super-data-analytics/config.json`；该 token = 整个 Blob store 的写权限，注意保管。线上 `app.py` 只读公开 URL，无需 token。

## 报告 .py 约定

- **顶层写 `st.*` 调用即可**（线上 exec 时注入 `__name__=="__main__"`，与本地 `streamlit run` 一致）；不需要 `META` dict、不要用 `if __name__ == "__main__"` 包裹。
- **自包含**：只能 `import` 已装包 + `from lib import ...`；**不能 import 兄弟报告或外部文件**（Blob 里的文件没有文件系统兄弟）。
- **新包必须进 `requirements.txt`**（需重新部署框架）——代码动态、依赖静态。
- **exec 远程代码**：信任边界 = token 持有者（= 你 / agent）。

## 标准结构（结论驱动）

照这个骨架写，**顺序就是叙事顺序**（完整模板见 `scripts/streamlit/templates/report-template.py`）：

```python
from __future__ import annotations
import pandas as pd
import streamlit as st
from lib import charts
from lib import components as C
from lib.data import cached

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
| `load_df(path)` | 按 csv/parquet/xlsx 读文件（绝对路径，或相对 streamlit 目录） |

## 写报告的要点

**数据从哪来**：内联 `pd.DataFrame({...})`（小数据集，零依赖）/ 绝对路径 CSV 用 `load_df` / 跨板块调 `querying-data --source sql` 或 `querying-data --source powerbi`。取数逻辑包进 `@cached` 函数。

**交互**：页内筛选器 `st.multiselect / selectbox / date_input / toggle`（放图表上方）；Plotly 原生 hover/缩放/图例切换默认就有；分段 `st.tabs`；折叠 `st.expander`。

**缓存**：只给确定性函数（同样输入同样输出）加 `@cached`；不给带副作用/依赖时间/依赖 session_state 的函数加。

## 交付流程

1. 写报告：从 `scripts/streamlit/templates/report-template.py` 复制到 `<工作区>/.super-data-analytics/scratch/report-<主题>.py`，改正文（meta 不写文件里，发布时传 flag）。
2. 本地冒烟（在 `scripts/streamlit/` 目录下，`lib` 才能解析）：
   ```bash
   streamlit run <报告.py 的绝对路径>
   ```
   逐项确认——标题 + 至少一张 Plotly 图（hover 可用）+ KPI 条 + 表格渲染、筛选/rerun 不抛异常。**不要止步于「能启动」**，必须确认图真的画出来。
3. 发布（在 `building-reports/` 目录下）：
   ```bash
   node scripts/streamlit/streamlit.js publish \
     --id report-<主题> --title "<标题>" --tags "<标签1>,<标签2>" --summary "<一句话>" \
     --report @<工作区>/.super-data-analytics/scratch/report-<主题>.py
   ```
   立即生效（线上 app 读索引，约 1 分钟缓存刷新后出现），**无需 git、无需部署**。
4. 把**直达链接**发给用户：`https://super-data-analytics.streamlit.app/<标题>`。

## 框架变更（改 app.py / lib / requirements，不常做）

```bash
# 在仓库根
git add building-reports/scripts/streamlit/<改的文件>
git commit -m "feat(streamlit): <改了啥>"
bash building-reports/scripts/streamlit/deploy.sh   # subtree push 到 Garcing/streamlit-reports，Cloud 自动重新部署
```

## 备注

- 报告若要连数据库/带密钥，密钥走 Streamlit Cloud 的 Secrets manager（`.streamlit/secrets.toml`，gitignored）。
- `deploy.sh` 是 fast-forward push；若远端分叉（一般不会，这是 deploy 专用仓库）会报错，需人工排查。
