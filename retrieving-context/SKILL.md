---
name: retrieving-context
description: 检索业务知识图谱，回答业务概念、指标定义、数据来源、业务关系等问题。触发词：业务上下文、指标含义、哪张表、数据来源、业务板块
metadata: 
  skill-series: super-data-analytics
  chinese-name: 检索业务知识
---

# 业务知识检索

通过本地 Neo4j 图数据库 + 向量语义检索，获取业务上下文。

## 触发条件

- 用户问业务概念："复购人数是什么意思？"
- 用户问数据来源："去哪张表查用户听课明细？"
- 用户问业务关系："前端增长投放包含哪些业务小点？"
- 用户问数据看板："哪个看板能看这个指标？"
- 其他 skill 需要业务上下文时引用

## 前置条件

- Neo4j 本地运行（`bolt://localhost:7687`）
- 数据已同步（运行过 `node scripts/sync.js`）
- 凭证/配置统一在 `~/.super-data-analytics/config.json`：
  - `env` 块：`NEO4J_URI` / `NEO4J_DATABASE` / `NEO4J_USER` / `NEO4J_PASSWORD` / `FEISHU_GRAPH_BITABLE_APP_TOKEN` / `PYTHON_PATH`
  - `graph-config` 块：`embedding`（model + dimensions）、`entities`、`relationships`

## CLI 命令

**先了解图结构**（写 Cypher 或选 targets 前先跑）：
```bash
node scripts/query.js --schema
```
打印所有实体（label / key_field / vector_index）和关系（type / from→to / match 字段），不连库。

**语义检索模式**（问"是什么"、"去哪找"）：
```bash
node scripts/query.js --question "用户问题" [--top-k 5] [--targets 表,指标]
```

**Cypher 查询模式**（问"有几个"、"有哪些"、"属于XX的"）：
```bash
node scripts/query.js --cypher "MATCH (n:\`表\`) RETURN count(n) AS 数量"
```

`--question` / `--cypher` 都支持三态输入：
- `--cypher "<CYPHER>"` inline
- `--cypher @<file>` 从文件读（避免中文反引号标签的 shell 转义地狱）
- `--cypher -` 或不传值 → stdin（管道）

参数：
- `--question` / `--cypher`：二选一。各支持 inline / `@file` / stdin 三态
- `--top-k N`：每个向量索引返回的最大结果数，默认 5（仅语义检索）
- `--targets 逗号分隔的实体名`：限制搜索范围。可用值：业务线,业务板块,业务小点,指标,维度,表（仅语义检索）
- `--schema`：打印实体 + 关系后退出，不连库

## 核心流程

### 第一步：选择查询模式

- **语义检索**（"X是什么意思"、"去哪找X"）→ `node scripts/query.js --question "问题"`
- **结构化查询**（"有几个X"、"X下面有哪些Y"、"列出所有X"）→ `node scripts/query.js --cypher "MATCH ..."`

### 第二步：语义检索模式 — 智能路由 targets

执行语义检索前，先跑 `node scripts/query.js --schema` 了解有哪些实体，判断问题可能涉及哪些，用 `--targets` 缩小范围。

**8 个可检索实体**：业务线、业务板块、业务小点、指标、维度、数据看板、数据域、表

**路由原则：宁可多搜不要漏搜。只要有 1% 的可能性涉及某个实体，就加上。**

常见路由参考（不是硬编码，根据问题灵活组合）：

| 问题倾向 | 推荐 targets | 理由 |
|---------|-------------|------|
| 问指标/度量 | 指标,业务小点,业务板块 | 指标可能归属业务小点或板块 |
| 问数据表 | 表,维度,数据域 | 表关联维度和数据域 |
| 问业务架构 | 业务线,业务板块,业务小点 | 三级层级 |
| 问看板/报表 | 指标,数据看板 | 看板展示指标 |
| 不确定 | 所有实体（不加 --targets） | 全搜最安全 |

**示例**：
- "复购人数是什么" → `--targets 指标,业务小点,业务板块`
- "听课明细去哪张表看" → `--targets 表,维度,数据域`
- "前端增长投放的业务结构" → `--targets 业务线,业务板块,业务小点,指标`

