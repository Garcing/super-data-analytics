# querying-via-sql

从 Hologres（PostgreSQL 兼容）数据库查询数据。SQL 通过 `--query` 传入（直接写语句 / `@文件` / 管道 stdin）；查询结果始终保存，并以统一 JSON 信封输出到 stdout。

## 环境要求

- Node.js 18+
- 凭证（舰队共享一份）：统一放 `~/.super-data-analytics/config.json` 的 `env` 块（`HOLOGRES_HOST`/`HOLOGRES_PORT`/`HOLOGRES_DATABASE`/`HOLOGRES_USER`/`HOLOGRES_PASSWORD`），**唯一来源**；config.json 缺失或字段不全时，脚本报错并指引，由 agent 引导补全后写回
- `.xlsx` 导出需要可选依赖 `xlsx`

## CLI

```bash
# 测试连接
node scripts/sql-query.js test-connection

# 获取表结构
node scripts/sql-query.js schema dw_study.table1 dw_study.table2

# 三种查询写法（--query 是唯一入口）
node scripts/sql-query.js query --query "SELECT 1 AS test"                   # 直接写 SQL
node scripts/sql-query.js query --query @.super-data-analytics/scratch/q.sql  # @ + 文件路径
node scripts/sql-query.js query --query - <<'EOF'                            # 管道 stdin（heredoc；也支持父进程 spawn）
SELECT 1 AS test;
EOF
```

查询参数：

| 参数 | 说明 |
|---|---|
| `--query <sql\|@path\|->` | 可选；直接写 SQL（≤500 字符单行纯 ASCII，含中文/引号/`$`/反引号/反斜杠会被拒），或 `@` + 文件路径，或 `-` 表示显式从管道 stdin 读；不传也等同 stdin |
| `--save <path>` | 可选；结果保存地址，支持 `.json`、`.csv`、`.xlsx`；不传则落 `cwd/result-<trace_id>.json`（`trace_id` 内部自动生成） |

旧参数 `--file`、`--stdin`、`--source`、`--sql`、`--sql-path`、`--work-dir`、`--retain-sql`、`--trace-id` 已全部删除，统一为 `--query`。

## 结果

结果地址由 `--save` 指定（不传则落当前工作目录 `result-<trace_id>.json`）。`.super-data-analytics/{results,scratch}` 的布局约定见 SKILL.md，由调用方/agent 构造路径传入，JS 不内置目录结构、不自动清理 SQL。

stdout 同时输出完整执行信封：

```json
{
  "trace_id": "...",
  "source": "file",
  "result_path": "...",
  "row_count": 10,
  "columns": [],
  "rows": []
}
```

`.json` 保存完整信封；`.csv` 和 `.xlsx` 只保存表格数据。进度和错误写入 stderr。

## 文件生命周期

- SQL 文件不会被自动删除；scratch（如 `.super-data-analytics/scratch/`）的清理归调用方/agent。
- `KEEP_SQL_FILE` 和 `KEEP_SQL_RESULT` 已删除。

## 安全传输

优先由父进程直接写 stdin（不传 `--query`，从管道读）：

```javascript
const child = spawn('node', ['scripts/sql-query.js', 'query'], {
  stdio: ['pipe', 'pipe', 'pipe'],
});
child.stdin.end(sql, 'utf8');
```

只有 Shell 能力时，优先写文件后用 `--query @<文件>`。Bash 下可使用带引号的 heredoc 直接管道。不要把含变量、引号或反引号的 SQL 直接写进 `--query "<...>"`（shell 会展开）。

## 测试

```bash
node cache/test-routing-matrix.js
```
