# Neo4j GraphRAG / MCP 技术调查与 SDA 采用建议

> 调查日期：2026-08-14；项目实测 Neo4j：Community 2026.04.0；调查范围：SDA 的飞书实体元数据 → Neo4j → embedding → 向量检索 → 图扩展链路。

## 结论先行

1. **Neo4j MCP 不能替换当前 GraphRAG 检索内核。** 它解决的是“让 Agent 发现图 schema、执行任意 Cypher、列出 GDS 过程”的协议接入问题，不负责 embedding、向量召回、混合召回或业务上下文组装。SDA 已有一个更合适的高层 MCP 工具 `retrieve_search`；再暴露官方 Neo4j MCP 会产生重复工具、扩大 Cypher 与写权限面。
2. **旧向量过程应立即换成 `SEARCH`。** Neo4j 2026.01 引入 Cypher 25 `SEARCH`，`db.index.vector.queryNodes` 从 2026.04 起弃用。SDA 已改为 2026.01+ 使用 `SEARCH`、老版本回退旧过程。
3. **不要用 Knowledge Graph Builder 重写同步。** 它主要解决 PDF/文本切块后由 LLM 抽实体和关系，且官方仍标记 KG Builder 为 experimental。SDA 的飞书表已经是结构化、人工治理过的实体与关系；现有确定性导入更便宜、更稳定、可复算。
4. **最值得做的检索升级是 hybrid + graph expansion。** 已在当前向量召回旁增加 CJK 全文召回、受治理实体名精确命中和 RRF，再批量展开图邻居。这样补足中文专名、表名、字段名、缩写、ID 等向量模型容易漏掉的精确词。
5. **`neo4j-graphrag` 适合逐步采用查询侧能力，不宜一次性接管全链路。** 其 `HybridCypherRetriever`、`VectorCypherRetriever`、版本探测和索引辅助函数有价值；但 SDA 有 8 类实体、每类独立索引、动态关系配置和 fastembed，仍需要一层业务编排。直接换库不会自动删除同步、路由和结果契约代码。

## 当前实现与官方能力的对应关系

| SDA 当前能力 | Neo4j 当前官方能力 | 是否替换 | 判断 |
|---|---|---:|---|
| Fastembed 生成 `search_text` embedding | Neo4j GraphRAG embedders / 自定义 `Embedder` | 暂不替换 | 当前 ONNX 方案已解决 3.6GB 服务器内存与中国产线下载问题；官方包没有原生 Fastembed 适配，需薄包装。 |
| 每类实体一个 vector index | Neo4j vector index + Cypher 25 `SEARCH` | 保留索引，升级查询 | 多索引与 `targets` 路由吻合；2026 的多标签索引会让按目标类型过滤更复杂，收益有限。 |
| 向量命中后逐关系扩展 | `VectorCypherRetriever` / `HybridCypherRetriever` | 可逐步替换 | 官方 retriever 能合并“召回 + retrieval query”，但动态关系配置仍需 SDA 生成 Cypher。 |
| 8 个索引结果按原始 cosine score 全局排序 | 官方建议各来源独立排名后做 RRF/WRRF | 应升级 | 不同索引/全文与向量的原始 score 不应直接比较；当前排序存在跨实体偏置风险。 |
| 手工选择 `targets` | `ToolsRetriever` / Agent tool routing | 保留 | 当前路由规则透明、零 LLM 成本；数据规模与实体类型固定，不需要再引入一次 LLM 选择。 |
| `retrieve_cypher` | 官方 Neo4j MCP `read-cypher` | 业务端保留高层工具 | 官方服务更适合开发调试；业务 Agent 应使用受约束工具。现有 `retrieve_cypher` 后续应补只读分类或白名单。 |
| 飞书结构化元数据建图 | experimental KG Builder | 不替换 | KG Builder 面向非结构化内容抽取，会引入成本、漂移和错误合并。 |
| 无 Text2Cypher 自动生成 | `Text2CypherRetriever` | 暂不引入 | 适合开放式图问答，但官方也明确生成查询不保证语法正确；SDA 已有 schema + 上游 Agent 生成 Cypher，重复增加 LLM 调用。 |

## Neo4j MCP 在本项目里的准确定位

官方 Neo4j MCP 当前主要提供：

- `get-schema`：探测节点、关系、属性；
- `read-cypher`：执行经 `EXPLAIN` 与查询分类检查的只读 Cypher；
- `write-cypher`：执行写查询，可通过 `NEO4J_READ_ONLY=true` 禁用；
- `list-gds-procedures`：发现 Graph Data Science 过程。

它是**通用数据库 MCP**，不是 GraphRAG 框架。对 SDA：

- 生产业务入口继续只暴露 `retrieve_search`、`retrieve_schema` 和受控的查询能力；这比让 Agent 自由生成 Cypher 更容易稳定输出既定 JSON 契约，也更节省上下文。
- 若需要让开发者在 Claude/Codex 中临时探索图，可单独部署官方 Neo4j MCP，并强制只读、使用受限 Neo4j 用户、不要挂到 hermes 的最终用户工具集。
- 不建议把官方 MCP 再代理进 SDA MCP；协议嵌套不会改善召回，只会增加一个进程、鉴权面和工具选择歧义。

## 最推荐的目标检索链路

