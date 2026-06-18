# retrieving-business-context 技术参考

## 架构

```
graph-config.yaml        # 唯一真相来源
sync/                    # Python 同步管线
  sync.py                # 主入口
  feishu_reader.py       # lark-cli → 飞书数据
  graph_builder.py       # Neo4j 建图
  embedding.py           # search_text + 向量化
  models/                # 本地 embedding 模型
server/
  query.js               # Node.js 查询 CLI
```

## 配置文件

- `graph-config.yaml`：实体定义、关系映射、向量开关。改字段/改关系只改这里
- `.env`：NEO4J_USER, NEO4J_PASSWORD, PYTHON_PATH

## Python 解释器

某些 agent（如 Claude Code）自带 Python 解释器，缺少 neo4j/sentence-transformers 等库。
所有 Python 调用都通过 Node.js 壳脚本中转，agent 只需执行 `node` 命令：

- `node server/sync.js [args]` → 内部用 PYTHON_PATH 执行 sync.py
- `node server/query.js "问题"` → 内部用 PYTHON_PATH 执行 embedding.py encode

Python 解释器路径在 `.env` 的 `PYTHON_PATH` 中配置，未配置则回退到系统 PATH 中的 `python`。

## 关键实现细节

### feishu_reader.py
- 调用 `lark-cli base +field-list` 和 `+record-list`
- 使用 `subprocess.run(cmd, shell=True)` (Windows)
- 自动过滤 auto_number 字段
- lark-cli 返回列式数据，代码自动转行式

### graph_builder.py
- 节点用 `MERGE` 保证幂等
- 三种关系匹配模式：direct / multi / via
- 关系通过 `key_field` 值匹配
- via 中间表支持关系属性

### embedding.py
- search_text 自动拼接：`字段名：值。`
- 模型加载自本地路径 `sync/models/bge-small-zh-v1.5`
- `encode` 子命令供 Node.js 调用

### query.js
- ESM 模块，neo4j-driver 直连
- 调 Python 子进程做向量化
- 使用 `db.index.vector.queryNodes()` 查询向量
- 图关系扩展根据 config 自动生成
- JSON 输出到 stdout，日志到 stderr

## Neo4j 向量索引

- 索引命名：`{实体标签}_embedding_index`
- cosine similarity，512 维

## Embedding 模型

- BAAI/bge-small-zh-v1.5，512 维
- 本地存储 `sync/models/bge-small-zh-v1.5/`
- 不提交 git
