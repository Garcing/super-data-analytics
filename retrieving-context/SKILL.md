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
- 数据已同步（运行过 `python scripts/pipeline/sync.py`）
- 凭证/配置统一在 `~/.super-data-analytics/config.json`：
  - `env` 块：`NEO4J_URI` / `NEO4J_DATABASE` / `NEO4J_USER` / `NEO4J_PASSWORD` / `FEISHU_GRAPH_BITABLE_APP_TOKEN`
  - `graph-config` 块：`embedding`（model + dimensions）、`entities`、`relationships`

> **需要理解这套图配置的字段语义、或要维护（新增实体/关系、换 embedding 模型、排查边没建上）时**，读 [`references/neo4j-config.md`](references/neo4j-config.md)。那里讲清了 `entities`/`relationships`（含 `match` vs `via` 两种建边机制）、建图与扩图的职责分工、以及维护指南。

## 运行环境与依赖

- Node.js `>=20.0.0`；在 `retrieving-context/scripts/` 执行 `npm ci`（`neo4j-driver`）。
- Python `>=3.10`；对 PATH 上的 `python` 执行 `python -m pip install -r scripts/pipeline/requirements.txt`（依赖：`neo4j`、`sentence-transformers`）。
- 同步飞书数据还要求可执行的 `lark-cli` 及已完成授权。
- 可选进程变量 `QUERY_STDIN_TIMEOUT_MS` 只调整查询 stdin 超时；embedding 模型由 `graph-config.embedding` 配置，首次使用会下载模型文件。

完整安装矩阵见仓库根目录 `DEPENDENCIES.MD`。


## CLI 命令

**先了解图结构**（写 Cypher 或选 targets 前先跑）：
```bash
node scripts/retrieve.js schema
```
打印所有实体（label / key_field / vector_index）和关系（type / from→to / match 字段），不连库。

**语义检索模式**（问"是什么"、"去哪找"）：
```bash
node scripts/retrieve.js search --question "用户问题" [--top-k 5] [--targets 表,指标]
```

**Cypher 查询模式**（问"有几个"、"有哪些"、"属于XX的"）：
```bash
node scripts/retrieve.js cypher --statement "MATCH (n:\`表\`) RETURN count(n) AS 数量"
```

**飞书文档读取模式**（已知 Docx URL 或 token，读取最新完整正文）：
```bash
node scripts/retrieve.js doc --doc "https://my.feishu.cn/docx/xxx"
```

该命令使用飞书用户身份读取文档，以 Markdown 返回 `document_id`、`revision_id` 和 `content`。它不连接 Neo4j，也不解析或改写正文。

`--question` / `--statement` 都支持三态输入：
- `--statement "<CYPHER>"` inline
- `--statement @<file>` 从文件读（避免中文反引号标签的 shell 转义地狱）
- `--statement -` 或不传值 → stdin（管道）

参数：
- `search --question`：语义检索正文，支持 inline / `@file` / stdin 三态；不传 `--question` 时走 stdin
- `cypher --statement`：Cypher 查询正文，支持 inline / `@file` / stdin 三态；不传 `--statement` 时走 stdin
- `doc --doc "<URL或token>"`：读取飞书 Docx 最新完整正文；`--doc` 可接 URL 或 token
- `--top-k N`：每个向量索引返回的最大结果数，默认 5（仅语义检索）
- `--targets 逗号分隔的实体名`：限制搜索范围。可用值：业务线,业务板块,业务小点,数据看板,指标,维度,表,表关系（仅语义检索）
- `schema`：打印实体 + 关系后退出，不连库

## 核心流程

### 第一步：选择查询模式

- **语义检索**（"X是什么意思"、"去哪找X"）→ `node scripts/retrieve.js search --question "问题"`
- **结构化查询**（"有几个X"、"X下面有哪些Y"、"列出所有X"）→ `node scripts/retrieve.js cypher --statement "MATCH ..."`

### 第二步：语义检索模式 — 智能路由 targets

执行语义检索前，先跑 `node scripts/retrieve.js schema` 了解有哪些实体，判断问题可能涉及哪些，用 `--targets` 缩小范围。

**8 个可检索实体**：业务线、业务板块、业务小点、数据看板、指标、维度、表、表关系

**路由原则：宁可多搜不要漏搜。只要有 1% 的可能性涉及某个实体，就加上。**

常见路由参考（不是硬编码，根据问题灵活组合）：

