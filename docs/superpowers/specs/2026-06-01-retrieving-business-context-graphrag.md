# retrieving-business-context GraphRAG Skill 设计

> 日期: 2026-06-01
> 状态: 已批准

## 概述

将 `retrieving-business-context/` 构建为一个完整的 GraphRAG agent skill。从飞书多维表格拉取业务知识数据，写入本地 Neo4j 图数据库并生成向量索引，供 agent 通过语义检索 + 图关系扩展获取业务上下文。

## 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 技术栈 | Python 同步 + Node.js 查询 | Python 擅长 embedding，Node.js 符合项目 CLI 模式 |
| 数据刷新 | 手动触发 `python sync.py` | 当前阶段简单稳定 |
| LLM 调用 | 不调 LLM，返回结构化上下文 | 在 agent 框架内运行，agent 自己总结 |
| 配置方式 | YAML 配置驱动 | 改字段/改关系只改配置，不改代码 |
| 飞书外键 | 不依赖 `dynamic_options_source` | YAML 是唯一真相来源，保持飞书配置自由度 |
| embedding 推理 | Python 子进程 | 简单直接，2s 延迟对 agent 可接受 |
| 模型存储 | 完整下载到项目文件夹 | 运行时零网络依赖 |

## 数据源

飞书多维表格 `BHINbLiOKa4rXDsLTlQcRwuSn9c`，包含 9 张表：

| 表名 | table_id | 字段数 | key_field |
|------|----------|--------|-----------|
| 业务线 | tbljp4PEWKQcjQzD | 5 | 业务线名称 |
| 业务板块 | tbl3LKdowDu3KLQm | 4 | 业务板块名称 |
| 业务小点 | tblmwx8jwrZVX49t | 5 | 业务小点名称 |
| 指标 | tblDiMrN7GaGVtpc | 5 | 指标名称 |
| 维度 | tblzgo2FcMG7eSwR | 6 | 维度名称 |
| 数据看板 | tblaOZqdUnySDDMG | 4 | 数据看板名称 |
| 数据域 | tblJY0BfS8LAPTcf | 4 | 数据域名称 |
| 表 | tbl6Ri6dTIwTWGch | 6 | 表名称 |
| 表关系 | tblhMmvHGmEh9MWx | 5 | (中间表，via 引用) |

## 文件结构

```
retrieving-business-context/
├── SKILL.md                     # Agent 技能定义
├── CLAUDE.md                    # 技术参考
├── graph-config.yaml            # 图模型配置（唯一真相来源）
├── .env                         # NEO4J_USER, NEO4J_PASSWORD
├── .gitignore
│
├── sync/                        # Python 同步管线
│   ├── sync.py                  # 主入口：一键同步
│   ├── feishu_reader.py         # lark-cli 读取飞书数据
│   ├── graph_builder.py         # 建节点、建关系
│   ├── embedding.py             # search_text + 向量化
│   ├── models/                  # 本地 embedding 模型
│   │   └── bge-small-zh-v1.5/  # 完整模型文件
│   └── requirements.txt
│
├── server/                      # Node.js 查询服务
│   ├── package.json
│   └── query.js                 # 向量检索 + 图扩展 CLI
│
└── 临时参考代码/                 # 旧参考代码（保留）
```

## graph-config.yaml 设计

### 顶层结构

```yaml
feishu:
  app_token: BHINbLiOKa4rXDsLTlQcRwuSn9c

neo4j:
  uri: bolt://localhost:7687
  database: neo4j
  # user/password 从 .env 读取

embedding:
  model: BAAI/bge-small-zh-v1.5
  model_path: sync/models/bge-small-zh-v1.5
  dimensions: 512
```

### entities 配置

每个实体对应一张飞书表和一个 Neo4j 标签：

```yaml
entities:
  业务线:
    table_id: tbljp4PEWKQcjQzD
    key_field: 业务线名称
    # vector_index: true    # 默认 true

  数据看板:
    table_id: tblaOZqdUnySDDMG
    key_field: 数据看板名称
    vector_index: false     # 不需要语义检索，图关系可达即可
```

**字段说明：**
- `table_id`: 飞书多维表格的表 ID
- `key_field`: 唯一标识字段，用于 Neo4j MERGE 保证幂等
- `vector_index`: 默认 true。false 时跳过 search_text/embedding/向量索引

**search_text 生成规则（全自动）：**
- 代码自动读取每行记录的所有字段
- 拼接为 `"字段名：值。字段名：值。"` 格式
- 自动跳过 `auto_number` 类型字段和 `_record_id`
- 使用 `coalesce(trim(), '')` 处理空值
- 无需手写模板

### relationships 配置

三种匹配模式：

**1. 直接匹配（source 字段值 = target 字段值）：**

```yaml
- type: 包含
  from: 业务线
  to: 业务板块
  match:
    source_field: 业务线名称
    target_field: 业务线名称
```

