# Neo4j 图配置逻辑

GraphRAG 这条线的图结构（实体、关系、embedding）全部声明在 `~/.super-data-analytics/config.json` 的顶层 `graph-config` 块里；连库凭证在 `env` 块。本文件讲清楚这套配置的**字段语义、建图与扩图的分工、以及维护时的注意事项**。

> 谁该读这份文档：需要新增/修改实体或关系、调整 embedding、排查"为什么某条边没建上/没扩出来"、或想理解 sync 与 query 两阶段如何协作时。

## 配置总览

```jsonc
{
  "env": {
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_DATABASE": "neo4j",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "...",
    "FEISHU_GRAPH_BITABLE_APP_TOKEN": "..."   // 飞书多维表格 base token，数据来源
  },
  "graph-config": {
    "embedding": { "model": "BAAI/bge-small-zh-v1.5", "dimensions": 512 },
    "entities": { /* 见下 */ },
    "relationships": [ /* 见下 */ ]
  }
}
```

- `env`：sync.py 启动时把 `env` 块灌进 `os.environ`（已有环境变量优先），retrieve.js 直接读 `config.env`。两边都不读 `.env`、不依赖环境变量导出。
- `graph-config`：纯图结构声明，sync 与 query 共用。

## embedding 块

```json
"embedding": { "model": "BAAI/bge-small-zh-v1.5", "dimensions": 512 }
```

- `model`：HuggingFace 官方 id。本地模型路径由它**约定派生**——取最后一段作为目录名：`scripts/pipeline/models/bge-small-zh-v1.5`。**不再有 `model_path` 字段**，约定优于配置。
- `dimensions`：向量维度，必须和模型实际输出一致（bge-small-zh-v1.5 = 512），建向量索引时用。
- 首次使用前需 `python scripts/pipeline/sync.py --download-model` 把模型下到上述约定目录。

## entities 块

每个实体 = 飞书里的一张多维表格 = Neo4j 里的一种节点标签。

```json
"指标": { "table_id": "tbls2R3wqBBYfSDM", "key_field": "指标ID" },
"维度": { "table_id": "tblzgo2FcMG7eSwR", "key_field": "维度ID" },
"表关系": { "table_id": "tblhMmvHGmEh9MWx", "key_field": "表关系ID" }
```

| 字段 | 必填 | 语义 |
|---|---|---|
| `table_id` | 是 | 飞书多维表格的 table id（在飞书 URL 里能取到）。sync 时按它拉数据。 |
| `key_field` | 是 | 该实体的**业务主键字段名**。建节点时 `MERGE (n:标签 {key_field: 值})`，保证幂等；扩图/查询时也用它做人类可读的节点身份。 |
| `vector_index` | 否 | 是否建向量索引、参与语义检索。默认 `true`。设 `false` 的实体只通过关系被扩到，不直接被 `--question` 向量命中。 |

当前 8 个实体：业务线、业务板块、业务小点、数据看板、指标、维度、表、表关系。

主键约定：
- 指标使用稳定短 ID `指标ID`，不要用可能改名的指标名称。
- 维度使用公式字段 `维度ID`（如 `ord.order_id`），保证同名维度不会合并。
- 表关系使用 `表关系ID`；它是一等实体，不再把整行关系压成一条简单的表↔表边。

## relationships 块

每条关系描述"两个实体之间怎么连边"。有**两种互斥的建边机制**：

### 模式 A：`match`（字段值直接匹配）

```json
{ "type": "包含", "from": "业务线", "to": "业务板块",
  "match": { "source_field": "业务线名称", "target_field": "业务线名称" } }
```

建边规则（在 `graph_builder.py` 的 direct-match 分支）：

```
from 表记录的 source_field 值  ==  to 表记录的 target_field 值
        → 建一条 (from节点)-[:type]->(to节点) 的边
```

**两个字段分属两张表**：
- `source_field` 在 **from 实体**的飞书表里读
- `target_field` 在 **to 实体**的飞书表里读

外键落在 from 侧还是 to 侧都行，取决于业务表怎么建。例如：
- 业务线→业务板块：外键在 to 侧（业务板块表存"业务线名称"外键）
- 指标→表：外键在 from 侧（指标表的多选字段"参与计算表"）
- 表关系→前置表关系：自关联字段"前置关系ID"匹配"表关系ID"

**多选字段自动展开**：只有当前关系配置的 `source_field` / `target_field` 会逐值匹配；同一记录里的其他多选字段不会参与展开，避免产生无关的笛卡尔积。

### 模式 B：`via`（中间表关联，兼容能力）

```json
{ "type": "关联", "from": "表", "to": "表",
  "via": { "table_id": "tblhMmvHGmEh9MWx", "from_field": "从表", "to_field": "到表",
           "properties": ["关联类型", "关联表达式"] } }
```

当两个实体是多对多、且无法靠字段直接匹配时，用一张**独立的中间表**（飞书里另建一张"关联关系表"）。中间表每行 = 一条边：

- `table_id`：中间表的飞书 table id
- `from_field` / `to_field`：中间表里分别存"from 实体的 key_field 值"和"to 实体的 key_field 值"的两列
- `properties`（可选）：中间表里要作为**边属性**写到关系上的列（如关联类型、关联表达式）

