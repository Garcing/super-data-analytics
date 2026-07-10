# super-data-analytics

面向互联网数据分析的全链路 skill 框架。把一个模糊的数据想法，从**需求对齐 → 业务上下文 → 取数 → 分析 → 可视化 → 报告 → 分发**拆成一串可编排的技能，每个技能是一段带方法论 + 可执行 CLI 的目录。LLM 本身是路由器，读到什么意图就走对应路径。

> 面向 agent 的工程化产物，不是给人直接运行的单体应用。每个 skill 都有自己的 `SKILL.md`（触发与用法）和 `scripts/`（确定性 CLI），agent 按需调用。

---

## 一、整体定位

数据分析类请求天然分轻重：有的是「查一下华东本月流水」一句话能答完，有的是「这个月业绩为什么下滑，出一份复盘报告」需要多技能串联。本框架用一个入口路由技能做轻重分流，再按最小必要技能集合完成任务，避免简单问题被复杂化、复杂问题被敷衍掉。

三大原则：

1. **先确认口径再下结论**——指标定义、时间范围、过滤条件、权威来源没对齐前，不给数字结论。
2. **最小必要技能集合**——能 inline 回答就不进完整对齐流程，能一个技能搞定就不串三个。
3. **正式交付物必须验收**——不只回复「已完成」，要返回可访问的文件 / 链接 / 图片，并说明口径与缺口。

---

## 二、板块架构

```
retrieving-context/              0 语料：检索业务知识图谱（指标定义、数据资产、业务上下文）
aligning-requirements/           1 需求：入口路由，意图识别 + 轻重分流 + 需求对齐 + 流程编排
querying-data/                   2 数据：统一查询入口（数据源子命令 sql / powerbi）
diagnosing-anomalies/            3 分析：指标异动归因方法论 + 贡献度计算脚本
predicting-trends/               3 分析：业务趋势预测和目标制定方法论 + 轻量预测脚本
evaluating-impact/               3 分析：效果评估与实验检验方法论 + A/B / DID / ROI 脚本
visualizing-data/                3 分析：确定性单图（Seaborn/Matplotlib，PNG/SVG）
using-templates/                 4 报告：数据播报 / 周期报告 / 复盘报告模板管理（飞书个人文件夹）
building-reports/                4 报告：按格式（html / image / streamlit / lark）路由生成报告
validating-analyses/             横向质检：交付前复核口径、计算、陷阱、图表与结论置信度
```

### 数据流

```
板块 0（语料）  ← 所有板块可随时引用
板块 1（需求）→ 板块 2（数据）→ 板块 3（分析）→ 板块 4（报告）
```

板块 3 的三个方法论技能互为兄弟：`diagnosing-anomalies` 回答「为什么变了」、`predicting_trends` 回答「未来会怎样 / 目标怎么定」、`evaluating-impact` 回答「做的事情有没有用 / 是否值得继续」。

---

## 三、触发路由

收到数据分析请求时，按意图明确程度选路径（详细规则见 [aligning-requirements/SKILL.md](aligning-requirements/SKILL.md)）。

### 直连路径（跳过对齐）

满足任意一条即直连具体 skill：

- 用户给了明确的 SQL / DAX 语句
- 「跑一下 / 查一下 / 拉一下」+ 具体指标名
- 只涉及单一数据源、单一指标、明确时间范围
- 用户明确说「不需要对齐」「直接查」

### 对齐路径（先走 alignment）

- 请求含「分析 / 为什么 / 看看情况」等模糊词
- 涉及多指标、多维度、需要拆解归因
- 需要跨数据源（同时用 Power BI 和 SQL）
- 意图需要多轮提问才能明确

### 横向服务（任何 skill 执行中都可调用）

| 技能 | 何时用 |
| --- | --- |
| `retrieving-context` | 需要知道指标定义、表名、业务层级、看板位置时 |
| `visualizing-data` | 需要把结构化数据画成数值必须准确的单图时 |
| `aligning-requirements` | 执行中发现需求不明确，可中途补走对齐 |
| `validating-analyses` | 分析/报告交付前，独立复核是否准确、有据、可分享 |

---

## 四、各板块速览

