# Super Data Analytics MCP

Super Data Analytics（SDA）是一个面向 AI Agent 的数据分析 MCP 服务。它把受治理语义检索、数据查询、确定性分析、图表和报告交付统一暴露为 19 个 MCP 工具，并配套 9 个分析 Skill，帮助 Agent 从业务问题一路完成到可交付结果。

服务基于 FastMCP 和 Python，使用 Streamable HTTP，对外只需要一个 MCP URL 和 Bearer Token。运行时可连接 Neo4j、Hologres/PostgreSQL、Power BI、飞书、Vercel Blob 和火山方舟。

## 能力概览

| 能力 | MCP 工具 | 用途 |
|---|---|---|
| SQL 查询 | `sql_query`、`sql_schema` | 查询 Hologres/PostgreSQL 数据与物理表结构 |
| Power BI | `powerbi_query`、`powerbi_schema` | 查询指定 Power BI 语义模型与模型 schema |
| 业务语义层 | `retrieve_search`、`retrieve_cypher`、`retrieve_schema` | 检索指标、维度、数据资产、业务层级和报告模板 |
| 语义层维护 | `retrieve_doc_read`、`retrieve_doc_update`、`sync` | 读取带 revision 的飞书结构化块、按 block ID 精确更新，并同步飞书多维表到 Neo4j |
| 分析计算 | `contribute`、`forecast`、`impact` | 贡献度归因、趋势预测、A/B、DID、ROI 与样本量计算 |
| 数据可视化 | `chart` | 将声明式 JSON 图表规格渲染为准确的 PNG/SVG |
| 报告交付 | `report_html_publish`、`report_html_list`、`report_html_get`、`report_html_delete`、`report_image_generate` | 发布 HTML 报告或生成单张图片报告 |

所有工具都提供结构化输入 schema、返回类型和面向模型的功能说明。业务分析流程由 `skills/` 中的 Skill 编排，工具本身专注于可靠执行。

## 配套 Skill

| Skill | 职责 |
|---|---|
| `orchestrating-analytics` | 分析入口、需求消歧、查询规格和全流程编排 |
| `retrieving-context` | 受治理业务语义检索与语义层维护 |
| `querying-data` | SQL 默认取数与显式 Power BI 查询 |
| `diagnosing-anomalies` | 指标异动确认和贡献度归因 |
| `predicting-trends` | 趋势预测、目标制定和达成判断 |
| `evaluating-impact` | 实验、DID、ROI 和动作效果评估 |
| `visualizing-data` | 确定性单图与数据表渲染 |
| `building-reports` | HTML 报告和图片报告交付 |
| `validating-analyses` | 分析成品的独立复核与交付质检 |

Skill 使用入口见 [`skills/README.md`](skills/README.md)。

## 架构

```text
Claude / Codex / Hermes / 其他 MCP Client
                  │ Streamable HTTP + Bearer Token
                  ▼
             FastMCP 服务
      ┌───────────┼────────────┐
      ▼           ▼            ▼
  MCP 工具层   Python 技能内核   外部服务适配
      │           │            │
 输入/输出契约  确定性计算     Neo4j / Hologres
 错误与内容块   图表和报告     Power BI / 飞书
                              Blob / 火山方舟
```

- `sda_mcp/tools/`：19 个 MCP 工具的注册、参数模型、说明和返回封装。
- `sda_mcp/skills/`：可独立测试的 Python 执行内核。
- `skills/`：供 Agent 阅读的分析方法和工具编排说明。
- `tests/`：单元测试及可选真实服务集成测试。

> Python 包刻意命名为 `sda_mcp`。官方 MCP SDK 已占用顶级包名 `mcp`，本项目若也使用该包名会遮蔽 SDK 并导致服务无法导入。

语义检索采用 Neo4j vector/full-text index、Fastembed 中文向量、精确实体命中和 Weighted RRF 融合。详细设计见 [`docs/neo4j-graphrag-2026-research.md`](docs/neo4j-graphrag-2026-research.md)。

## 快速开始

要求 Python 3.10 或更高版本。

```bash
python -m venv .venv
python -m pip install -e .
```

准备 `~/.super-data-analytics/config.json`，并设置服务 Bearer Token 后启动：

```bash
export SDA_MCP_TOKEN="replace-with-a-long-random-token"
python -m sda_mcp.server
```

默认端点为 `http://127.0.0.1:3100/mcp`。也可以使用 Docker Compose：

```bash
docker compose build
docker compose up -d
```

客户端配置示例：

```json
{
  "mcpServers": {
    "sda": {
      "type": "http",
      "url": "http://YOUR_SERVER:3100/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN"
      }
    }
  }
}
```

不要把真实 Token 或 `config.json` 提交到 Git。

## 测试

```bash
python -m pytest -q
```

当前测试基线为 218 项通过、8 项真实服务集成测试默认跳过。配置好外部服务后，可设置 `SDA_INTEGRATION=1` 执行集成验证。

## 项目维护

开发约定、工具与 Skill 的同步规则、配置矩阵、服务器部署、重新发布、回退和运维检查清单统一记录在 [`AGENTS.md`](AGENTS.md)。

拆分前的旧版 CLI Skill 套件已归档到 [Garcing/super-data-analytics-old](https://github.com/Garcing/super-data-analytics-old)。
