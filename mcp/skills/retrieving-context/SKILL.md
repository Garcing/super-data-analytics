---
name: retrieving-context
description: 检索业务知识语义层（指标定义、口径、表归属、业务层级、报告模板），供下数前查口径、写 SQL 前找表。适用于指标定义与口径、哪张表、数据来源、业务上下文、业务板块、模板等问题。
metadata:
  skill-series: super-data-analytics
  chinese-name: 检索业务知识
  mcp-server: sda
  mcp-tools:
    owns:
      - retrieve_search
      - retrieve_cypher
      - retrieve_schema
      - retrieve_doc_read
      - retrieve_doc_update
      - sync
    uses: []
---

# retrieving-context（检索业务知识）

通过 `sda` MCP 服务的 Neo4j GraphRAG 语义层，检索受治理的业务知识：指标定义与口径、表归属、业务层级（业务线→板块→小点）、数据看板、维度、表关系、报告模板。这是全链路分析的第一环——**下数之前先查口径，写 SQL 之前先找对表**。

## 何时使用 / 何时不用

**用**：
- 用户问业务概念："复购人数是什么口径？"
- 用户问数据来源："听课明细去哪张表查？"
- 用户问业务结构 / 看板 / 维度归属。
- 其他技能（querying-data、分析三技能、building-reports）需要业务上下文或报告模板时。
- 语义层多维表结构变更后需要重灌图（sync）。

**不用**：
- 纯执行 SQL / 查 Power BI 模型 → querying-data。
- 问具体数据值（"上月 GMV 多少"）→ 先本技能定位口径和表，再走 querying-data。
- 已知飞书文档 token 且只要正文 → 直接 `retrieve_doc_read`，不必先检索。

## 决策流程

1. **受治理指标先查口径再下数**：凡问题涉及指标、表、维度等语义层实体，必须先 `retrieve_search` 拿到受治理定义，禁止凭名称猜测口径或表归属。
2. **默认 hybrid 检索**：`retrieve_search` 默认 `strategy="hybrid"`（向量 + CJK 全文 + 精确命中，WRRF 融合）。仅在诊断检索质量问题、需要 A/B 基线时回退 `strategy="vector"`。
3. **需要图上精确遍历**（上下游依赖、层级展开、"X 下有哪些 Y"、计数）→ 先 `retrieve_schema` 拿实时结构，再写 Cypher 走 `retrieve_cypher`。
4. **语义表与 SQL 文档（取数前的关键一步）**：命中的「表」实体看 `实现方式` 字段——值为 `sql_query` 时这是**语义表（逻辑表）**：库中没有同名物理表，其数据由飞书「SQL 文档」里的查询定义产生。`SQL文档` 字段值为「显示文本\n文档URL」（第二行是 docx 链接）→ 剥出 token 用 `retrieve_doc_read` 读正文，查询定义交给 querying-data 按 CTE 组装（组装规则见该技能）。`实现方式` 为其他值或缺省 → 按物理表处理。**别对语义表跑 `sql_schema`**——`relation does not exist` 是预期行为，不是数据缺失。
5. **报告模板（原 using-templates 的替代）**：模板 = 语义层「报告模板」多维表里的行（用 `retrieve_search` / `retrieve_cypher` 发现元数据）+ 其链接的 docx 正文（`retrieve_doc_read` 读、`retrieve_doc_update` 改）。
6. **检索为空 / schema 报图为空** → 图未建或已变更，跑 `sync`（详见 [references/sync-and-maintenance.md](references/sync-and-maintenance.md)）。

