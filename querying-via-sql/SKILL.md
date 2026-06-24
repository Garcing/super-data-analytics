---
name: querying-via-sql
description: 从 Hologres/PostgreSQL 数据库查询数据，支持 stdin、文件和短 inline SQL，统一保存并输出查询结果
metadata:
  skill-series: super-data-analytics
  chinese-name: 查询数据通过SQL
---

# 查询数据通过 SQL

使用 Node.js `pg` 驱动直连 Hologres/PostgreSQL。Agent 必须在执行 CLI 前选择 SQL source，禁止把复杂 SQL 直接拼进 Shell 命令。

## 环境要求

- Node.js 18+
- 凭证（舰队共享一份）：统一放 `~/.super-data-analytics/config.json` 的 `env` 块（**唯一来源**，不再支持环境变量覆盖）；config.json 缺失或字段不全时，脚本报错并指引补全，由 agent 引导用户提供后写回：
  ```json
  { "env": { "HOLOGRES_HOST": "...", "HOLOGRES_PORT": "80", "HOLOGRES_DATABASE": "...", "HOLOGRES_USER": "...", "HOLOGRES_PASSWORD": "..." } }
  ```

## CLI

```bash
node scripts/sql-query.js test-connection
node scripts/sql-query.js schema <schema.table> [schema.table ...]

# 三种查询写法（--query 是唯一入口）：
node scripts/sql-query.js query --query "<SQL>"                  # 直接写 SQL（短纯 ASCII 单行）
node scripts/sql-query.js query --query @<文件>                    # @ + 文件路径
node scripts/sql-query.js query --query - <<'EOF'                # 管道 stdin（heredoc 喂入；也支持父进程 spawn）
SELECT ...;
EOF
# 通用可选：[--save <path>] [--trace-id <id>]
```

## 路径约定（JS 不管，agent 按 MD 约定构造）

**JS 不内置任何目录结构**：结果由 `--save <path>` 指定（默认落 `cwd/result-<trace>.json`），SQL 文件路径由 `--query @<path>` 指定。`.super-data-analytics/{results,scratch}` 这套布局是 **MD 约定，由 agent 自己构造路径**传进去，JS 不创建、不清理、不假设。

| 类别 | 去向 | 怎么传 |
|---|---|---|
| **凭证(home)** | `~/.super-data-analytics/config.json` 的 `env` 块 | JS 自己读，舰队共享一份 |
| **产物(workspace)** | `<工作区>/.super-data-analytics/results/result-<trace>.json` | agent 构造路径，经 `--save` 传 |
| **scratch(workspace)** | `<工作区>/.super-data-analytics/scratch/sql-query-<ts>-<rand>.sql` | agent 构造路径，经 `--query @<path>` 传 |

> **scratch 由 agent 全权管理**：写进去、复跑、清理都归 agent；JS 不会自动删任何 SQL 文件。建议在工作区项目根加一行 `.super-data-analytics/scratch/` 到 `.gitignore`（临时件不该进版本库）。技能不会自动改你的 `.gitignore`。

旧参数 `query --stdin`、`query --file`、`--source`、`--sql`、`--sql-path`、`--work-dir`、`--retain-sql` 已全部删除，统一为 `--query`。

## Agent 路由（--query 三种写法）

> **路由的本质是"SQL 文本由谁解析"，不是"是否落盘"。** `--query` 一个参数承载三种来源：直接 SQL、`@文件`、管道 stdin。判断顺序：有进程 API → 管道 stdin；POSIX shell → heredoc；PowerShell → driver+spawn；需要审阅/留痕 → `@文件`；只有短纯 ASCII 才直接写。

| 条件 | 写法 | 执行方式 |
|---|---|---|
| 调用工具支持**进程 API**（harness/Agent SDK） | 管道 stdin | **首选**；父进程 `spawn` 写 UTF-8 SQL，唯一无 shell 路径，bash/zsh/PowerShell 通用 |
| bash/zsh 下、明确不落盘 | 管道 stdin | quoted heredoc `<<'EOF'`（引号抑制 `$`/反引号展开） |
| **PowerShell-only** | 管道 stdin | `.js driver` + `spawn`（避开 PS 灌原生 stdin 的 UTF-16/GBK 编码坑，不要用 here-string 传中文/emoji） |
| SQL 需要审阅、复跑或**留痕** | `--query @<文件>` | agent 把 SQL 写进 `<工作区>/.super-data-analytics/scratch/`，经 `--query @` 传入；文件不会被自动删除，清理归 agent |
| 简短、单行、纯 ASCII、无 Shell 特殊字符 | `--query "<SQL>"` | ≤500 字符；含中文/引号/`$`/反引号/反斜杠会被脚本拒绝 |

禁止把含特殊字符的 SQL 直接写进 `--query`（shell 会展开 `$abc`、执行反引号，拿到静默错误结果）：

```bash
node scripts/sql-query.js query --query "select '$abc', 'a`b';"    # ❌ shell 展开
```

推荐父进程直接写 stdin（进程 API 路由，shell 完全不接触 SQL，任何环境都适用）：

```javascript
const child = spawn('node', ['scripts/sql-query.js', 'query'], {
  stdio: ['pipe', 'pipe', 'pipe'],
});
child.stdin.end(sql, 'utf8');
```

bash/zsh 下用 quoted heredoc（不落盘、不展开，UTF-8 干净）：

```bash
node scripts/sql-query.js query --query - <<'EOF'
SELECT 'a$b`c 中文' AS s;
EOF
```

## 工作流

### Phase 1：获取表结构

调用方必须提前提供表名，本 Skill 不负责选择表。

```bash
node scripts/sql-query.js schema <schema.table> [schema.table ...]
```

### Phase 2：生成 SQL

需要文件模式时，参考 [`templates/style.sql`](templates/style.sql)，由 agent 把 SQL 写进**工作区**下的 scratch 区（路径 agent 自己构造，JS 不管）：

```text
<工作区>/.super-data-analytics/scratch/sql-query-YYYYMMDD-HHMMSS-<至少10位随机字符>.sql
```

### Phase 3：执行与读取结果

```bash
# --query @文件 读取 scratch 里的 SQL；--save 指定结果地址（不传则落 cwd/result-<trace>.json）
node scripts/sql-query.js query --query @<工作区>/.super-data-analytics/scratch/<file.sql> --save <工作区>/.super-data-analytics/results/result-<trace>.json
```

stdout 同时返回完整执行信封：

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

- `.json` 保存完整执行信封；`.csv`、`.xlsx` 只保存表格数据。
- SQL 文件不会被自动删除；scratch 的清理归 agent。
- 不使用 `KEEP_SQL_FILE`、`KEEP_SQL_RESULT` 环境变量。
