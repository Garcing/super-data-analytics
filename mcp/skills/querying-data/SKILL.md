---
name: querying-data
description: 从 Hologres 跑 SQL 取数或对 Power BI 语义模型执行 DAX 查询。适用于查数、取数、跑 SQL、看表结构、Power BI / DAX 查询等场景；是全链路「检索口径 → 取数 → 分析」中的执行环节。
metadata:
  skill-series: super-data-analytics
  chinese-name: 数据查询
  mcp-server: sda
  mcp-tools:
    owns:
      - sql_query
      - sql_schema
      - powerbi_schema
      - powerbi_query
    uses:
      - retrieve_search
---

# querying-data（数据查询）

通过 `sda` MCP 服务执行取数：默认路径是 Hologres（PostgreSQL 兼容）单条 SELECT SQL；Power BI 语义模型（DAX）是保留的显式分支，仅当用户明确点名时使用。取数是全链路分析的执行环节——**受治理指标先经 retrieving-context 查口径，再在这里下数**。

## 何时使用 / 何时不用

**用**：
- 用户要具体数据值："上月 GMV 多少"、"拉一下近 30 天日活"。
- 用户问表结构："orders 表有哪些字段？"
- 用户明确给出 DAX、点名 Power BI / 语义模型 / artifactId。
- 下游技能（分析三技能、visualizing-data、building-reports）需要数据输入。

**不用**：
- 问指标口径、哪张表、业务概念 → 先 retrieving-context（`retrieve_search`），拿到口径和表归属再来。
- 改写语义层 / 灌图 → retrieving-context 的 `sync`。
- 问题只是"表之间什么关系"且答案在语义层 → `retrieve_search` / `retrieve_cypher`，不必真的跑数。

## 决策流程

1. **SQL 是默认入口**：凡能用 Hologres/PG 查的，一律 `sql_query`，不绕道 Power BI。
2. **Power BI 只走显式分支**：用户明确给 DAX、点名 Power BI、或指定 PBI 语义模型（artifactId）时才用 `powerbi_*`；"从 SQL 降级到 Power BI"也须用户确认。
3. **受治理业务指标先解析口径**：问题涉及语义层治理的指标/表时，先 `retrieve_search`（retrieving-context 技能）拿到受治理定义和表/字段归属，再写 SQL——禁止凭名称猜表猜字段。
4. **写 SQL 前先 `sql_schema` 确认字段名**（列名/类型），尤其是没把握的表；schema 对了 SQL 才一次过。
5. **写 DAX 前必须 `powerbi_schema`**：确认表/列/度量值的准确名称。artifactId 是 GUID，来自用户指定或 config.json 的模型清单（服务未提供 list 工具）。

## 工具契约

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `sql_query` | `sql: str` 必填（单条 SELECT，readOnly）；`max_rows?: int`（预留，内核未用） | `{columns, rows, row_count}`：columns 为 `[{name, dataTypeID}]`，rows 为按列名索引的对象数组，row_count 为行数。行多时先 COUNT 评估量级再决定是否收窄 |
| `sql_schema` | `tables: list[str]` 必填（≥1，`schema.table` 形式，如 `["public.orders"]`） | `{tables: [{schema, table, columns[]}]}`，columns 含列名、类型等定义（来自 PG information_schema） |
| `powerbi_schema` | `artifact_id: str` 必填（语义模型 GUID，格式校验严格） | 语义模型表/列 schema（Fabric MCP `GetSemanticModelSchema` 原始结构，微软 Preview API，字段按实际返回解析） |
| `powerbi_query` | `artifact_id: str` 必填（GUID）；`dax_queries: list[str]` 必填（**1-4 条** DAX，多条批量一次调用）；`max_rows: int=250`（1-1000，每条上限） | 各 DAX 查询的结果（Fabric MCP `ExecuteQuery` 原始结构）。底层 msal 认证 + 202 异步轮询（≤60s），agent 无感；结果结构按实际返回解析，不要硬编码路径 |

## 调用示例

**例 1：sql_schema → sql_query 串联**

先调 `sql_schema` 确认字段名：

```json
{"tables": ["public.orders"]}
```

按返回的列名写 SQL，再调 `sql_query`：

```json
{"sql": "SELECT date_trunc('day', created_at) AS day, count(DISTINCT user_id) AS dau FROM public.orders WHERE created_at >= now() - interval '30 days' GROUP BY 1 ORDER BY 1"}
```

返回 `columns`（含每列名与类型 OID）、`rows`（对象数组）、`row_count`。下一步：结果交给分析/画图/报告技能，或按发现继续追查。

**例 2：powerbi_query 最小示例**（用户已给 artifactId，schema 已确认）

调 `powerbi_query`：

```json
{"artifact_id": "11111111-2222-3333-4444-555555555555", "dax_queries": ["EVALUATE ROW(\"test\", 1)"]}
```

返回该 DAX 的查询结果。多条 DAX 一并放进 `dax_queries`（最多 4 条），不要拆成多次调用。

## 陷阱与注意

- **Hologres 走 VPN，偶发握手慢**：connect_timeout 20s；连接报错先怀疑 VPN/白名单，超时可重试一次，连续失败再报用户。
- **空字段名兜底**：psycopg 对空列名返回空串，内核兜底成 `col_N`（按列序编号）——rows 里出现 `col_0` 这类键即此原因。
- **多条 DAX 批量**：一次 `powerbi_query` 带 1-4 条，优于多次单条调用（每次都要重新认证 + 轮询）。
- **Power BI 权限**：Application（Client Credentials）模式，需 Azure AD 应用已授 Power BI API 权限 + Admin Consent；401/403 按错误提示的三条检查项引导用户找管理员。
- `sql_query` 只接受单条 SQL；写操作不在本技能范围（readOnly）。
- Power BI 结果是 Preview API 原始 JSON，结构可能随微软更新变化，解析按实际字段取。

## 深入参考

- [references/powerbi.md](references/powerbi.md) —— DAX 编写方法论：schema 先行、度量值引用规范、常见错误模式、EVALUATE 语法要点、函数查阅策略。
