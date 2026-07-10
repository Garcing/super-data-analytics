# SQL 源用法（Hologres / PostgreSQL）

通过 `node scripts/query.js sql ...` 直连 Hologres/PostgreSQL 查询返回数据。凭证统一来自 `~/.super-data-analytics/config.json` 的 `env` 块（`HOLOGRES_*`），不读 `.env`、不依赖环境变量导出。

所有命令在 `querying-data/` 目录下执行，前缀为 `node scripts/query.js`。

## CLI 命令

```bash
# 1) 测试数据库连接
node scripts/query.js sql test-connection

# 2) 获取数据表 schema（调用方必须提前提供表名，本脚本不负责选表）
node scripts/query.js sql schema <schema.table> [schema.table ...]

# 3) 查询数据：--sql 三种来源（inline / @file / stdin）
node scripts/query.js sql query --sql "<SQL>"              # inline
node scripts/query.js sql query --sql @<file-path>         # 文件
node scripts/query.js sql query --sql -                    # stdin（管道）

# 追加 --output <file-path> 可落盘结果（仅当用户明确要求时）；支持 .json / .csv / .xlsx
node scripts/query.js sql query --sql @./dau.sql --output ./.super-data-analytics/results/sql-result-20260626-103000-dau.json
```

> 子命令清单：`test-connection` / `schema` / `query`。SQL 源没有 `list-tools`。

## `--sql` 三来源路由

`--sql` 是 SQL 正文入口，按值的形式自动判定来源：

| 取值 | 来源 | 说明 |
|---|---|---|
| 不传 或 `-` | stdin | 从管道读取；`-` 是 Unix 惯用的"显式 stdin" |
| `@<path>` | file | 从文件读取 SQL |
| 其他 | inline | 直接 SQL 字符串 |

### 按环境选择写法

| 环境条件 | 写法 | 执行方式 |
|---|---|---|
| Agent 支持进程 API | 管道 stdin | 调用方进程在内存直接 `spawn` 子进程，向子进程 stdin 写 UTF-8 SQL；不要为了用 `spawn` 把 SQL 或 driver JS 落盘 |
| bash/zsh | 管道 stdin | quoted heredoc `<<'EOF'`（引号抑制 `$` 或反引号展开） |
| PowerShell | 管道 stdin | 统一显式设置 `$OutputEncoding` 为 UTF-8 without BOM；单引号 here-string `@'...'@`；`$sql` 管道到 `node ... --sql -` |
| SQL 需要审阅、复跑或留痕；或管道 stdin 写法报错 | @文件 | agent 把 SQL 写入 `<工作区>/.super-data-analytics/scratch/`，经 `--sql @` 传入 |
| 简短 SQL | 直接 SQL | SQL 直接写入命令行；含 `$` 或反引号时不建议 inline，复杂 SQL 走 file/stdin 更稳 |

**注意事项**

- 含 `$` 或反引号的 SQL 不建议用 inline：双引号外层下 shell 会展开 `$abc`、执行反引号，可能拿到静默错误结果。
- 原则上尽量不写临时 SQL 文件，管道 stdin 优先。

### 参考示例

**Agent 进程 API（spawn + stdin）**——不要为了用 spawn 额外生成临时 driver JS：

```javascript
const child = spawn('node', ['scripts/query.js', 'sql', 'query', '--sql', '-'], {
  cwd: 'querying-data',
  stdio: ['pipe', 'pipe', 'pipe'],
});
child.stdin.end(sql, 'utf8');
```

**bash/zsh quoted heredoc（不落盘、不展开，UTF-8 干净）：**

```bash
node scripts/query.js sql query --sql - <<'EOF'
SELECT 'a$b`c 中文' AS s;
EOF
```

**PowerShell 单引号 here-string + 显式 UTF-8：**

```powershell
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom

$sql = @'
SELECT '$abc' AS d, '中文 🚀' AS u;
'@

$sql | node scripts\query.js sql query --sql -
```

## 输出（stdout envelope）

`query` 子命令向 stdout 输出一个 JSON envelope：

```json
{
  "source": "sql",
  "row_count": 12,
  "columns": [{"name": "uid", "dataTypeID": 25}, ...],
  "rows": [{"uid": "...", ...}, ...],
  "result_path": "/abs/path/to/sql-result-....json"
}
```

字段说明：

- `source` —— 固定为字面量 `"sql"`（数据源名，不是查询输入来源）。
- `row_count` —— 行数。
- `columns` —— 列元信息（`name` + `dataTypeID`）。
- `rows` —— 行数据数组。
- `result_path` —— 仅当传入 `--output` 时出现，指向落盘文件的绝对路径。

## `--output`（可选落盘）

- 默认不保存；仅当用户明确要求时才传 `--output <file-path>`。
- 支持扩展名：`.json` / `.csv` / `.xlsx`（xlsx 需要 `npm install xlsx`）。
- 落盘目录由 agent 决定，建议 `<工作区>/.super-data-analytics/results/`。
- 命名建议：`sql-result-YYYYMMDD-HHMMSS-<主题>.<ext>`（agent 按需命名，不是硬规则）。
- 落盘成功时脚本在 **stderr** 打印 `结果已保存到: <path>`，envelope 仍正常输出到 stdout。

## schema

```bash
node scripts/query.js sql schema dwd.dwd_user dim.dim_date
```

调用方负责提供 `schema.table` 列表，脚本按顺序返回每张表的列定义：

```json
[
  {"schema": "dwd", "table": "dwd_user", "columns": [{"column_name": "uid", "data_type": "text", ...}]},
  {"schema": "dim", "table": "dim_date", "columns": [...]}
]
```
