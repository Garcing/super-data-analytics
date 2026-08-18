# sync 与语义层维护

真相源：`mcp/sda_mcp/skills/retrieving_context_sync.py`。`sync` 只有一个参数 `dry_run: bool=false`；不要传未声明字段。由于默认值会执行破坏性全量重建，**先明确传 `dry_run=true` 预检再全量**，不要裸调。

## 两段式流程：外部准备全部在清库前

`sync` 是**全量重建**，不是增量。编排顺序（`sync_graph`）：

**阶段 1（预检，零写库）**
1. 校验 `graph-config`：`entities`（每个实体必须有 `table_id`、`key_field`）、`embedding.model`、`embedding.dimensions`（正整数）、每条关系的 `from`/`to` 必须引用已配置实体且 `match.source_field`/`target_field` 齐全。
2. 拉取全部实体多维表记录并清洗字段值。
3. 校验源数据：任一实体无记录 → 停止；`key_field` 重复值 → 停止；主键非标量 → 停止；空主键记录跳过并记入 `warnings`。
4. Fastembed 预检：真实生成一条探测向量，确认模型可加载且**维度与配置一致**（不一致 → ConfigError）。
5. Neo4j 连通性 `RETURN 1`。

**阶段 2（写库，预检全部通过后才开始）**
`_clear_graph`（DETACH DELETE 全部节点）→ 删除全部约束和所有非 LOOKUP 索引 → 建唯一约束 → MERGE 节点 → 建关系 → 生成 `search_text` → 建 vector/fulltext 索引 → 批量 embedding。

**关键保证**：所有可能失败的外部工作（飞书拉数、模型加载、Neo4j 连接）都发生在清库之前——失败不写库，现有图保持原样。

## dry_run 预检清单

`dry_run=true` 完成阶段 1 全部检查 + Neo4j 连通性，不写任何数据。返回：

```json
{
  "dry_run": true, "validated": true,
  "fetch": {"指标": 120, "表": 45},
  "warnings": ["飞书实体 X 有 2 条记录缺主键字段 Y，同步时将跳过"],
  "planned": {"clear_graph": true, "rebuild_constraints": 8,
              "rebuild_relationship_types": 8,
              "rebuild_vector_indexes": 8, "rebuild_fulltext_indexes": 8,
              "regenerate_embeddings": true}
}
```

何时用：变更 embedding 模型、维度或字段结构后，先 dry_run 确认再全量；确认 `fetch` 数量符合预期。

## 幂等性

全量 sync 幂等：每次都清空节点/关系、全部约束和所有非 LOOKUP 索引后按当前配置重建。含义：

- Neo4j 数据库**仅供 SDA 使用**——库里手工建的约束/索引会被删掉。
- 改了 graph-config（删实体/改关系）后历史实体不会残留 schema 对象。
- 节点按 `key_field` MERGE 写入，重复跑不产生重复节点。

## 字段类型清洗（飞书多维表 → Neo4j 原生类型）

目标形态：str / int / float / bool / list[str]。支持范围（`_simplify_value` 按字段 `type` 分派）：

| 类型 | 清洗 |
|---|---|
| Text | `[{text}]` / `{text}` / 纯串 → 拼接字符串，换行保留 |
| URL | `{text,link}` → `显示文本\nURL`（**保留 link**，如 `SQL文档` 字段 agent 靠 URL 读文档正文）；只有 link 时仅存 link |
| Number | 开放平台返回**字符串**（"12.5"）→ int/float |
| DateTime | ms 毫秒时间戳 → `YYYY-MM-DD HH:MM:SS`（+8 时区） |
| Checkbox | bool 原样 |
| 单选/多选 | 选项 dict 或名字串 → 名字；多选 → list[str] |
| 公式 / lookup | 按结果 `data_type`(int) 分派（不用 ui_type——设过格式后可能缺失）：文本/数字/日期/单选多选同上；公式 select 返回**选项 ID**，用表级 optId→name 映射反查；容忍 `{type,value}` 包装与裸值两种形态 |

**不支持**（值结构复杂、语义层用不到）：人员、创建人/修改人、附件、地理位置、群组、创建/修改时间、单向/双向关联 → 值写成 `（X字段，暂不支持取值）` 提示文本，不做清洗。兜底：未识别类型若返回结构化 dict/片段数组也拍平成可读串，避免写坏 Neo4j（Map 类型错）。

## 索引与约束契约

- 向量索引：`<label>_embedding_index`，索引 `n.embedding`，cosine，维度取 `graph-config.embedding.dimensions`（默认 512）。
- 全文索引：`<label>_search_text_index`，索引 `n.search_text`，analyzer 固定 `cjk`。
- `search_text` 由节点全部业务属性拼成 `字段名：值。` 串（跳过检索内部属性）；`vector_index=false` 的实体不参与检索、不建索引。
- 唯一约束：每实体 `sda_<label>_<key_field>_unique`，使 `key_field` 成为稳定标识。
- 查询侧不猜索引名：通过 `SHOW VECTOR INDEXES` / `SHOW FULLTEXT INDEXES` 按 label 实时发现并缓存。

## embedding 审计字段

每个向量节点写入：`embedding_model`（模型名）、`embedding_dimensions`（维度）、`embedding_updated_at`（UTC 时间戳）。写入与查询共用同一 Fastembed(ONNX) 实例，天然同源。**换模型或维度必须重跑 sync 全量重算**，并在测试图先 `dry_run` 通过再执行；确认所有索引 `ONLINE`。

## 运维备忘

- 首次部署后 Neo4j 为空，必须跑一次 `sync` 才能检索。
- 改飞书多维表结构（加字段/改类型）→ 跑一次 `sync`。
- 服务器上 sync 属长任务，建议重建容器清掉进程内模型缓存后再跑（详见 `mcp/README.md` §6）。
