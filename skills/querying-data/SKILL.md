---
name: querying-data
description: 执行 SDA 数据查询。默认用只读 Hologres/PostgreSQL SQL 查数或查看物理表 schema；仅当用户明确要求 Power BI、DAX 或指定 Power BI 语义模型时走 Power BI。用于执行用户给出的查询，或执行由受治理语义层和 Query Spec 形成的查询；不自行发明业务指标口径。
---

# 查询数据

可靠执行查询，并把结果连同口径、粒度和限制交给下游分析。业务问题尚未解析为明确指标、表、关系和过滤条件时，先用 retrieving-context；复杂请求先用 orchestrating-analytics。

## 数据源选择

默认用 SQL，包括普通查数、指标计算、业务分析、Hologres/PostgreSQL、表 schema 和用户提供的 SQL。

只有下列情况使用 Power BI：

- 用户明确要求 Power BI 或 DAX。
- 用户指定 semantic model / artifact ID。
- 用户提供 DAX 并要求执行。
- SQL 路径不可用，且用户确认改用 Power BI。

“指标、语义层、看板、报表、KPI”这些词本身不触发 Power BI。

## 工具与职责

| 工具 | 职责 |
|---|---|
| `sql_schema` | 内省一个或多个物理表的真实列和类型 |
| `sql_query` | 在强制只读事务中执行一条 SQL；结果不自动截断 |
| `powerbi_schema` | 获取指定 Power BI 语义模型的表、列和度量值 |
| `powerbi_query` | 对同一模型批量执行 1–4 条 DAX，每条有行数上限 |

具体参数、枚举和返回结构以工具列表中的输入/输出 schema 为准。Power BI 细节见 [powerbi.md](references/powerbi.md)。

## SQL 前置契约

业务取数开始前应已明确：

- 指标定义、表达式、过滤条件。
- 统计实体、去重键和目标粒度。
- 时间字段、范围、时区和完整周期。
- 参与表、稳定别名、实现方式和最新 SQL 文档 code 块逐字文本。
- 指标直接引用的表关系 ID、基数与 JOIN 表达式。
- 分组/筛选维度及其直接字段或维表 JOIN。
- 输出列、排序/数量限制与必要检查。

信息不足时返回 retrieving-context / orchestrating-analytics，不从数据库猜口径、表、字段或 JOIN。

## SQL 组装

### 逻辑语义表

`实现方式="sql_query"` 的表是逻辑表：

1. 从语义层取得 `表别名` 和 `SQL文档`。
2. 用 `retrieve_doc_read` 默认 compact 读取文档最新结构化块快照，按文档顺序定位 `type="code"` 的块并使用其逐字 `text`；SQL 读取不需要 full 的 `content.elements`，也不要补 Markdown 围栏。多个代码块的组合方式不明确时先回到 retrieving-context 判断相邻说明，不盲目拼接。
3. 将确认后的完整查询定义作为对应别名的 CTE：

```sql
WITH ord AS (
  <SQL 文档中的完整查询定义>
)
SELECT ...
FROM ord
```

4. 保留业务逻辑，只做必要的别名和 Hologres 方言适配。多层 CTE 不兼容时改为等价派生表，不重写指标逻辑。

不要对逻辑语义表调用 `sql_schema`——物理库中不存在该表，工具会报 ValidationError 并提示改读其 SQL 文档；拼写错误的表名同样会显式报错，不会静默返回空列。

### 物理表与 JOIN

- 不确定列名/类型时，先 `sql_schema`；入参是 `tables: ["schema.table"]`。
- 普通事实表之间只使用指标 `使用表关系` 直接引用的受治理关系；最新版没有表关系链。
- 严格采用关系实体中的参与表、别名、基数和 JOIN 表达式，不因同名字段推断连接。
- 维度已经由事实/语义表输出时直接引用；否则按维度来源表与关联键补 JOIN，默认 `LEFT JOIN`。
- 拉链表按业务日期约束生效/失效区间；只按 ID 连接会重复并使用错误历史状态。
- `1:N` 或多表 JOIN 前先把右表聚合到目标粒度，或明确使用 distinct；不能靠最终 `GROUP BY` 掩盖行数爆炸。