| 问题倾向 | 推荐 targets | 理由 |
|---------|-------------|------|
| 问指标/度量 | 指标,表,表关系,维度 | 指标关联计算表、Join 链和常用维度 |
| 问数据表 | 表,维度,表关系 | 表关联来源维度和 Join 链 |
| 问业务架构 | 业务线,业务板块,业务小点 | 三级层级 |
| 问看板/报表 | 数据看板,指标 | 看板和指标都可能直接命中 |
| 不确定 | 所有实体（不加 --targets） | 全搜最安全 |

**示例**：
- "复购人数是什么" → `--targets 指标,表,表关系,维度`
- "听课明细去哪张表看" → `--targets 表,维度,表关系`
- "前端增长投放的业务结构" → `--targets 业务线,业务板块,业务小点`

### 维度检索

用户问题出现分组、筛选、对比或枚举取值时，不只检索指标的“常用维度”。还要用用户原词及可能的取值检索 `维度`，并用 Cypher 取得候选的完整契约：

- 维度 ID、维度名称、维度组
- 来源字段、来源表
- 维度组关联键、维度组主键维度
- 取值特征
- `来源于` 的表节点及其表别名、表类型

先检查指标参与计算表是否已输出语义一致的维度字段；一致则标记为直接使用。不存在或含义不确定时，依据事实表可用关联键选择可接入的维度来源表。名称相似或枚举值部分重合不能单独证明是同一维度；若多个候选仍会产生不同结果，返回候选差异供上游追问，不替上游猜测。

### 第三步：Cypher 模式

根据 `schema` 输出（即 config.json 的 `graph-config` 块）中的实体和关系构造 Cypher：
- 实体标签：业务线、业务板块、业务小点、数据看板、指标、维度、表、表关系
- 关系类型：包含、使用、启用、常用维度、来源于、起始于、加入、基于
- 节点属性参考 graph-config.yaml 中每个实体的 key_field

### 第四步：解读结果，格式化回答

- 引用具体的指标定义、表名、业务板块名称
- 说明层级关系（业务线 → 业务板块 → 业务小点）或指标计算链（指标 → 表 / 表关系 / 维度）
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

- **指标类问题**：给出指标定义、计算说明、参与计算表、使用表关系、默认时间字段和常用维度组
- **数据表问题**：给出中文表名、表名、别名、类型、粒度、来源维度和相关 Join 步骤
- **表关系问题**：按前置关系递归展开，依次说明起始表、加入表、JOIN 类型、JOIN 条件和关联基数
- **业务层级问题**：给出完整的 业务线→业务板块→业务小点 链路
- **维度问题**：给出维度 ID、名称、维度组、取值特征、来源字段、来源表、维度组关联键和维度组主键维度；同时说明参与计算表可直接使用该字段，还是需要通过关联键引入来源表

## 数据同步（维护时使用）

直接用 Python CLI 运行 `scripts/pipeline/sync.py`。前提是 PATH 上的 `python` 已按上方"运行环境与依赖"装好 requirements.txt。配置（飞书 token / Neo4j 凭证 / 实体 / 关系）全部来自 config.json，sync.py 自己读取，不依赖任何 Node 包装。

> 改动 `graph-config`（加实体/关系、换 embedding 模型）前，先读 [`references/neo4j-config.md`](references/neo4j-config.md) 的"维护指南"，确认字段语义和重建步骤。

### `python scripts/pipeline/sync.py`（无参数）— 全流程重建

从零重建整个图数据库，按顺序执行三个阶段：
1. **拉飞书数据**：8 张表全拉下来
2. **构建 Neo4j 图**：清空旧数据 → 建节点 → 建关系
3. **向量化**：拼 search_text → 建向量索引 → 生成 embedding

**使用场景**：飞书表结构有变化（加了新字段、新表、新关系），或想彻底重建。

### `python scripts/pipeline/sync.py --only graph` — 只建图

拉数据 + 建节点和关系，**不重建向量索引**。

**使用场景**：飞书数据有增删改（比如新增了几个指标），但不需要重新生成 embedding。

### `python scripts/pipeline/sync.py --only embed` — 只重建向量

跳过拉数据和建图，在现有图上重新生成 search_text 和 embedding。已有 embedding 的节点默认跳过。

**使用场景**：图结构没变，只想重建向量（比如换了 embedding 模型、调整了 search_text 逻辑）。

### `python scripts/pipeline/sync.py --force-embed` — 强制重建所有 embedding

全流程执行，且即使节点已有 embedding 也全部重新生成。

**使用场景**：换了 embedding 模型，或需要全量重算。

### `python scripts/pipeline/sync.py --dry-run` — 预览模式

只拉飞书数据并打印统计（每张表多少条记录、多少字段），**不写入 Neo4j**。

**使用场景**：验证飞书数据是否正常，确认数据量。

### `python scripts/pipeline/sync.py --download-model` — 下载模型

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
