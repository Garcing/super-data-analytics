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
2. SQL 直接按下文执行；Power BI 执行前完整阅读 [`references/powerbi.md`](references/powerbi.md)。
3. 检查查询与上游规格一致后执行。
4. 检查结果并返回必要的来源、时间和限制说明。

## SQL

### 查询契约

执行生成的 SQL 前，应已有：

- 指标表达式、过滤条件
- 统计粒度与去重键
- 时间字段和范围
- 参与表、稳定别名及最新 SQL 文档正文
- 表关系链
- 维度、筛选和输出要求

信息不足时返回 `orchestrating-analytics` / `retrieving-context`，不要从数据库猜口径、表、字段或 JOIN。

### 组装规则

- 保留语义表 SQL 的业务逻辑，只做必要的别名和方言适配。
- 使用语义层约定的表别名；将 SQL 文档作为 CTE 或子查询嵌入。若 Hologres 拒绝多层 CTE，改用等价派生表，不改写业务逻辑。
- 普通表严格按已启用关系的顺序、类型和条件连接，不因字段同名自行推断。
- 维度只有 `field` 时直接引用已确认语义一致的字段；同时提供 `join` 时，按维度契约的来源表和关联键补充连接。
- 不以相似字段、名称模式、枚举顺序、`CASE` 或“非 A 即 B”发明业务维度，除非治理元数据明确规定映射。
- 严格使用指标表达式、默认时间字段、过滤条件和 SQL Spec 输出粒度。

### 校验

执行前检查字段与别名存在、JOIN 两侧含义和类型兼容、维表关联键唯一性足以保持粒度、一对多连接不会放大结果。

执行后检查：

- 返回列、行数和粒度
- 空结果、异常全零、关键字段 NULL 和时间覆盖
- 关联前后业务键数量、重复与维度匹配率
- 数据新鲜度及适用的数学、业务约束

不得因为 SQL 成功运行就宣称口径正确。

### CLI

```bash
node scripts/query.js sql test-connection
node scripts/query.js sql schema <schema.table> [schema.table ...]
node scripts/query.js sql query --sql "<SQL>"
node scripts/query.js sql query --sql @<file>
node scripts/query.js sql query --sql -
```

复杂 SQL 默认通过 stdin 执行；需要审阅、复跑或留痕时才保存为文件并使用 `@<file>`。含 `$`、反引号或多行内容时避免直接 inline。PowerShell 管道必须将 `$OutputEncoding` 和控制台输出设为 UTF-8。

## Power BI

Power BI 只是兼容分支。命中前述显式条件时，完整阅读 [`references/powerbi.md`](references/powerbi.md)，再按其中的模型发现、schema 确认和 DAX 执行流程操作。正文使用 `--payload '<JSON>'`、`--payload @<file>` 或 `--payload -`。

## 结果落盘

`--output <file>` 仅在用户明确要求结果落盘时使用。结果目录建议：

```text
<工作区>/.super-data-analytics/results/
```

## 环境

- Node.js `>=20.0.0`
- 在 `querying-data/scripts/` 执行 `npm ci`
- 凭证来自 `~/.super-data-analytics/config.json`
  - SQL：`HOLOGRES_HOST`、`HOLOGRES_PORT`、`HOLOGRES_DATABASE`、`HOLOGRES_USER`、`HOLOGRES_PASSWORD`
  - Power BI：`POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID`
- `SQL_QUERY_STDIN_TIMEOUT_MS` 可调整 stdin 超时

Power BI 能力保留为兼容分支，不作为默认查询方法。
