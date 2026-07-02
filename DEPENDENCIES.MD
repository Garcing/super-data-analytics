# Dependencies

## 凭证与配置如何工作

本框架**不读 `.env`、不读散落的 yaml**。所有运行时凭证统一来自用户主目录下的 `~/.super-data-analytics/config.json`，作为唯一真相来源，由各 skill 的 `scripts/` 读取。结构分两块：

- **`env` 块**：数据库、Neo4j、飞书、Vercel Blob、apimart、`PYTHON_PATH` 等所有凭证
- **`graph-config` 块**：仅 `retrieving-context` 用，定义 embedding 模型、飞书表 → Neo4j 标签映射、关系匹配规则

外部工具用各自配置：`lark-cli` 走 `lark-cli config init` + `lark-cli auth login`；Vercel CLI 用 `VERCEL_TOKEN` 环境变量（仅部署时需要）。

skills 目录保持纯净——动态产物（生成的图片、报告留痕、临时 JSON）落到 `<工作区>/.super-data-analytics/`，已 gitignore。

## 本项目依赖

| 类别 | 用途 | 具体依赖 | 凭证 / 配置 |
| --- | --- | --- | --- |
| 运行时（Node.js） | 取数、查询、报告发布、模板管理 | Node.js 18+（Vite 6 / `@vercel/blob` 2 / `neo4j-driver` 5 / `pg` 8 / `undici` 6+） | 各 `scripts/package.json` |
| 运行时（Python） | GraphRAG 同步与向量化、预测 / 归因 / 效果评估脚本、图表渲染 | Python 3.10+ | `config.json` 的 `env.PYTHON_PATH` 指定解释器 |
| 图数据库 | GraphRAG 业务知识存储（指标定义、表结构、业务层级） | Neo4j 5.x（本地实例，`bolt://localhost:7687`） | `config.json` 的 `env.NEO4J_*` |
| Embedding 模型 | `retrieving-context` 中文语义检索向量化 | `BAAI/bge-small-zh-v1.5`（首次 `node sync.js --download-model` 下载到 `scripts/pipeline/models/`） | `config.json` 的 `graph-config.embedding` |
| BI / 数据仓库 | 指标取数 | Power BI 语义模型（Azure AD 鉴权）+ PostgreSQL | Azure AD client_id / 数据库连接串 |
| 飞书 | GraphRAG 数据源 + 报告模板存储 + 文档交付 | 飞书多维表格 + 飞书云文档 | `config.json` 的 `env.FEISHU_GRAPH_BITABLE_APP_TOKEN` + `lark-cli` 授权 |
| 前端托管 | HTML 报告公网访问 | Vercel 项目 `super-data-analytics`（域名 `www.super-data-analytics.online`）+ Blob Store | `config.json` 的 `env.BLOB_READ_WRITE_TOKEN` / `env.VERCEL_REPORTS_URL` |
| 报告托管（Streamlit） | Streamlit 报告线上多页 app | Streamlit Community Cloud（监听 `Garcing/streamlit-reports` 仓库） | `deploy.sh` subtree push |
| AI 生图 | 图片报告 | apimart gpt-image-2（异步提交 → 轮询 → 下载） | `config.json` 的 `env.APIMART_API_KEY` / `env.APIMART_BASE_URL` |

## 各 skill 依赖明细

### querying-data（取数）

Node.js，`scripts/package.json`：

- `@azure/identity` ^4 —— Power BI 通过 Azure AD 取 token
- `pg` ^8 —— PostgreSQL 驱动
- `xlsx` ^0.18 —— 结果导出 Excel

### retrieving-context（业务知识图谱）

Node.js + Python 双层。

Node 层（`scripts/package.json`）：

- `neo4j-driver` ^5 —— 查询 CLI 连 Neo4j

Python 层（`scripts/pipeline/requirements.txt`）：

- `neo4j` >=5.0
- `sentence-transformers` >=2.0 —— 本地 bge 模型推理
- `pyyaml` >=6.0

外部 CLI：`lark-cli`（拉飞书多维表格字段与记录，参考 `using-templates/references/lark-cli-setup.md`）。

### using-templates（报告模板）

Node.js，`scripts/package.json` 无第三方依赖（纯 ESM）。外部依赖 `lark-cli` 操作飞书个人文件夹中的模板。

### diagnosing-anomalies / predicting_trends / evaluating-impact（分析方法论）

Python 标准库 + 轻量计算（`numpy` 等数值计算），无重型 ML 框架。各自内置脚本：

- `diagnosing-anomalies/scripts/contribution.py` —— 加法 / 乘法 / 比率型贡献度
- `predicting-trends/scripts/forecast.py` —— naive / 移动平均 / 指数平滑 / Holt 线性 / 趋势回归等
- `evaluating-impact/scripts/impact.py` —— A/B 率值 / 均值、DID、ROI、样本量估算

### visualizing-data（确定性单图）

Python：`matplotlib` + `seaborn` + `pandas` + `pillow`（PNG 非空检查）。无 `requirements.txt`，按需安装：

```bash
pip install matplotlib seaborn pandas pillow pytest
```

### building-reports（报告生成）

Node.js，多个子目录各有独立 `node_modules`：

- `scripts/`（共享）：`@vercel/blob` ^2.5、`undici` ^6 —— Blob 读写 + 代理友好的 fetch
- `scripts/html/`：`react` ^18、`react-dom` ^18、`react-router-dom` ^7、`recharts` ^2、`undici` ^8；devDeps `vite` ^6、`@vitejs/plugin-react` ^4、`tailwindcss` ^3、`postcss`、`autoprefixer`
- `scripts/image/`：`undici` ^8 —— 调 apimart
- `scripts/streamlit/`：Python，`requirements.txt` = `streamlit`>=1.36、`pandas`>=2.0、`plotly`>=5.20

外部：Vercel CLI（部署 HTML，token 来自 `config.json`）。

## 安装速查

每个 skill 的 `scripts/` 子目录独立装依赖，互不污染：

```bash
# Node 依赖（各目录单独装）
cd querying-data/scripts && npm install
cd retrieving-context/scripts && npm install
cd using-templates/scripts && npm install
cd building-reports/scripts && npm install
cd building-reports/scripts/html && npm install
cd building-reports/scripts/image && npm install

# Python 依赖
cd retrieving-context/scripts/pipeline && pip install -r requirements.txt
cd building-reports/scripts/streamlit && pip install -r requirements.txt

# 可视化（无 requirements 文件）
pip install matplotlib seaborn pandas pillow pytest

# 外部 CLI
npm install -g @anthropic-ai/lark-cli   # 飞书操作
lark-cli config init && lark-cli auth login
```

## 测试

```bash
python -m pytest predicting-trends/tests/test_forecast.py -q
python -m pytest visualizing-data/tests/test_chart_cli.py -q
```
