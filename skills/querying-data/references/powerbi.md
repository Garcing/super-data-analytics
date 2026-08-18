# Power BI 语义模型用法（DAX 查询）

Power BI 是 querying-data 的显式保留分支，不是默认查询路径：仅当用户明确要求 Power BI、DAX、指定语义模型 / artifactId，或确认从 SQL 降级时使用。普通指标和取数默认走 SQL（`sql_query`）。

执行入口是 `sda` MCP 服务的两个工具（本文件不再有 CLI / Node 命令）：

- `powerbi_schema` —— 获取语义模型表/列 schema（写 DAX 前必查）。
- `powerbi_query` —— 对语义模型批量执行 1-4 条 DAX。

底层经 Microsoft Fabric MCP HTTP 端点（`https://api.fabric.microsoft.com/v1/mcp/powerbi`），Azure AD Client Credentials 零交互认证 + 202 异步轮询，全部由服务封装，agent 无感。

## artifactId 怎么拿

`artifact_id` 是必填的语义模型 GUID，服务不做任何回落——没带就报格式错误。获取顺序：

1. **上游上下文已给**（业务方明确指定了看板/模型）→ 直接用。
2. **未给 ID，但用户指定了业务看板** → 用 `retrieve_search` 检索「数据看板」实体，从其 `PowerBI语义模型ID` 取得候选，并核对看板名称/业务范围。
3. **语义层也没有候选** → 请用户提供 artifact ID 或明确模型；服务没有 list 工具，客户端不能读取服务器本地 config，也不能猜 GUID。

## 调用形态

```json
{"artifact_id": "11111111-2222-3333-4444-555555555555", "max_rows": 100, "dax_queries": ["EVALUATE TOPN(10, 'Sales')"]}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `artifact_id` | string (GUID) | 是 | 语义模型 ID，格式严格校验 |
| `dax_queries` | string[] | 是 | 1 到 4 条 DAX 语句，每条非空；多条批量一次调用 |
| `max_rows` | int | 否 | 1..1000，默认 250，每条查询的行数上限 |

## DAX 编写检查清单

写 DAX 前对照这 4 步自检：

1. 计算的初始筛选上下文是什么？
2. 涉及哪些表？关系和筛选方向？
3. 是否需要 `CALCULATE` 修改筛选器？
4. 完成后检查：是否复用了已有度量值？表/列/度量值名称是否在 `powerbi_schema` 返回里？

## schema 先行

- **写 DAX 前必须先调 `powerbi_schema`**，用返回中的准确名称——表名带空格要加单引号（`'Sales Orders'`），列引用必须带表名（`'Sales'[Amount]`），度量值引用不带表名（`[Total Sales]`）。
- 优先复用模型中已有度量值：度量值封装了口径，直接引用既准确又省查询成本；只有确实没有现成度量值时才用基础列重写表达式。
- schema 返回中的名称大小写、下划线、中文都按原样引用，不要"顺手规范化"。

## 常见 DAX 错误模式

- **列引用漏了表名**：`[Amount]` 在无行上下文时解析为度量值或直接报错——列永远写 `'Table'[Column]`。
- **把度量值当列用**：度量值不能进 `SUMMARIZE` 的 group-by 列，也不能被 `SUM` 等聚合——需要"度量值按维度分组"时用 `SUMMARIZECOLUMNS` 或 `ADDCOLUMNS`。
- **在行上下文里直接引用另一表的列**：跨表取值须 `RELATED`（多对一方向）或改用度量值（度量值自带上下文转换）。
- **`FILTER` 全表扫描**：对大表 `FILTER('Table', ...)` 应换成列级谓词或 `KEEPFILTERS`，让引擎下推。
- **EVALUATE 缺失**：DAX 查询必须以 `EVALUATE <table表达式>` 开头（可配 `DEFINE MEASURE` / `ORDER BY` / `TOPN`）；只有表达式没有 EVALUATE 会报语法错误。

## EVALUATE 语法要点

- 基本形态：`EVALUATE <表>`；常配 `TOPN`、`SUMMARIZE`、`FILTER`、`CALCULATETABLE`。
- 临时度量值用 `DEFINE MEASURE`，随后在 EVALUATE 中引用，避免污染模型。
- 排序用 `ORDER BY <列> [ASC|DESC]`；取前 N 用 `TOPN(N, <表>, <排序列>, <方向>)`。
- 快速自检常量：`EVALUATE ROW("test", 1)`。

## 函数查阅策略

微软官方文档按需查阅，不要猜测函数用法：

- 语法规范：[DAX 查询语法](https://learn.microsoft.com/en-us/dax/dax-queries)（EVALUATE / DEFINE / ORDER BY）。
- 不确定用什么函数 → [DAX 函数板块概览](https://learn.microsoft.com/en-us/dax/dax-function-reference)。
- 知道函数名 → 直接查 `https://learn.microsoft.com/en-us/dax/<函数名小写>-function-dax`（如 `calculate-function-dax`）。

| 板块 | 典型函数 |
|---|---|
| 聚合 | SUM, SUMX, AVERAGEX, MINX, MAXX |
| 日期时间 | DATEADD, SAMEPERIODLASTYEAR, TOTALMTD |
| 筛选 | CALCULATE, FILTER, ALL, KEEPFILTERS |
| 信息 | ISBLANK, HASONEVALUE |
| 逻辑 | IF, SWITCH |
| 关系 | RELATED, USERELATIONSHIP |
| 表操作 | TOPN, SUMMARIZE, VALUES |

## 输出解析

`powerbi_query` / `powerbi_schema` 返回 Fabric MCP 端点的原始 JSON（Preview API），结构可能随微软更新变化——按实际返回字段解析，不要硬编码路径。权限类失败（401/403）的错误信息自带三条检查指引（应用已授权 / 管理员同意 / 租户正确），按提示引导用户处理。
