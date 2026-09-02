# Cypher 指南：retrieve_schema 与 retrieve_cypher

真相源：`sda_mcp/skills/retrieving_context.py`（`schema` / `cypher` / `fetch_graph_context_batch`）。

## retrieve_schema 返回结构逐字段解读

完全从 Neo4j 实时内省，不读 `graph-config`：

```json
{
  "nodes": {
    "指标": {
      "properties": {"指标ID": "STRING", "指标名称": "STRING", "更新频率": "STRING"},
      "unique": ["指标ID", "指标名称"]
    }
  },
  "relationships": ["(:`指标`)-[:`使用`]->(:`表`)"]
}
```

- `nodes.<label>.properties`：属性名 → Neo4j 类型（来自 `db.schema.nodeTypeProperties()`；多类型用 ` | ` 连接，未知为 `ANY`）。**检索内部属性不返回**：`embedding`、`search_text`、`embedding_model`、`embedding_dimensions`、`embedding_updated_at`——写 Cypher 时不要引用它们。
- `nodes.<label>.unique`：来自**当前实际存在节点**的唯一约束字段（`SHOW CONSTRAINTS`，UNIQUENESS / *KEY 类）。这是实体的稳定标识，`WHERE` / `MERGE` 优先用它；无节点的历史约束不会出现。
- `relationships`：数据库中**实际存在的有向边**（不是配置声明），格式即写法——直接照抄进 `MATCH`。多标签节点 label 会拼成 `A:B` 形式。
- 图为空时抛可操作错误提示先 `sync`，不会用遗留约束拼凑 schema。
- 不返回索引详情、embedding 配置、飞书 table_id、建边规则——写查询用不到。

## 写 Cypher 规范

1. **先 schema 后查询**：每次写 Cypher 前先 `retrieve_schema` 拿实时 label、属性和关系，不凭记忆拼。
2. **中文 label / 属性名 / 关系类型必须反引号**：`` MATCH (n:`指标`) WHERE n.`指标名称` = $name ``。模板里的 `:`` `` 转义照抄即可。
3. **只读优先**：`retrieve_cypher` 是**可写库**工具（非 readOnly）。日常问答只用 `MATCH ... RETURN`；任何写操作（MERGE/SET/DELETE）都要明确理由，且明确这是全量 sync 会清掉的临时数据。
4. **参数化值**：能传参就传参（Neo4j 驱动支持），避免拼接引号地狱。
5. **不要手扫全表算 cosine**：向量检索走 `retrieve_search`（内部用向量索引或 Cypher 25 `SEARCH`）；手写逐节点 cosine 全表扫描既慢又绕过索引。同理，全文检索走内置 CJK 索引，不要 `toLower(n.search_text) CONTAINS ...`。
6. 邻居太多时先 `LIMIT`：检索结果的高基数 context 桶会省略 `items` 并带 `truncated` 标记，完整遍历（如展开整棵业务层级）用 Cypher 并限制返回量。

## 图扩展与邻居截断

`retrieve_search` 的图上下文扩展（`fetch_graph_context_batch`）有两个关键行为：

- **发生在融合截断之后**：先 WRRF 融合各来源候选、截取全局 `top_k`，只对最终候选查邻居——所以不会为落选候选浪费查询。
- **每命中、每类邻居标签应用固定阈值 10**：总数不超过 10 时返回按邻居实体 `key_field` 排序的全部邻居；超过 10 时返回 `items=[]`、真实 `total`、`truncated=true` 和 `omitted_reason="high_cardinality"`。自环关系（from=to）双向扩展且排除自身。
- **图扩展可关闭**：默认 `context_mode="auto"`；只需候选发现时传 `context_mode="none"`，服务端跳过邻居查询并为每个结果返回 `context={}`。

因此检索结果 `context` 里高基数邻居只保留计数属于正常现象：某指标关联 50 张表时 `items=[]`，但 `total=50`、`truncated=true`。需要完整邻居（全量列举、递归层级）时，改用 `retrieve_schema` + `retrieve_cypher` 自己写有界遍历，例如：

```cypher
MATCH (m:`指标` {`指标ID`: $id})-[:`使用`]->(t:`表`)
RETURN t.`表名` ORDER BY t.`表名`
```