> `match` 和 `via` 互斥：一条关系二选一，不会同时出现。

当前语义层不使用 `via`。表关系包含前置关系、累积结果集和多表 JOIN 条件，不能简化成一条表↔表边，因此建模为独立的"表关系"实体。

当前 9 条关系全部使用 `match`：

| from | type | to | source_field → target_field |
|---|---|---|---|
| 业务线 | 包含 | 业务板块 | 业务线名称 → 业务线名称 |
| 业务板块 | 包含 | 业务小点 | 业务板块名称 → 业务板块名称 |
| 指标 | 使用 | 表 | 参与计算表 → 表名称 |
| 指标 | 启用 | 表关系 | 使用表关系 → 表关系ID |
| 指标 | 常用维度 | 维度 | 常用维度组 → 维度组 |
| 维度 | 来源于 | 表 | 来源表 → 表名称 |
| 表关系 | 起始于 | 表 | 起始表 → 表名称 |
| 表关系 | 加入 | 表 | 加入表 → 表名称 |
| 表关系 | 基于 | 表关系 | 前置关系ID → 表关系ID |

## 表关系链

一条表关系记录只表示一个 JOIN 步骤：

- 没有`前置关系ID`：从`起始表`开始，再连接`加入表`。
- 有`前置关系ID`：先递归执行前置关系，再把当前`加入表`连到累积结果集。
- `JOIN条件`可引用前置关系已经提供的全部表别名。

例如 `date-staff-quality` 先基于 `date-staff` 得到日期×员工结果集，再同时使用日期键和员工键连接质检事实表。查询阶段会递归返回完整关系链，并以最大 10 层限制防止异常循环无限展开。

## 建图与扩图的分工（关键）

**两阶段职责分离，是这套配置最重要的设计原则。**

| 阶段 | 谁干 | 用到配置的什么 | 产出 |
|---|---|---|---|
| **sync**（写） | `graph_builder.py` 读 `entities` + `relationships` | 按 `match`/`via` 规则算出所有边，`MERGE` 进 Neo4j | 库里物理存在的节点和边 |
| **query**（读） | `retrieve.js` 的 `fetchGraphContext` | 只看关系的 `type`/`from`/`to`，**完全不读 `match`/`via`** | 沿库里已有边扩出邻居 |

换句话说：
- **`match` / `via` 是 sync 阶段的"建图说明书"**——告诉 sync 怎么算边。算完写进库，说明书就可以扔了。
- **扩图阶段不需要、也不应该重新算关系**。边已经在库里躺着，查询时直接 `MATCH (n)-[:type]-(other) WHERE elementId(n)=$id` 沿边走即可，不管这条边当初是 `match` 建的还是 `via` 建的。

这条原则的历史教训：早期 `fetchGraphContext` 曾试图在扩图时重新读 `rel.match.source_field` 去定位起点，结果遇到 `via` 型关系（没有 `match`）直接 `TypeError` 崩溃。根因就是查询代码越界去干了建图的活。现在扩图只用节点 `elementId` + 关系类型，对两种建边机制一视同仁。

## 维护指南

### 新增一个实体
1. 在飞书多维表格里建好表，记下 `table_id`。
2. `graph-config.entities` 下加一项：`key_field` 选业务上能唯一标识的字段；要语义检索就留 `vector_index` 默认，否则设 `false`。
3. 如果它和其他实体有关系，按下面"新增关系"配。
4. 重跑 `python scripts/pipeline/sync.py`（默认全量重建）。

### 新增一条关系
- **能靠字段值匹配**的优先用 `match`：确认 from 表的 `source_field` 和 to 表的 `target_field` 值能对上（注意多选字段会自动展开）。
- **多对多、靠中间表**的用 `via`：在飞书建好中间表，配 `from_field`/`to_field`（这两列存的是两端实体的 `key_field` 值）。
- `type` 是 Neo4j 里的关系类型名，中文也可，扩图时按它走。
- 改完跑 `python scripts/pipeline/sync.py --only graph` 重建图（不用重算向量）。

### 换 embedding 模型
1. 改 `graph-config.embedding.model`（用 HF 官方 id）和 `dimensions`。
2. `python scripts/pipeline/sync.py --download-model` 下新模型。
3. `python scripts/pipeline/sync.py --force-embed` 全量重算 embedding（模型变了维度可能变，必须重建向量索引）。

### 排查"边没建上"
1. 先 `node scripts/retrieve.js schema` 确认配置被正确读入。
2. 用 Cypher 直接查：`node scripts/retrieve.js cypher --statement "MATCH (a:实体A)-[:关系类型]->(b:实体B) RETURN count(*)"`。
3. count=0 多半是 `match` 字段值对不上（飞书里两表的值拼写/空格不一致），或 `via` 中间表的 `from_field`/`to_field` 取错了列。

### 排查"扩图没扩出来"
- 扩图只沿**库里已建的边**走。先按上一条确认边存在。
- 注意 `vector_index:false` 的实体不会被 `--question` 直接命中，只能作为别的命中节点的邻居出现在 `context` 里。
- 扩图按 `relationships` 里 `from`/`to` 命中当前 label 的关系展开，自环关系（from===to，如 表-关联-表）会自动排除起点自身。