| 板块 | skill 名 | 职责 | 主要入口 |
| --- | --- | --- | --- |
| 语料 | `retrieving-context` | GraphRAG：飞书多维表格 → Neo4j → 向量语义检索 + 图扩展 | `node retrieving-context/scripts/retrieve.js search --question "..."` |
| 需求 | `aligning-requirements` | 入口路由、轻重分流、需求对齐、流程编排、交付验收 | 纯方法论，无脚本 |
| 数据 | `querying-data` | 统一查询，按 `sql\|powerbi` 数据源子命令路由，支持 inline / @file / stdin 三态输入 | `node querying-data/scripts/query.js sql query --sql ...` |
| 分析 | `diagnosing-anomalies` | 异动归因方法论 + 贡献度计算 | `python diagnosing-anomalies/scripts/contribution.py ...` |
| 分析 | `predicting_trends` | 趋势预测和目标制定方法论 + 轻量预测 | `python predicting-trends/scripts/forecast.py <input.json>` |
| 分析 | `evaluating-impact` | 效果评估与实验检验方法论 + A/B / DID / ROI | `python evaluating-impact/scripts/impact.py <input.json>` |
| 分析 | `visualizing-data` | 确定性单图 PNG/SVG | `python visualizing-data/scripts/chart.py --data @spec.json --output out.png` |
| 报告 | `using-templates` | 数据播报 / 周期 / 复盘报告模板生命周期（飞书个人文件夹） | `node using-templates/scripts/templates.js list\|read\|create\|update\|delete` |
| 报告 | `building-reports` | 按格式路由生成报告（html / image / streamlit / lark） | 见下表 |
| 横向 | `validating-analyses` | 分析成品质检：交付前独立复核口径/计算/陷阱/图表，给置信度评级 | 纯方法论，无脚本 |

### building-reports 各格式入口

所有命令在 `building-reports/` 目录下执行。

| 格式 | 输入 | 输出 | 入口 |
| --- | --- | --- | --- |
| HTML | 报告 JSON（meta + summary + conclusions） | Vercel 公网链接 | `node scripts/report.js html ...` |
| Image | 文本提示词（+ 可选 size/quality/model） | 本地图片 + 公网 URL | `node scripts/report.js image generate --prompt ... --output ...` |
| Streamlit | 报告 `.py`（`from lib import ...`） | 多页 app（本地 / Community Cloud） | `node scripts/report.js streamlit ...` |
| 飞书 | lark-doc / lark-slides 要求格式 | 飞书文档 / 幻灯片 URL | 参考 `lark-doc` / `lark-slides` skill |

---

## 五、共享基础设施

### `~/.super-data-analytics/config.json` —— 唯一凭证真相来源

所有可执行 skill 不读 `.env`、不读散落的 yaml，业务凭证统一来自用户主目录下这一份 `config.json`。结构：

- **取数**：`HOLOGRES_*`、`POWERBI_CLIENT_ID` / `POWERBI_CLIENT_SECRET` / `POWERBI_TENANT_ID`
- **GraphRAG**：`NEO4J_*`、`FEISHU_GRAPH_BITABLE_APP_TOKEN`、`PYTHON_PATH`
- **模板**：`FEISHU_TEMPLATE_FOLDER_TOKEN` / `FEISHU_TEMPLATE_DELETE_PASSWORD`
- **报告**：`VERCEL_REPORTS_URL` / `APIMART_API_KEY` / `APIMART_BASE_URL` / `BLOB_READ_WRITE_TOKEN`
- **`graph-config` 块**：embedding 模型、实体映射、关系匹配规则（仅 `retrieving-context` 用）

`PYTHON_PATH` 只服务于 `retrieving-context` 的 Node → Python pipeline。归因、预测、效果评估、可视化和 Streamlit 都直接使用命令中的 Python 解释器及各自 `requirements.txt`。

进程级代理/超时（如 `HTTPS_PROXY`、`SQL_QUERY_STDIN_TIMEOUT_MS`）不是业务凭证，可按需通过环境变量覆盖。完整安装位置、Node/Python 版本与依赖清单见 [DEPENDENCIES.MD](DEPENDENCIES.MD)。

### 运行时产物目录

`<工作区>/.super-data-analytics/`（已 gitignore）：

- `results/` —— 报告脚本落盘的图片、生成的报告留痕
- `scratch/` —— 临时输入 JSON
- `cache/` —— 模板 CLI 的本地缓存

