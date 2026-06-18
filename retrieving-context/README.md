# retrieving-business-context

GraphRAG 业务知识检索。从飞书多维表格同步业务知识到本地 Neo4j 图数据库，通过向量语义检索 + 图关系扩展回答业务问题。

## 架构

```
graph-config.yaml              唯一真相来源：实体、关系、向量配置
         │
         └── scripts/
                 │
                 Node.js 层
                   sync.js                 壳：调用 pipeline/sync.py（自动读 .env 的 PYTHON_PATH）
                   query.js                查询 CLI
                   env.js                  共享：.env 读取 + Python 解释器解析
                       │
                       ↓
                 pipeline/ (Python 层)
                   sync.py                 一键编排全流程
                   feishu_reader.py        调 lark-cli 拉飞书数据
                   graph_builder.py        按配置 MERGE 节点 + 建关系
                   embedding.py            search_text 拼接 + 向量化
                       │
                       ↓
                 JSON 输出给 Agent → Agent 基于上下文生成回答
```

**数据流**：飞书多维表格 → Python 同步到 Neo4j → Node.js 查询返回 JSON → Agent 总结回答

**两种查询模式**：

| 模式 | 适用场景 | 命令 |
|------|---------|------|
| 语义检索 | "X 是什么意思"、"去哪找 X" | `node scripts/query.js "问题"` |
| Cypher 查询 | "有几个 X"、"X 下面有哪些 Y" | `node scripts/query.js --cypher "MATCH ..."` |

## 图模型

数据来源：飞书多维表格 `BHINbLiOKa4rXDsLTlQcRwuSn9c`，共 9 张表。

```
业务线 ──包含──→ 业务板块 ──包含──→ 业务小点 ──涉及──→ 指标
                                              ↑
数据看板 ──展示───────────────────────────────→ 指标
维度 ──筛选──────────────────────────────────→ 指标
数据域 ──包含──→ 表 ──关联──→ 表
```

8 个实体类型（6 个建向量索引，2 个仅图关系可达），7 种关系类型。

## 运行流程

### 1. 初始化

```bash
# 下载 embedding 模型到本地（首次）
node scripts/sync.js --download-model
```

### 2. 同步数据（飞书有变动时执行）

```bash
# 全流程重建（拉飞书 → 建图 → 向量化）
node scripts/sync.js

# 其他场景
node scripts/sync.js --only graph       # 只建图，不重建向量
node scripts/sync.js --only embed       # 只重建向量，不动图
node scripts/sync.js --dry-run          # 预览飞书数据量，不写入
```

### 3. 查询（Agent 调用）

```bash
# 语义检索
node scripts/query.js "复购人数是什么意思？" --top-k 5
node scripts/query.js "去哪张表查听课明细？" --targets 表,维度,数据域

#结构化查询
node scripts/query.js --cypher "MATCH (n:\`表\`) RETURN count(n) AS 表数量"
node scripts/query.js --cypher "MATCH (d:\`数据域\`)-[:包含]->(t:\`表\`) WHERE d.\`数据域名称\` = 'dw_ops' RETURN t.\`表名称\`, t.\`表中文名称\`"
```

## 配置

### graph-config.yaml（唯一真相来源）

定义实体（哪张飞书表 → 哪个 Neo4j 标签）、关系（字段匹配规则）、向量开关。改字段/改关系只改这里，不改代码。

### .env

```
NEO4J_USER=neo4j
NEO4J_PASSWORD=xxx
PYTHON_PATH=D:\APP\python3.12.1\python.exe
```

`PYTHON_PATH` 解决 agent 自带 Python 缺少依赖的问题。所有 Python 调用都通过 Node.js 壳脚本中转，agent 只需执行 `node` 命令。

## 关键设计

- **多选字段自动展开**：飞书多选字段（list）在建关系前自动展开为多行，统一走单值匹配逻辑，YAML 无需手动标记 `multi`
- **节点属性保持完整**：展开只在 Python 内存中发生，不影响 Neo4j 节点属性（多选字段仍然存为 list）
- **MERGE 幂等**：所有节点和关系都用 MERGE 创建，重复执行不会产生重复数据
- **search_text 自动拼接**：所有属性自动拼接为 `字段名：值。` 格式，不需要手写模板
