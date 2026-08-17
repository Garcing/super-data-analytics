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
      - retrieve_doc_read
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

### 语义表 SQL 组装规则（受治理指标取数主链路）

语义层命中的「表」分两类，取数方式不同：

- **语义表（逻辑表）**：表节点 `实现方式 = "sql_query"`（如 `semantic.fact_order`）。**库里没有同名物理表**——数据由飞书「SQL 文档」里的查询定义产生，`SQL文档` 字段值为「显示文本\n文档URL」。
  1. 用 `retrieve_doc_read`（retrieving-context 技能）读 SQL 文档**最新正文**——不依赖对话中或记忆里的旧 SQL 副本。
  2. 把文档 SQL 作为该表**别名**（表节点的 `表别名` 字段，如 `ord`）的 CTE 嵌入：
     ```sql
     WITH ord AS ( <SQL 文档正文中的查询定义> )
     SELECT <指标表达式/维度/过滤> FROM ord ...
     ```
  3. **保留文档中的业务逻辑**，只做必要的别名和 Hologres 方言适配；Hologres 拒绝多层 CTE 时改用等价派生表（子查询），不改写逻辑。
- **物理表**：严格按语义层**已启用的表关系链**连接（顺序、类型、条件都来自元数据），不因字段同名自行推断 JOIN；维度补充按维度契约的来源表和关联键 `LEFT JOIN`（除非口径明确要求缩小总体）。

**执行前校验**：字段与别名存在、JOIN 两侧类型与业务含义兼容、维表关联键唯一性足以保持粒度、一对多连接不放大结果。**执行后校验**：空结果/异常全零、关键字段 NULL、时间覆盖、行数与粒度符合预期。**SQL 跑通 ≠ 口径正确**。

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

**例 3：语义表取数（受治理指标主链路）**

`retrieve_search` 命中 GMV 指标，参与计算表 `semantic.fact_order`（`实现方式=sql_query`，`表别名=ord`，`SQL文档` 第二行是 docx URL）。先经 retrieving-context 的 `retrieve_doc_read` 读到查询定义（示意），再组装：

```json
{"sql": "WITH ord AS (SELECT ... FROM dw_trade.... WHERE ...) SELECT date_trunc('day', ord.支付时间) AS day, sum(ord.订单金额) AS gmv FROM ord WHERE ord.支付时间 >= '2026-07-01' GROUP BY 1 ORDER BY 1"}
```

CTE 内是文档原文（保留业务逻辑），外层套指标表达式/时间/维度。下一步：结果交分析/画图技能，交付时注明「口径来自语义层指标 gmv」。

## 陷阱与注意

- **Hologres 走 VPN，偶发握手慢**：connect_timeout 20s；连接报错先怀疑 VPN/白名单，超时可重试一次，连续失败再报用户。
- **语义表不是物理表**：`实现方式=sql_query` 的表跑 `sql_schema`/直接 FROM 会 `relation does not exist`——先查表节点的 `SQL文档` 链接读查询定义（见上文组装规则），别把预期行为当数据缺失上报。
- **SQL 文档永远读最新**：每次取数重新 `retrieve_doc_read`，文档可能已被治理方修改；对话历史里的旧 SQL 副本只作参考。
- **空字段名兜底**：psycopg 对空列名返回空串，内核兜底成 `col_N`（按列序编号）——rows 里出现 `col_0` 这类键即此原因。
- **多条 DAX 批量**：一次 `powerbi_query` 带 1-4 条，优于多次单条调用（每次都要重新认证 + 轮询）。
- **Power BI 权限**：Application（Client Credentials）模式，需 Azure AD 应用已授 Power BI API 权限 + Admin Consent；401/403 按错误提示的三条检查项引导用户找管理员。
- `sql_query` 只接受单条 SQL；写操作不在本技能范围（readOnly）。
- Power BI 结果是 Preview API 原始 JSON，结构可能随微软更新变化，解析按实际字段取。

## 深入参考

- [references/powerbi.md](references/powerbi.md) —— DAX 编写方法论：schema 先行、度量值引用规范、常见错误模式、EVALUATE 语法要点、函数查阅策略。