含义：在飞书「业务板块」表中，找到 `业务线名称` 字段值等于「业务线」实体 `key_field` 值的记录，创建 `(业务线)-[:包含]->(业务板块)` 关系。

**2. 多选匹配（拆分后逐一匹配）：**

```yaml
- type: 涉及
  from: 业务小点
  to: 指标
  match:
    source_field: 指标名称
    target_field: 指标名称
    multi: true
```

含义：`source_field` 是多选字段，值如 `["复购人数", "超V回流率"]`，拆分后每个值分别匹配。

**3. 中间表匹配（via）：**

```yaml
- type: 关联
  from: 表
  to: 表
  via:
    table_id: tblhMmvHGmEh9MWx
    from_field: 从表
    to_field: 到表
    properties:
      - 关联类型
      - 关联表达式
```

含义：读取「表关系」中间表，每行 `从表` 值匹配 `表.key_field`，`到表` 值匹配 `表.key_field`，创建关系时携带 `properties` 中的字段作为关系属性。

## 数据流

### 同步流程（Python）

```
python sync/sync.py

① 读取 graph-config.yaml
② feishu_reader: 调 lark-cli 逐表拉数据
   - lark-cli base +record-list --base-token X --table-id Y --as bot --page-all
   - 返回 List[Dict]，每行一个 dict
③ graph_builder: 遍历 entities，MERGE 节点
   - MERGE (n:`标签` {`key_field`: value}) SET n += 其他属性
④ graph_builder: 遍历 relationships，创建关系
   - match: 找字段值相等的节点对
   - multi: 拆分多选值后逐一匹配
   - via: 读中间表，按 from_field/to_field 匹配
⑤ embedding: 对 vector_index=true 的实体
   - 自动拼接 search_text
   - 加载本地模型，生成 embedding，写回节点
   - CREATE VECTOR INDEX IF NOT EXISTS
⑥ 打印统计信息
```

### 查询流程（Node.js）

```
node server/query.js "复购人数下降了怎么看？" --top-k 5

① 调 Python 子进程做向量化
   - python sync/embedding.py encode "复购人数下降了怎么看？"
   - 返回 512 维向量 JSON
② 直连 Neo4j，对每个 vector_index=true 的索引做向量检索
   - 使用 Neo4j SEARCH Cypher 子句
③ 直连 Neo4j，对每个命中节点做图关系扩展
   - 根据 config relationships 自动生成 OPTIONAL MATCH
④ 输出 JSON
```

### CLI 接口

**sync.py:**
```bash
python sync/sync.py                    # 全流程
python sync/sync.py --only fetch       # 只拉飞书数据
python sync/sync.py --only graph       # 只建图
python sync/sync.py --only embed       # 只重建向量
python sync/sync.py --dry-run          # 预览不写入
python sync/sync.py --force-embed      # 强制重新生成 embedding
python sync/sync.py --download-model   # 下载模型到本地
```

**query.js:**
```bash
node server/query.js "<问题>"                    # 基本查询
node server/query.js "<问题>" --top-k 5          # 限制返回数量
node server/query.js "<问题>" --targets 表,指标   # 只查部分索引
```

### query.js 输出格式

```json
{
  "question": "复购人数下降了怎么看？",
  "results": [
    {
      "label": "指标",
      "score": 0.89,
      "properties": {
        "指标名称": "复购人数",
        "指标定义": "...",
        "数据看板名称": "超级VIP项目看板"
      },
      "context": {
        "业务板块": [
          { "业务板块名称": "超级VIP运营", "业务板块介绍": "..." }
        ],
        "数据看板": [
          { "数据看板名称": "超级VIP项目看板", "语义模型ID": "xxx" }
        ]
      }
    }
  ]
}
```

## 图关系扩展策略

扩展查询根据 `graph-config.yaml` 的 relationships 自动生成，不硬编码：

```
对每个命中节点 (label, key_field, key_field_value):
  遍历 relationships:
    如果 rel.from == label:
      MATCH (source:`label` {`key_field`: value}) -[:`rel.type`]-> (target)
      RETURN target.key_field + 展示字段
    如果 rel.to == label:
      MATCH (source) -[:`rel.type`]-> (target:`label` {`key_field`: value})
      RETURN source.key_field + 展示字段
```

加新关系只需改 YAML，扩展查询自动生效。

## 依赖

**Python (sync/requirements.txt):**
- `neo4j` — Neo4j Python Driver
- `sentence-transformers` — 加载 bge-small-zh-v1.5
- `pyyaml` — 读取 graph-config.yaml

**Node.js (server/package.json):**
- `neo4j-driver` — Neo4j JavaScript Driver
- 无其他依赖

**系统依赖:**
- `lark-cli` — 已安装，用于读取飞书数据
- Neo4j — 本地运行，bolt://localhost:7687
