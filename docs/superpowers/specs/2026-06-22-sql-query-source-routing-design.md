# SQL Query Source Routing Design

## 目标

重构 `querying-via-sql` 的查询入口，让 Agent 在执行前根据 SQL 的复杂度、调用工具能力和留痕需求，显式选择 `stdin`、`file` 或 `inline`。CLI 负责严格校验、统一保存结果和保护源文件，不再通过环境变量控制运行行为。

本次是破坏性升级，不兼容现有 `query --file` 和 `query --stdin` 参数。

## CLI 接口

统一命令：

```bash
node scripts/sql-query.js query --source <stdin|file|inline> [options]
```

参数：

| 参数 | 适用范围 | 规则 |
|---|---|---|
| `--source` | 必填 | 仅接受 `stdin`、`file`、`inline` |
| `--sql` | `inline` | 必填；必须为单行，长度不超过 500 字符 |
| `--sql-path` | `file` | 必填；相对路径按调用 CLI 时的当前工作目录解析 |
| `--save` | 全部 | 可选；覆盖默认结果路径，支持 `.json`、`.csv`、`.xlsx` |
| `--retain-sql` | `file` | 可选；保留 `.cache/` 内执行成功的 SQL 文件 |
| `--trace-id` | 全部 | 可选；未提供时使用 `crypto.randomUUID()` 生成 |

参数严格互斥：

- `stdin` 禁止 `--sql`、`--sql-path`、`--retain-sql`。
- `file` 必须提供 `--sql-path`，禁止 `--sql`。
- `inline` 必须提供 `--sql`，禁止 `--sql-path`、`--retain-sql`。
- 旧参数 `--file`、`--stdin` 作为未知参数直接报错。
- 自定义 `trace_id` 仅允许字母、数字、点、下划线和连字符，避免路径穿越。

## Agent Source 路由

| 条件 | Source | 传输方式 |
|---|---|---|
| 调用工具支持独立 stdin payload | `stdin` | 父进程通过进程 API 将 UTF-8 SQL 直接写入 stdin |
| SQL 需要审阅、复跑、留痕 | `file` | 写入 `.cache/sql-query-<timestamp>-<random>.sql` 后传入路径 |
| 调用工具只有 Shell 命令能力 | `file` | 写入文件后使用 `--sql-path`，避免在命令文本中嵌入 SQL |
| Bash 环境且明确不落盘 | `stdin` | 使用带引号的 heredoc：`<<'EOF'` |
| SQL 简短、单行且无 Shell 特殊字符 | `inline` | 使用 `--sql` |
| SQL 含中文、引号、`$`、反引号、换行或用户输入值 | `stdin` 或 `file` | 禁止使用 `inline` |

禁止使用双引号 `echo` 或其他会让 Shell 展开 SQL 内容的拼接方式。CLI 只校验 inline 的长度和换行；特殊字符路由由 Skill 规范约束，以免误伤合法 SQL。

## 数据流

```text
Agent 选择 source
  -> CLI 解析并严格校验参数
  -> 从 stdin、文件或 argv 获取 UTF-8 SQL
  -> 执行 PostgreSQL 查询
  -> 生成执行信封
  -> 保存结果文件
  -> stdout 输出执行信封
  -> 按规则清理内部 SQL 缓存文件
```

数据库连接必须在 `finally` 中关闭。只有查询和结果保存均成功后，才允许清理 SQL 文件。

## 缓存与路径

运行时文件统一放在 `querying-via-sql/.cache/`，该目录加入根 `.gitignore`。默认结果路径固定相对于 Skill 目录，不受当前工作目录影响：

```text
querying-via-sql/.cache/result-<trace_id>.json
```

路径规则：

- `--sql-path` 和自定义 `--save` 的相对路径相对于调用 CLI 时的当前工作目录。
- 自定义保存路径的父目录不存在时自动创建。
- 保存格式严格根据扩展名判断，仅支持 `.json`、`.csv`、`.xlsx`。
- `.cache/` 内的 SQL 文件执行成功后默认删除；`--retain-sql` 可保留。
- `.cache/` 外的 SQL 文件始终保留，CLI 不提供删除外部文件的参数。
- 查询或保存失败时，SQL 文件始终保留。

## 输出协议

成功时 stdout 只输出一个 JSON 执行信封：

```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "source": "file",
  "result_path": "C:/.../querying-via-sql/.cache/result-550e8400-e29b-41d4-a716-446655440000.json",
  "row_count": 10,
  "columns": [],
  "rows": []
}
```

- 默认 `.json` 和自定义 `.json` 保存完整执行信封。
- `.csv`、`.xlsx` 只保存表格数据，stdout 仍输出完整信封。
- 进度、保存位置和诊断信息只写 stderr。
- 参数错误、SQL 为空、文件不可读、查询失败或保存失败时返回非零退出码，错误写 stderr，stdout 保持为空。

## 环境变量清理

删除以下运行时开关及相关代码：

```text
KEEP_SQL_FILE
KEEP_SQL_RESULT
```

SQL 保留行为由 `--retain-sql` 和文件所在目录决定。结果始终保存，默认路径由 CLI 生成，自定义路径由 `--save` 指定。

## 测试与验收

自动化测试覆盖：

- `stdin`、`file`、`inline` 的正常参数解析。
- 三种 source 的缺失参数、互斥参数和未知参数。
- 旧 `--file`、`--stdin` 参数被拒绝。
- stdin 中中文、引号、美元符号、反引号和多行内容原样保留。
- inline 超过 500 字符或包含换行时被拒绝。
- trace ID 自动生成、显式传入和非法值拒绝。
- 默认 `.cache` JSON 保存，以及自定义 JSON、CSV、XLSX 保存。
- 保存目录自动创建。
- `.cache/` SQL 默认清理、`--retain-sql` 保留、失败保留和外部文件保护。
- stdout 执行信封和 stderr 分流。
- 使用现有缓存 SQL 完成一次真实数据库回归测试。

## 非目标

- 不引入 JSON payload 模式。
- 不保留旧 CLI 参数兼容层。
- 不改变 `test-connection`、`schema` 或数据库查询实现。
- 不在本次改动中增加 SQL 只读语句检查。
