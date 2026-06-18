---
name: querying-via-sql
description: 从 Hologres/PostgreSQL 数据库查询数据，文件驱动 SQL 执行，支持结果导出
metadata: 
  skill-series: super-data-analytics
  chinese-name: 查询数据通过SQL
---

# 查询数据通过SQL

从 Hologres (PostgreSQL) 数据库查询数据，使用 pg 驱动直连

## 触发条件

- 用户需要从数据库查询数据
- 其他 skill 需要数据库数据时引用
- 用户使用 `/querying-via-sql` 命令

## 环境要求

- Node.js 18+
- 数据库凭证（`.env` 文件或环境变量）：`HOLOGRES_HOST`、`HOLOGRES_PORT`、`HOLOGRES_DATABASE`、`HOLOGRES_USER`、`HOLOGRES_PASSWORD`

## CLI 命令

```bash
# 测试连接
node scripts/sql-query.js test-connection

# 获取表结构（支持多表）
node scripts/sql-query.js schema <schema.table> [schema.table ...]

# 执行 SQL 文件
node scripts/sql-query.js query --file <file_path> [--keep] [--save <output>]
```

## 核心流程

### Phase0：意图识别

当用户已提供完整SQL代码，跳过Phase1，从Phase2写入SQL文件开始，并执行返回结果即可

### Phase1：获取表结构

调用方必须提前提供要使用的表名（本 SKILL 不负责选择表）

```bash
# 单表
node scripts/sql-query.js schema <schema.table>
# 多表
node scripts/sql-query.js schema <schema.table1> <schema.table2> <schema.table3>
```

返回字段信息：序号、字段名、数据类型、默认值、是否允许为空、是否为主键、字段注释。

### Phase2：生成 SQL

根据表结构 + 用户需求生成 SQL，写入 `cache/` 目录，文件名格式：

生成SQL风格请参考 [`templates/style.sql`](templates/style.sql)

```text
sql-query-YYYYMMDD-HHMMSS-<random>.sql
```

其中 `YYYYMMDD-HHMMSS` 使用当前时间，`<random>` 使用至少 10 位随机字母数字，如 `cache/sql-query-20260510-143522-a7f3c98f4k.json`，不要和已有的文件命名冲突。

### Phase3：执行查询

```bash
node scripts/sql-query.js query --file cache/<Step2生成的文件.sql>
```

默认行为：查询结果以 JSON 输出到 stdout，SQL 文件执行后自动删除。

**保存结果**：

```bash
# 保存为 CSV
node scripts/sql-query.js query --file cache/xxx.sql --save <Phase2文件命名>.csv

# 保存为 Excel（需要 npm install xlsx）
node scripts/sql-query.js query --file cache/xxx.sql --save <Phase2文件命名>.xlsx

# 保存为 JSON
node scripts/sql-query.js query --file cache/xxx.sql --save <Phase2文件命名>.json
```

**调试时保留 SQL 文件**：

```bash
node scripts/sql-query.js query --file cache/xxx.sql --keep
```

