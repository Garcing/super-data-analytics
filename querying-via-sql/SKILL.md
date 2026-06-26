---
name: querying-via-sql
description: 从 Hologres/PostgreSQL 数据库查询数据，支持 stdin、文件和短 inline SQL，按需保存并输出查询结果
metadata:
  skill-series: super-data-analytics
  chinese-name: 查询数据通过SQL
---

# 查询数据通过 SQL

使用 Node.js 驱动直连 Hologres/PostgreSQL 查询返回数据。

## 环境要求

- Node.js 18+
- 凭证： `~/.super-data-analytics/config.json` 的 `env` 块；config.json 缺失或字段不全时，脚本报错并指引补全，由 agent 引导用户提供后写回：
  ```json
  { 
  	"env": { 
          "HOLOGRES_HOST": "...", 
          "HOLOGRES_PORT": "...", 
          "HOLOGRES_DATABASE": "...", 
          "HOLOGRES_USER": "...", 
          "HOLOGRES_PASSWORD": "..." 
      } 
  }
  ```

## CLI 命令

```bash
# 测试数据库连接
node scripts/sql-query.js test-connection

# 获取数据表schema
node scripts/sql-query.js schema <schema.table> [schema.table ...]

# 查询数据（支持inline sql、sql-file path、stdin三种方式）
# 可选保存查询结果：追加 [--save <file-path>]，格式支持 json/csv/xlsx
node scripts/sql-query.js query --query "<SQL>"                  
node scripts/sql-query.js query --query @<file-path>              
node scripts/sql-query.js query --query -             
```

## 路径命名约定

**临时写入SQL**

默认存入 `<工作区>/.super-data-analytics/scratch/`，命名规范为 `sql-query-YYYYMMDD-HHMMSS-<查询主题>.sql`，例如 `sql-query-20260531-133045-新用户7日留存.sql`

**结果命名约定**

默认不保存查询结果；当用户明确提出需求时保存

默认存入 `<工作区>/.super-data-analytics/results/`，命名和文件格式按用户提供，若无可参考 `sql-result-YYYYMMDD-HHMMSS-<查询主题>.<json|csv|xlsx>`

## Agent 路由

`--query` 承载三种来源：直接 SQL、@文件、管道 stdin，需按照以下规则判断，尽量避免写入临时SQL和JS文件

| 环境条件 | 写法 | 执行方式 |
|---|---|---|
| Agent支持进程API | 管道 stdin | 调用方进程在内存直接 `spawn` 子进程，并向子进程 stdin 写 UTF-8 SQL；不要为了使用 `spawn` 把 SQL 或 driver JS 落盘 |
| bash/zsh | 管道 stdin | quoted heredoc `<<'EOF'`（引号抑制 `$`或反引号展开） |
| PowerShell | 管道 stdin | 统一显式设置 `$OutputEncoding` 为 UTF-8 without BOM；单引号 here-string `@'...'@`；`$sql` 管道到 `node ... --query -` |
| SQL 需要审阅、复跑或留痕<br />管道stdin写法报错 | @文件 | agent 把 SQL 写入 `<工作区>/.super-data-analytics/scratch/`，经 `--query @` 传入 |
| 简短 SQL | 直接SQL | SQL 直接写入命令行；含 `$` 或反引号时不建议 inline，复杂 SQL 走 file/stdin 更稳 |

**注意事项**

- 含 `$` 或反引号的 SQL 不建议用 inline：双引号外层下 shell 会展开 `$abc`、执行反引号，可能拿到静默错误结果
- 原则上尽量不写临时SQL文件，管道stdin优先

**参考示例**

支持进程 API 时，调用方在内存直接 `spawn` 子进程写入 SQL

注意不要为了使用 spawn 额外生成临时 driver JS

```javascript
const child = spawn('node', ['scripts/sql-query.js', 'query', '--query', '-'], {
  stdio: ['pipe', 'pipe', 'pipe'],
});
child.stdin.end(sql, 'utf8');
```

bash/zsh 下用 quoted heredoc（不落盘、不展开，UTF-8 干净）

```bash
node scripts/sql-query.js query --query - <<'EOF'
SELECT 'a$b`c 中文' AS s;
EOF
```

PowerShell 下统一显式设置 UTF-8，再用单引号 here-string 经 stdin 传入

```powershell
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom

$sql = @'
SELECT '$abc' AS d, '中文 🚀' AS u;
'@

$sql | node scripts\sql-query.js query --query -
```

## 使用场景

### 获取数据表结构

调用方必须提前提供表名，本 Skill 不负责选择表。

```bash
node scripts/sql-query.js schema <schema1.table1> <schema2.table2>
```

### 查询和保存结果

参考上述CLI和Agent路由描述即可