```text
问题
  ├─ 一次 fastembed（沿用 BAAI/bge-small-zh-v1.5）
  ├─ 每个 target 的 vector SEARCH，取 source_k 候选
  ├─ 每个 target 的 CJK full-text search，取 source_k 候选
  └─ 可选精确命中：key/name/table/field 等受治理字段
          ↓
  各来源独立排名 → RRF/WRRF 融合 → 全局 top_k
          ↓
  仅对融合后的 top_k 节点做一次批量图扩展
          ↓
  properties + context + retrieval evidence
```

这比当前流程有三点实质改善：

- 精确术语不会只依赖 embedding：如表英文名、字段、指标缩写、ID；
- 不再把不同索引的 cosine / Lucene score 当作同一量纲；
- 当前实现会先对每类命中的每个节点逐关系查询，再全局排序；改为先融合、后对最终节点批量扩展，可显著减少 Neo4j 往返次数。

全文索引建议继续按实体类型建立在 `search_text` 上，先用当前数据库已确认存在的 `cjk` analyzer（双字切分、归一化、大小写折叠）。不要直接套官方 `HybridRetriever` 默认排序上线：先用项目自己的评测集选择向量/全文权重与候选池大小。

## 分阶段实施建议

### Phase 0：兼容性修复（已完成）

- Neo4j 2026.01+：`CYPHER 25 MATCH ... SEARCH ... SCORE AS score`。
- Neo4j 5.x / 2025.x：回退 `db.index.vector.queryNodes`。
- index name 来自 `SHOW VECTOR INDEXES`，作为 Cypher identifier 转义后插入；embedding 与 top-k 继续参数化。

### Phase 1：建立检索基线（已完成）

- `evals/retrieval_gold.json` 已整理 30 条真实问题，覆盖指标定义、表定位、关系链、维度、英文表名/字段名和业务层级。
- `evals/benchmark_retrieval.py` 输出 Recall@1/5、MRR@5、平均/P95 延迟和逐题排名，不调用 LLM、不写数据库。
- 纯向量基线：Recall@1 70%、Recall@5 93.3%、MRR@5 0.794。

### Phase 2：混合召回与批量图扩展（已完成）

- sync 为各 vector-enabled label 创建对应的 `cjk` full-text index；全文索引由 Neo4j 自动随节点更新。
- 查询侧独立执行向量、全文和受治理 ID/名称/别名精确命中，再用 RRF 融合；不直接相加 cosine 与 Lucene score。
- 图扩展从逐命中、逐关系查询改为按关系方向批量 Cypher，并只扩展融合后的最终候选。
- `retrieve_search` 默认 `strategy=hybrid`，保留 `strategy=vector` 回退；原 `score` 仍表示向量相似度，新增 `retrieval` evidence。
- 30 题 A/B：Hybrid Recall@1 83.3%、Recall@5 100%、MRR@5 0.906，分别较纯向量提升 13.3pp、6.7pp 和 0.112。

### Phase 3：评估引入 `neo4j-graphrag` 1.x

先做一个 feature flag 原型，只替换查询侧：

- 用自定义 `Embedder.embed_query()` 包装现有 cached Fastembed；
- 每个实体配置 `HybridCypherRetriever`；
- retrieval query 由 `graph-config.relationships` 生成；
- 对照自研 hybrid 的准确率、延迟、镜像体积和错误可观测性。

若官方库显著减少代码且评测不回退，再采用；否则保留轻量 Cypher 实现。当前 `pip --dry-run neo4j-graphrag==1.18.0` 显示核心包会新增 `json-repair`、`pypdf`、`types-PyYAML` 等依赖，但无需安装 LLM provider extras；依赖体积不是主要障碍，业务适配和检索契约才是。

### Phase 4：可选实验，不纳入主链

- Text2Cypher：只在只读用户、超时/行数限制、查询审计下实验开放式图问答。
- GDS / FastRP 结构向量：只有 gold set 证明“拓扑相似”是核心召回信号时再引入；当前业务图规模和层级明确，先不增加 GDS 运维面。
- 官方 Neo4j MCP：仅作为开发者只读诊断 sidecar，不面向 hermes 业务用户。

## 不建议现在做的事

- 不因 deprecated 警告而更换数据库、embedding 模型或整套框架；这是一个局部查询语法迁移。
- 不把受治理的飞书行转成文本，再让 LLM 重新抽一遍实体关系。
- 不把全部实体合成单一多标签 vector index 只为了少写循环；当前 `targets` 支持与分类型召回更重要。
- 不把官方 MCP 的 `write-cypher` 暴露给生产 Agent；Neo4j 官方同样建议使用受限用户并审查生成查询。
- 不用原始 score 混排全文、向量或多个索引结果。

## 官方资料

- [Neo4j vector indexes 与 `SEARCH`](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Cypher 25 `SEARCH` 语法和限制](https://neo4j.com/docs/cypher-manual/current/clauses/search/)
- [Neo4j 官方 GraphRAG Python](https://neo4j.com/docs/neo4j-graphrag-python/current/)
- [GraphRAG retrievers：VectorCypher、HybridCypher、Text2Cypher](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html)
- [Knowledge Graph Builder（experimental）](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html)
- [Neo4j hybrid search 与 WRRF](https://neo4j.com/developer/genai-ecosystem/hybrid-search/)
- [Neo4j 官方 MCP](https://neo4j.com/docs/mcp/current/)
- [Neo4j MCP 工具与只读模式](https://neo4j.com/docs/mcp/current/tools/)
- [Neo4j MCP 安全建议](https://neo4j.com/docs/mcp/current/security/)
