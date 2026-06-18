# querying-via-sql

从 Hologres（PostgreSQL 兼容）数据库查询数据，文件驱动 SQL 执行，支持结果导出 csv / json / xlsx。

## 目录结构

```
querying-via-sql/
  .env                  # 数据库连接凭证（不入库）
  .gitignore
  SKILL.md              # AI Agent 技能定义
  README.md
  cache/                # SQL 请求文件，执行后默认自动删除
  references/
    get_table_schema.sql  # 表结构提取 SQL 模板
  templates/
    style.sql             # SQL 编写风格指南
  scripts/
    sql-query.js        # 核心：HologresClient 类 + CLI
    package.json        # 依赖：pg
    node_modules/
```

## 环境要求

- Node.js 18+

## 配置

编辑 `.env`，填入 Hologres 连接信息：

```env
HOLOGRES_HOST=xxx.hologres.aliyuncs.com
HOLOGRES_PORT=80
HOLOGRES_DATABASE=your_db
HOLOGRES_USER=access_id
HOLOGRES_PASSWORD=access_key
```

## 安装

```bash
cd scripts && npm install
```

`node_modules/` 随代码携带，拷贝即用，无需再次安装。

## CLI 命令

### 测试连接

```bash
node scripts/sql-query.js test-connection
```

### 获取表结构

```bash
# 单表
node scripts/sql-query.js schema dw_study.dim_xqd_study_category

# 多表
node scripts/sql-query.js schema dw_study.table1 dw_study.table2
```

参数格式为 `schema.table`，至少传一个。返回每个表的字段信息（名称、类型、主键、注释等）。

### 执行 SQL

```bash
# 基本用法（结果输出到 stdout，SQL 文件执行后自动删除）
node scripts/sql-query.js query --file cache/xxx.sql

# 保留 SQL 文件（调试用）
node scripts/sql-query.js query --file cache/xxx.sql --keep

# 保存结果为文件
node scripts/sql-query.js query --file cache/xxx.sql --save output.csv
node scripts/sql-query.js query --file cache/xxx.sql --save output.json
node scripts/sql-query.js query --file cache/xxx.sql --save output.xlsx  # 需额外安装 xlsx
```

## 典型工作流

1. **获取表结构** → `schema dw_study.some_table` 了解字段
2. **编写 SQL** → 将查询语句写入 `cache/request-YYYYMMDD-HHMMSS-xxx.sql`
3. **执行** → `query --file cache/xxx.sql` 获取结果

## 依赖

| 包 | 用途 | 必需 |
|---|---|---|
| `pg` | PostgreSQL 驱动 | 是 |
| `xlsx` | Excel 导出 | 否（仅 `--save .xlsx` 时动态加载） |