skills 目录本身保持纯净，不放动态资源。

### 三态输入约定

`querying-data` 的 `--sql` / `--payload`、`building-reports` 的 `--report` / `--prompt`、`visualizing-data` 的 `--data`、`retrieving-context` 的 `--question` / `--statement` 都遵循同一约定：

- `-` 或不传 → stdin
- `@<path>` → 读文件
- 其他 → inline JSON / 文本

方便 agent 用 heredoc、临时文件或直接内联三种方式喂入。

---

## 六、外部服务与凭证

| 服务 | 用途 | 凭证位置 |
| --- | --- | --- |
| Neo4j | GraphRAG 业务知识图存储 | `config.json` 的 `env.NEO4J_*` |
| 飞书多维表格 | GraphRAG 数据源（指标定义、表结构、业务层级） | `config.json` 的 `env.FEISHU_GRAPH_BITABLE_APP_TOKEN` + `lark-cli auth` |
| Azure AD（Power BI） | Power BI 语义模型取数鉴权 | client_id `d44d3dbe-...`，Application 类型权限 + Admin Consent |
| Hologres（PostgreSQL 协议） | SQL 取数 | `config.json` 的 `env.HOLOGRES_*` |
| Vercel + Blob Store | HTML 报告前端托管 + 报告 JSON 公网读写 | `config.json` 的 `env.BLOB_READ_WRITE_TOKEN` / `env.VERCEL_REPORTS_URL` |
| Streamlit Community Cloud | Streamlit 报告线上托管 | `Garcing/streamlit-reports` 仓库，自动部署 |
| apimart gpt-image-2 | 图片报告生成 | `config.json` 的 `env.APIMART_API_KEY` / `env.APIMART_BASE_URL` |
| `lark-cli` | 飞书文档 / 多维表格操作（模板管理、lark-doc 交付） | `lark-cli config init` + `lark-cli auth login` |

详细的依赖、版本、安装方式见 [DEPENDENCIES.MD](DEPENDENCIES.MD)。

---

## 七、关键注意事项

- **Vercel 构建缓存**：改前端代码后必须 `rm -rf dist` 再部署。
- **HTML 报告无 serverless**：前端直连 Vercel Blob 读写，没有 API 路由层；用 `scripts/report.js html` 发布 / 列出 / 读取 / 删除。
- **DAX 编写**：必须先通过 `GetSemanticModelSchema` 确认字段名，参考 [querying-data/references/powerbi.md](querying-data/references/powerbi.md)。
- **`@vercel/blob`**：`put()` 必须指定 `access: 'public'`，读取用 `head()` + `fetch(url)`。
- **Streamlit 部署**：发布新报告 commit 后，在 `building-reports/` 下跑 `bash scripts/streamlit/deploy.sh`（subtree push 到 `Garcing/streamlit-reports`）。
- **方法论技能不取数不生图**：`diagnosing-anomalies` / `predicting_trends` / `evaluating-impact` 只提供方法 + 内置轻量计算脚本，取数交给 `querying-data`，画图交给 `visualizing-data`，报告交给 `building-reports`。

---

## 八、测试

```bash
# 异动贡献度脚本
python -m pytest diagnosing-anomalies/tests/test_contribution.py -q

# 预测脚本契约测试（含 CLI / 渲染 / 边界回归）
python -m pytest predicting-trends/tests/test_forecast.py -q

# 效果评估脚本
python -m pytest evaluating-impact/tests/test_impact.py -q

# 图表 CLI 合同 + 渲染 smoke + 边界回归
python -m pytest visualizing-data/tests/test_chart_cli.py -q
```

依赖装哪些、装在哪见 [DEPENDENCIES.MD](DEPENDENCIES.MD)。

---

## 九、文档索引

| 文档 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 给 agent 的精简架构 / 路由 / 部署速查 |
| [DEPENDENCIES.MD](DEPENDENCIES.MD) | 运行时、外部服务、各 skill 依赖清单 |
| [aligning-requirements/SKILL.md](aligning-requirements/SKILL.md) | 入口路由的完整对齐方法论与示例 |
| 各 `<skill>/SKILL.md` | 单个技能的触发词、流程、命令、注意事项 |
| 各 `<skill>/references/` | 输入契约、视觉规范、模型选择、DAX 编写等深度参考 |