### 指标表达式

- 使用受治理分子/分母、过滤条件和默认时间字段。
- 比率使用安全除法，如 `numerator / NULLIF(denominator, 0)`。
- 人数/个数按 Query Spec 的稳定 ID 去重。
- 不用 `CASE`、名称模式、枚举顺序或“非 A 即 B”发明业务维度。
- 未完整周期不得和完整周期直接比较；周/月按已确认的日历口径截取。

## 执行策略

1. **先估规模**：明细或未知量级先 COUNT、抽样或限定时间；大结果在 SQL 中聚合/LIMIT，工具不会自动截断。
2. **一条只读 SQL**：`sql_query` 强制只读事务；不要尝试 DDL/DML、临时表或多语句脚本。
3. **渐进验证**：复杂查询先验证各 CTE 粒度与关键键，再组合最终查询。
4. **保留实际查询**：高风险交付、复核或用户要求时提供实际执行 SQL；普通查数不默认倾倒长 SQL。

## 查询前检查

- 表别名、字段名和类型存在。
- 指标表达式引用的别名都在 sources 中。
- JOIN 两侧字段业务含义与类型兼容。
- JOIN 基数和维表唯一性保持目标粒度。
- 过滤、排除项、时间范围和时区完整。
- 每个用户要求的维度都经过语义解析。

## 查询后检查

至少检查：

- `columns`、`row_count` 与目标输出是否一致。
- 是否空结果、异常全零、关键字段大量 NULL。
- 明细行数、主实体 distinct 数、JOIN 前后放大率。
- 结果粒度和分组是否符合 Query Spec。
- 最小/最大日期及最新分区是否覆盖所问窗口。
- 总计与分项、分子与分母、比例范围等数学约束。

SQL 成功运行只说明语法和权限通过，不说明业务答案正确。异常时先缩小到单表/单期/单实体定位，再决定修 SQL、补语义或说明数据问题。

## Power BI 流程

1. 从用户指定、语义层“数据看板”的 Power BI 模型 ID，或已确认配置取得 artifact ID；不得猜 GUID。
2. 先调用 `powerbi_schema`，确认表、列和度量值的精确名称。
3. 根据 schema 写 DAX；同一模型需要多个小查询时可在一次 `powerbi_query` 中批量提交 1–4 条。
4. 使用 `max_rows` 控制每条结果；需要全量时优先在 DAX 中聚合，不盲目把上限调大。
5. 返回结果时说明使用的模型 ID、度量值/字段和过滤上下文。

不得凭 SQL 表结构猜 DAX 名称，也不得把 SQL 和 Power BI 的同名指标默认视为同一口径。

## 结果交付

轻量查数至少返回：结果、采用口径、时间范围、主要筛选、来源层级和数据最大日期（可查时）。

下游接口：

- 上涨/下跌原因 → diagnosing-anomalies。
- 未来值/目标 → predicting-trends。
- 实验/活动效果 → evaluating-impact。
- 数值精确单图 → visualizing-data。
- 正式报告 → building-reports；高风险交付前 validating-analyses。

## 常见失败

- 逻辑语义表 schema 报不存在：改为读取 SQL 文档的 code 块 `text` 并包装 CTE。
- 物理表列不存在：用 `sql_schema` 获取真实名称，不连续猜字段。
- 一对多 JOIN 放大：先聚合右表，复核 distinct 主键和覆盖率。
- 空结果：先检查时间字段/时区、过滤值、数据新鲜度和 INNER JOIN 丢失。
- Power BI schema/query 超时或失败：按工具错误修复身份、模型 ID 或 DAX；不要静默改走 SQL。
