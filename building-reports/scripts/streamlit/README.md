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

## 云部署（Streamlit Community Cloud）

线上地址：**https://super-data-analytics.streamlit.app/**（每份报告直达链接 = `线上地址/<报告title>`，如 `…/区域销售分析`）

`scripts/streamlit/` 子目录经 `git subtree` 推成独立仓库 `Garcing/streamlit-reports` 的根，Streamlit Community Cloud 监听其 `main` 分支自动重新部署。

发布新报告：commit 到 skill 仓库后，在 **`generating-insights-report/`** 目录下跑一条命令上线：

```bash
bash scripts/streamlit/deploy.sh
```

详见 [`../../references/report_to_streamlit.md`](../../references/report_to_streamlit.md) 的「交付流程」。
