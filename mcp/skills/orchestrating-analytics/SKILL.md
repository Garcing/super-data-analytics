---
name: orchestrating-analytics
description: 数据分析请求的入口编排技能。当用户意图不明（含"分析一下/为什么/看看情况/帮忙看看"等模糊词）、请求涉及多指标多维度需拆解归因、跨多实体多数据源，或需要多轮澄清对齐口径时，先进本技能做轻重分流与全链路编排；用户已给明确 SQL/DAX 或点名具体指标只要执行时可跳过（但受治理指标仍需语义层解析口径）。
metadata:
  skill-series: super-data-analytics
  chinese-name: 分析编排
  mcp-server: sda
  mcp-tools:
    owns: []
    uses:
      - retrieve_search
      - sql_query
      - sql_schema
      - contribute
      - forecast
      - impact
      - chart
      - report_html_publish
---

# orchestrating-analytics（分析编排）

全链路入口路由：把用户的分析请求稳定映射到最新、受治理的数据实体，再编排最小必要技能完成取数、分析、可视化、报告与质检。准确率首先是上下文和口径对齐问题，不是 SQL 生成问题——**口径没对齐不给数字结论**。本技能只管分流与编排，具体方法论由各 owns 技能负责。

## 编排涉及的技能与工具

本技能 owns 无工具，只做路由。各工具契约详见对应技能的 SKILL.md：

| 环节 | 技能 | 用到的工具 |
|---|---|---|
| 语义检索（受治理口径） | retrieving-context | `retrieve_search` |
| 取数 | querying-data | `sql_query`、`sql_schema` |
| 异动归因 / 预测 / 效果评估 | diagnosing-anomalies / predicting-trends / evaluating-impact | `contribute` / `forecast` / `impact` |
| 可视化 | visualizing-data | `chart` |
| 报告交付 | building-reports | `report_html_publish` |
| 成品质检 | validating-analyses | （方法论复核，无专属工具） |

## 何时使用 / 何时不用

**进编排**：
- 请求含"分析、为什么、看看情况、帮忙看看"等开放意图，尚未映射到明确指标。
- 多指标、多维度、多实体、多数据源，需要拆解或归因。
- 需要多轮澄清才能对齐口径（指标名模糊、时间粒度不明、人群范围有歧义）。
- 结果将用于汇报、决策或外部分享的正式交付。

**直连（跳过编排）**：
- 用户给出明确 SQL/DAX，只要求执行 → querying-data。
- "查一下/跑一下"+ 具体指标名 + 明确时间范围，单源单指标 → querying-data。
- 用户明说"直接查"。
- **例外：语义层解析不跳**——即便直连，只要指标是受治理指标（非用户自定义算式），取数前仍先 `retrieve_search` 拿权威定义，防止同名不同义。

## 决策流程

1. **轻重分流**：按上节判断直连还是编排。简单问题不进流程：能 inline 回答的不套链路，能一个技能解决的不串三个。最小必要技能集合是底线。

2. **实体消歧**：模糊指标名先 `retrieve_search` 检索受治理定义（指标、维度、表关系），拿到口径后与用户确认再取数。消歧要点：
   - **同名指标**：不同团队/阶段的同名概念含义不同，确认适用语境。
   - **时间粒度**：日/周/月、完整周期含义、时间字段与范围。
   - **过滤条件**：人群、渠道、排除项。
   - **权威来源**：受治理指标 > 受治理表 > 用户确认的 SQL/数据 > 原始探索；Power BI 不是默认来源。
   只有会实质改变结果的歧义才追问，一次只问最关键的阻塞问题。

3. **SQL Spec 意识**：编排路径下取数前先写下查询规格（内部执行契约，不必展示给用户）：问题、指标 id 与口径、粒度与去重键、时间字段与范围、分组/筛选维度、参与表与 JOIN、输出列。所有 JOIN 严格来自语义层的启用关系链，不猜字段不猜 JOIN。

4. **串联顺序**：
   ```text
   retrieving-context → querying-data → 分析三选一
   （diagnosing-anomalies / predicting-trends / evaluating-impact）
   → visualizing-data → building-reports → validating-analyses 质检 → 交付
   ```
   - 中途口径不明 → 回退到检索补齐，不凭印象补口径。
   - 检索为空、该有的实体/表不在图谱 → 提示可能需要 sync（见 retrieving-context 技能的 reference），不擅自编表编字段。
   - 用户已提供现成数据 → 跳过取数，直接进分析或报告技能。

5. **交付验收**：必须返回**可访问产物**（在线报告 URL / 图片 URL / 结构化数据结果），附口径说明（指标定义、时间范围、来源层级）与缺口声明（影响可信度的数据缺口）。只回复"已完成"不算交付。

## 陷阱与注意

- **简单问题不进编排**：编排是为复杂请求省轮次，不是给简单查数加流程；过度编排和口径错配一样浪费。
- **口径对齐前别先跑数**：同名指标跑错口径，重来一轮比先问一句更贵。
- **三原则**：先确认口径再下结论；最小必要技能集合；交付必须验收。
- **不得用"SQL 能跑"代替口径正确**：查询成功只说明语法对，不代表回答了用户的问题。
- **连续追问复用上下文**：已确认的指标、口径、时间范围直接复用，只有新问题改变了指标/实体/人群/时间/粒度才重新对齐。