## 工具契约

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `retrieve_search` | `question: str` 必填（自然语言）；`top_k: int=5`（1-20；hybrid 为融合后**全局** top_k，vector 为每索引 top_k）；`targets?: list[str]` 限定实体标签（如 `["指标","表"]`，不传=全搜）；`strategy: "vector"\|"hybrid"` 默认 `hybrid` | `{question, strategy, results[]}`；每条含 `label`、`score`（向后兼容=vector cosine，仅全文召回时为 0）、`properties`（业务属性，内部属性已滤）、`context`（图邻居，按关联标签分组）。hybrid 额外有 `retrieval` evidence：`fusion_score`（WRRF 融合分，仅排序用、非概率）、`vector_score`/`fulltext_score`（量纲不同，**禁止直接比较**）、`exact_match`（受治理名称/ID/别名精确命中，未命中 null）、`vector_rank`/`lexical_rank`/`exact_rank`。下一步：读 properties 回答定义类问题，或顺 context 继续遍历 |
| `retrieve_cypher` | `statement: str` 必填（**可写库**，非 readOnly） | `{cypher, rows[]}`；节点自动剥内部属性。写库前先 `retrieve_schema` 确认结构；优先只读 MATCH |
| `retrieve_schema` | 无参 | `{nodes: {label: {properties: {名: 类型}, unique: [字段]}}, relationships: ["(:\`A\`)-[:\`R\`]->(:\`B\`)"]}`，全部来自 Neo4j 实时内省。图为空时返回可操作错误 → 先跑 `sync` |
| `retrieve_doc_read` | `doc: str`（**只收 docx token**——代码不做 URL 解析，从链接里剥出 docx token 再传） | `{content, document_id}`，content 为 markdown。文档须已共享给飞书自建应用，权限报错按提示处理 |
| `retrieve_doc_update` | `doc: str`（**只收 docx token**——代码不做 URL 解析，从链接里剥出 docx token 再传）+ `content: str`（markdown） | `{updated, document_id}`。**覆盖写**非追加（先清空正文块再重灌）；须给应用写权限。只改正文，不碰多维表 |
| `sync` | `dry_run: bool=false`（true=只预检不写库） | 全量重建 飞书多维表 → Neo4j 图 → 向量。何时用：语义层多维表结构变更后、检索/schema 报图为空时。详细契约见 [references/sync-and-maintenance.md](references/sync-and-maintenance.md) |

## 调用示例

**例 1：查指标口径**

调 `retrieve_search`：

```json
{"question": "复购人数是什么口径", "targets": ["指标", "表", "表关系", "维度"]}
```

返回摘要：`results[0]` 为「指标」实体，`properties` 含指标名称、定义、计算说明、参与计算表；`context.表` / `context.表关系` 带出计算链；`retrieval.exact_match` 若非 null 说明精确命中了受治理名称。下一步：按定义向用户复述口径，或转 querying-data 按 `context` 中的表下数。

**例 2：读报告模板正文**

先调 `retrieve_search`（targets 限定「报告模板」标签；该标签以 graph-config 实际配置为准，若未配置则去掉 targets 全搜）：

```json
{"question": "周报 模板", "targets": ["报告模板"]}
```

从「报告模板」行的属性里拿 docx 链接，剥出 docx token；再调 `retrieve_doc_read`：

```json
{"doc": "docxcnXXXXXXXXXXXX"}
```

返回 markdown 正文。下一步：按模板结构组装报告；需要改模板本身时用 `retrieve_doc_update`（覆盖写，先读后拼全量正文）。

## 陷阱与注意

- **精确命中只匹配受治理身份字段**（字段名以 ID 结尾 / 含"名称""别名" / name / alias），不扫定义等长文本——"定义里提到另一个指标"不会被误加权。
- **换 embedding 模型或维度必须全量重算**（重跑 `sync`），新旧向量不可混用；索引维度不匹配会导致向量召回静默为空。
- `retrieve_doc_update` 是**覆盖写**：会把文档正文整体替换，改模板须先 `retrieve_doc_read` 取回原文再拼改后全文。
- 飞书多维表、目标文档、模板 docx 必须**共享给飞书自建应用**，否则 403/权限错误。
- 检索结果 `context` 里邻居被截断（每命中每类关系最多 20 个）属正常现象，需完整邻居时改用 `retrieve_cypher`。
- `score` 在 hybrid 下只是兼容字段，判断融合顺序看 `retrieval.fusion_score`。

## 深入参考

- [references/sync-and-maintenance.md](references/sync-and-maintenance.md) —— sync 两段式流程、dry_run 预检清单、字段类型清洗范围、索引契约、embedding 审计字段。
- [references/cypher-guide.md](references/cypher-guide.md) —— `retrieve_schema` 返回结构逐字段解读、中文 label 的 Cypher 写法、图扩展截断说明。
