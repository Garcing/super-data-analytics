---
name: querying-data
description: 统一数据查询入口。默认使用 SQL 查询 Hologres/PostgreSQL；仅当用户明确要求 Power BI、DAX 或指定 Power BI 语义模型时使用 powerbi 分支。支持 SQL/PowerBI 的连接测试、schema 获取、查询执行，以及 inline、@file、stdin 三态正文输入。用于执行用户提供的查询，或执行由上游语义层与 SQL Spec 编译出的查询。
---

# 查询数据

在 `querying-data/` 目录执行：

```bash
node scripts/query.js <sql|powerbi> <命令> [参数]
```

本技能负责可靠执行查询，不负责自行定义业务指标。业务问题尚未解析为明确指标、表、关系和过滤条件时，先调用 `orchestrating-analytics` / `retrieving-context`。

## 数据源选择

### 默认：SQL

未明确指定数据源时一律使用 `sql`，包括：

- 普通查数、指标计算和业务分析
- 语义层命中的指标、表、维度和表关系
- Hologres、PostgreSQL、表、字段、schema 或数仓问题
- 用户提供 SQL

### 显式分支：Power BI

只有以下情况使用 `powerbi`：

- 用户明确要求 Power BI 或 DAX
- 用户指定 Power BI semantic model / artifactId
- 用户给出 DAX，并要求执行
- SQL 路径不可用，且用户确认改用 Power BI

“指标、语义层、看板、报表、KPI”本身不再触发 Power BI；这些概念默认通过受治理语义上下文编译为 SQL。

## 执行前置

接受以下任一输入：

1. 用户提供的明确 SQL/DAX。
2. 上游形成的 SQL Spec 和完整语义上下文。
3. 已明确的表、字段、关系、过滤条件和输出要求。

只有模糊业务问题时不要直接猜 SQL。先用 `retrieving-context` 找到指标、参与计算表、关系和维度；需要完整编排时调用 `orchestrating-analytics`。

SQL Spec 引用了飞书 SQL 文档但未提供正文时，在 `retrieving-context/` 下执行：

```bash
node scripts/retrieve.js doc --doc "<Docx URL 或 token>"
```

## 执行步骤

1. 根据上述规则选择数据源。
2. 执行查询前必须完整阅读对应 reference：
   - SQL → [`references/sql.md`](references/sql.md)
   - Power BI → [`references/powerbi.md`](references/powerbi.md)
3. 检查查询与上游规格一致。
4. 执行查询。
5. 检查返回结构、空结果和明显异常。
6. 返回结果及必要的来源、时间和限制说明。

## SQL 查询要求

由语义层组装 SQL 时：

- 使用最新 SQL 文档正文，不使用旧对话中的副本。
- 每张语义表保持约定别名。
- 表 SQL 作为 CTE 或子查询嵌入，保留其业务逻辑。
- 只做必要的字段别名适配和数据库方言调整。
- 严格按语义层表关系链的顺序和 JOIN 条件连接。
- 使用指标计算表达式、过滤条件和默认时间字段。
- 最终输出粒度必须符合 SQL Spec。

执行前检查字段、别名、JOIN、字段类型、聚合粒度、时间范围和排除项。执行后检查行数、空值、重复、异常全零、时间覆盖及适用的业务约束。

不得因为 SQL 成功运行就宣称口径正确。

## 通用输入与输出

正文支持三态输入：

- SQL：`--sql "<SQL>"` / `--sql @<file>` / `--sql -`
- Power BI：`--payload '<JSON>'` / `--payload @<file>` / `--payload -`
- 不传正文 flag 时从 stdin 读取

`--output <file>` 仅在用户明确要求结果落盘时使用。结果目录建议：

```text
<工作区>/.super-data-analytics/results/
```

复杂 SQL 需要用户审阅、复跑或留痕时，保存最终实际执行版本并通过 `--sql @<file>` 运行，确保展示版本与执行版本一致。普通一次性查询优先 stdin，不强制落盘。

## 环境

- Node.js `>=20.0.0`
- 在 `querying-data/scripts/` 执行 `npm ci`
- 凭证来自 `~/.super-data-analytics/config.json`
  - SQL：`HOLOGRES_HOST`、`HOLOGRES_PORT`、`HOLOGRES_DATABASE`、`HOLOGRES_USER`、`HOLOGRES_PASSWORD`
  - Power BI：`POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID`
- `SQL_QUERY_STDIN_TIMEOUT_MS` 可调整 stdin 超时

Power BI 能力保留为兼容分支，不作为默认查询方法。