### 第三步：Cypher 模式

根据 `--schema` 输出（即 config.json 的 `graph-config` 块）中的实体和关系构造 Cypher：
- 实体标签：业务线、业务板块、业务小点、指标、维度、数据看板、数据域、表
- 关系类型：包含、涉及、展示、筛选、关联
- 节点属性参考 graph-config.yaml 中每个实体的 key_field

### 第四步：解读结果，格式化回答

- 引用具体的指标定义、表名、业务板块名称
- 说明层级关系（业务线 → 业务板块 → 业务小点 → 指标）
- 如果语义检索结果不充分（score < 0.5），换关键词或改用 Cypher 查询

## 输出格式

查询返回 JSON：
```json
{
  "question": "用户问题",
  "results": [
    {
      "label": "实体标签",
      "score": 0.89,
      "properties": { "字段名": "值" },
      "context": { "关联实体标签": [{ "字段名": "值" }] }
    }
  ]
}
```

## 回答指引

- **指标类问题**：给出指标定义、所属业务板块、在哪个数据看板可以看
- **数据表问题**：给出表中文名、表名全称、所属数据域、上下游关联表
- **业务层级问题**：给出完整的 业务线→业务板块→业务小点 链路
- **维度问题**：给出维度名称、字段名称、级别、来自哪张表

## 数据同步（维护时使用）

Python 解释器路径在 config.json 的 `env.PYTHON_PATH` 中配置，sync.js 自动读取，无需关心 Python 环境。配置（飞书 token / Neo4j 凭证 / 实体 / 关系）全部来自 config.json，不再读 `.env` 或 `graph-config.yaml`。

### `node scripts/sync.js`（无参数）— 全流程重建

从零重建整个图数据库，按顺序执行三个阶段：
1. **拉飞书数据**：9 张表全拉下来
2. **构建 Neo4j 图**：清空旧数据 → 建节点 → 建关系
3. **向量化**：拼 search_text → 建向量索引 → 生成 embedding

**使用场景**：飞书表结构有变化（加了新字段、新表、新关系），或想彻底重建。

### `node scripts/sync.js --only graph` — 只建图

拉数据 + 建节点和关系，**不重建向量索引**。

**使用场景**：飞书数据有增删改（比如新增了几个指标），但不需要重新生成 embedding。

### `node scripts/sync.js --only embed` — 只重建向量

跳过拉数据和建图，在现有图上重新生成 search_text 和 embedding。已有 embedding 的节点默认跳过。

**使用场景**：图结构没变，只想重建向量（比如换了 embedding 模型、调整了 search_text 逻辑）。

### `node scripts/sync.js --force-embed` — 强制重建所有 embedding

全流程执行，且即使节点已有 embedding 也全部重新生成。

**使用场景**：换了 embedding 模型，或需要全量重算。

### `node scripts/sync.js --dry-run` — 预览模式

只拉飞书数据并打印统计（每张表多少条记录、多少字段），**不写入 Neo4j**。

**使用场景**：验证飞书数据是否正常，确认数据量。

### `node scripts/sync.js --download-model` — 下载模型

把 embedding 模型下载到 `scripts/pipeline/models/` 本地目录，后续操作不联网。

**使用场景**：第一次搭建环境，或换了机器。

### 速查表

| 命令 | 改图 | 改向量 | 联网 | 速度 |
|------|:---:|:---:|:---:|:---:|
| 默认 | ✅ 清空重建 | ✅ | 拉飞书 | 慢 |
| `--only graph` | ✅ 清空重建 | ❌ | 拉飞书 | 中 |
| `--only embed` | ❌ | ✅ 增量 | 不联网 | 中 |
| `--force-embed` | ✅ 清空重建 | ✅ 全量重算 | 拉飞书 | 最慢 |
| `--dry-run` | ❌ | ❌ | 拉飞书 | 快 |
| `--download-model` | ❌ | ❌ | 下载 | 慢 |
