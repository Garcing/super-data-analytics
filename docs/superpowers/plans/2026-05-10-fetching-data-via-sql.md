# fetching-data-via-sql Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Node.js skill for querying Hologres (PostgreSQL) databases with file-driven SQL execution, matching the via-powerbi pattern.

**Architecture:** Single-file `sql-query.js` exports `HologresClient` class + CLI. Uses `pg` for database connectivity, `.env` for credentials, file-driven workflow with cache auto-deletion, and optional `--save` for result persistence (xlsx/csv/json).

**Tech Stack:** Node.js 18+, pg (node-postgres), xlsx (optional, for Excel export)

---

## File Map

| File | Responsibility |
|------|---------------|
| `fetching-data-via-sql/package.json` | Project manifest, dependencies |
| `fetching-data-via-sql/.gitignore` | Ignore node_modules/, .env, cache/ |
| `fetching-data-via-sql/.env` | Database connection credentials (template) |
| `fetching-data-via-sql/sql-query.js` | **Core**: HologresClient class + CLI entry point + all helpers |
| `fetching-data-via-sql/SKILL.md` | Skill definition for AI agent |
| `fetching-data-via-sql/templates/style.sql` | SQL writing style guide |
| `fetching-data-via-sql/tests/sql-query.test.js` | Unit tests |

**Existing files (no changes):**
- `fetching-data-via-sql/references/get_table_schema.sql` — table schema query (already complete)

---

### Task 1: Project Scaffold

**Files:**
- Create: `fetching-data-via-sql/package.json`
- Create: `fetching-data-via-sql/.gitignore`
- Create: `fetching-data-via-sql/.env`
- Create: `fetching-data-via-sql/cache/.gitkeep`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "sql-query",
  "private": true,
  "type": "module",
  "dependencies": {
    "pg": "^8.13.0"
  }
}
```

Note: `xlsx` is NOT a dependency — it will be dynamically imported only when `--save xxx.xlsx` is used, so users who only need csv/json don't need to install it.

- [ ] **Step 2: Create .gitignore**

```
node_modules/
.env
cache/
```

- [ ] **Step 3: Create .env template**

```env
HOLOGRES_HOST=xxx.hologres.aliyuncs.com
HOLOGRES_PORT=80
HOLOGRES_DATABASE=your_db
HOLOGRES_USER=access_id
HOLOGRES_PASSWORD=access_key
```

- [ ] **Step 4: Create cache/.gitkeep**

Empty file to ensure cache/ directory is tracked by git.

- [ ] **Step 5: Install dependencies**

Run: `cd fetching-data-via-sql && npm install`
Expected: `node_modules/` created with `pg` and its dependency `pg-cloudflare` / `pg-protocol`.

- [ ] **Step 6: Commit**

```bash
git add fetching-data-via-sql/package.json fetching-data-via-sql/package-lock.json fetching-data-via-sql/.gitignore fetching-data-via-sql/.env fetching-data-via-sql/cache/.gitkeep
git commit -m "feat(via-sql): project scaffold with pg dependency"
```

---

### Task 2: sql-query.js — .env Loader + Constants + Exported Helpers

**Files:**
- Create: `fetching-data-via-sql/sql-query.js`

This task builds the file skeleton: .env loader, constants, and all the pure helper functions. No database interaction yet.

- [ ] **Step 1: Write the failing test for parseQueryArgs**

Create `fetching-data-via-sql/tests/sql-query.test.js`:

```js
import assert from 'node:assert/strict';
import test from 'node:test';
import { join } from 'node:path';

async function importModule() {
  const originalArgv = process.argv;
  process.argv = [originalArgv[0], originalArgv[1]];
  try {
    return await import(`../sql-query.js?test=${Date.now()}`);
  } finally {
    process.argv = originalArgv;
  }
}

test('parseQueryArgs parses --file, --keep, --save flags', async () => {
  const { parseQueryArgs } = await importModule();

  assert.deepEqual(parseQueryArgs(['--file', 'cache/test.sql']), {
    filePath: 'cache/test.sql',
    keep: false,
    savePath: null,
  });

  assert.deepEqual(parseQueryArgs(['--file', 'cache/test.sql', '--keep']), {
    filePath: 'cache/test.sql',
    keep: true,
    savePath: null,
  });

  assert.deepEqual(parseQueryArgs(['--file', 'cache/test.sql', '--save', 'output.csv']), {
    filePath: 'cache/test.sql',
    keep: false,
    savePath: 'output.csv',
  });

  assert.deepEqual(parseQueryArgs(['--file', 'cache/test.sql', '--keep', '--save', 'out.xlsx']), {
    filePath: 'cache/test.sql',
    keep: true,
    savePath: 'out.xlsx',
  });
});

test('parseQueryArgs throws on missing --file', async () => {
  const { parseQueryArgs } = await importModule();
  assert.throws(() => parseQueryArgs([]), /--file/);
  assert.throws(() => parseQueryArgs(['--keep']), /--file/);
});

test('parseQueryArgs throws on unknown flag', async () => {
  const { parseQueryArgs } = await importModule();
  assert.throws(() => parseQueryArgs(['--file', 'a.sql', '--bogus']), /未知/);
});

test('shouldDeleteSqlFile only auto-deletes files inside cache', async () => {
  const { shouldDeleteSqlFile } = await importModule();

  assert.equal(shouldDeleteSqlFile(join(process.cwd(), 'cache', 'test.sql'), false), true);
  assert.equal(shouldDeleteSqlFile(join(process.cwd(), 'cache', 'test.sql'), true), false);
  assert.equal(shouldDeleteSqlFile(join(process.cwd(), 'test.sql'), false), false);
});

test('readSqlFile reads and trims SQL content', async () => {
  const { readSqlFile } = await importModule();
  const { mkdirSync, writeFileSync, rmSync } = await import('node:fs');
  const dir = join(process.cwd(), 'cache');
  const path = join(dir, 'test-read.sql');
  mkdirSync(dir, { recursive: true });
  writeFileSync(path, '  SELECT 1;\n  \n', 'utf8');
  try {
    const sql = readSqlFile(path);
    assert.equal(sql, 'SELECT 1;');
  } finally {
    rmSync(path, { force: true });
  }
});

test('readSqlFile throws on empty file', async () => {
  const { readSqlFile } = await importModule();
  const { mkdirSync, writeFileSync, rmSync } = await import('node:fs');
  const dir = join(process.cwd(), 'cache');
  const path = join(dir, 'empty.sql');
  mkdirSync(dir, { recursive: true });
  writeFileSync(path, '   \n  \n', 'utf8');
  try {
    assert.throws(() => readSqlFile(path), /空文件/);
  } finally {
    rmSync(path, { force: true });
  }
});
```

Run: `cd fetching-data-via-sql && node --test tests/sql-query.test.js`
Expected: FAIL (module not found)

- [ ] **Step 2: Write sql-query.js skeleton with helpers**

Create `fetching-data-via-sql/sql-query.js`:

```js
import {
  existsSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { join, dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// 从脚本所在目录向上查找 .env 文件并加载
const __dirname = dirname(fileURLToPath(import.meta.url));
for (let dir = __dirname; dir !== dirname(dir); dir = dirname(dir)) {
  try {
    const envPath = join(dir, '.env');
    const content = readFileSync(envPath, 'utf-8');
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eq = trimmed.indexOf('=');
      if (eq === -1) continue;
      const key = trimmed.slice(0, eq).trim();
      const val = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '');
      if (!process.env[key]) process.env[key] = val;
    }
    break;
  } catch {}
}

const CACHE_DIR = join(__dirname, 'cache');
const SCHEMA_SQL_PATH = join(__dirname, 'references', 'get_table_schema.sql');

// ── Exported helpers ──

export function parseQueryArgs(args) {
  let filePath;
  let keep = false;
  let savePath = null;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--file') {
      filePath = args[++i];
      if (!filePath) {
        throw new Error('用法: node sql-query.js query --file <file_path> [--keep] [--save <output>]');
      }
    } else if (arg === '--keep') {
      keep = true;
    } else if (arg === '--save') {
      savePath = args[++i];
      if (!savePath) {
        throw new Error('--save 需要指定输出文件路径');
      }
    } else {
      throw new Error(`未知 query 参数: ${arg}\n用法: node sql-query.js query --file <file_path> [--keep] [--save <output>]`);
    }
  }

  if (!filePath) {
    throw new Error('用法: node sql-query.js query --file <file_path> [--keep] [--save <output>]');
  }

  return { filePath, keep, savePath };
}

function isInsideCacheDir(filePath) {
  const base = resolve(CACHE_DIR);
  const target = resolve(filePath);
  const rel = relative(base, target);
  return rel && !rel.startsWith('..') && !isAbsolute(rel);
}

export function shouldDeleteSqlFile(filePath, keep) {
  return !keep && isInsideCacheDir(filePath);
}

export function readSqlFile(filePath) {
  let content;
  try {
    content = readFileSync(filePath, 'utf-8').replace(/^﻿/, '').trim();
  } catch (e) {
    throw new Error(`无法读取 SQL 文件 ${filePath}: ${e.message}`);
  }
  if (!content) {
    throw new Error(`SQL 文件为空: ${filePath}`);
  }
  return content;
}

// ── HologresClient (placeholder for Task 3) ──

export class HologresClient {
  constructor() {}
}

// ── CLI entry point ──

const [,, command, ...cliArgs] = process.argv;

if (command) {
  (async () => {
    try {
      const client = new HologresClient();
      switch (command) {
        case 'test-connection':
        case 'schema':
        case 'query':
          console.error(`命令 "${command}" 尚未实现`);
          process.exit(1);
        default:
          console.error(`未知命令: ${command}\n`);
          console.error('用法: node sql-query.js <命令> [参数]');
          console.error('');
          console.error('命令:');
          console.error('  test-connection              测试数据库连接');
          console.error('  schema <tableName>           获取表结构');
          console.error('  query --file <file_path>     从 SQL 文件读取并执行查询');
          process.exit(1);
      }
    } catch (err) {
      console.error(err.message);
      process.exit(1);
    }
  })();
}
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd fetching-data-via-sql && node --test tests/sql-query.test.js`
Expected: All 6 tests PASS

- [ ] **Step 4: Commit**

```bash
git add fetching-data-via-sql/sql-query.js fetching-data-via-sql/tests/sql-query.test.js
git commit -m "feat(via-sql): env loader, constants, and helper functions with tests"
```

---

### Task 3: HologresClient — Database Connection + test-connection + schema

**Files:**
- Modify: `fetching-data-via-sql/sql-query.js`
- Modify: `fetching-data-via-sql/tests/sql-query.test.js`

This task implements the `HologresClient` class with constructor, `testConnection`, `getTableSchema`, `query`, and `close` methods.

- [ ] **Step 1: Write tests for HologresClient constructor validation**

Add to `fetching-data-via-sql/tests/sql-query.test.js`:

```js
test('HologresClient constructor throws on missing env vars', async () => {
  const { HologresClient } = await importModule();
  const original = {
    HOST: process.env.HOLOGRES_HOST,
    PORT: process.env.HOLOGRES_PORT,
    DATABASE: process.env.HOLOGRES_DATABASE,
    USER: process.env.HOLOGRES_USER,
    PASSWORD: process.env.HOLOGRES_PASSWORD,
  };
  delete process.env.HOLOGRES_HOST;
  delete process.env.HOLOGRES_PORT;
  delete process.env.HOLOGRES_DATABASE;
  delete process.env.HOLOGRES_USER;
  delete process.env.HOLOGRES_PASSWORD;
  try {
    assert.throws(() => new HologresClient(), /缺少环境变量/);
  } finally {
    Object.assign(process.env, original);
  }
});

test('HologresClient constructor creates pool from env vars', async () => {
  const { HologresClient } = await importModule();
  const original = {
    HOST: process.env.HOLOGRES_HOST,
    PORT: process.env.HOLOGRES_PORT,
    DATABASE: process.env.HOLOGRES_DATABASE,
    USER: process.env.HOLOGRES_USER,
    PASSWORD: process.env.HOLOGRES_PASSWORD,
  };
  process.env.HOLOGRES_HOST = 'localhost';
  process.env.HOLOGRES_PORT = '5432';
  process.env.HOLOGRES_DATABASE = 'testdb';
  process.env.HOLOGRES_USER = 'testuser';
  process.env.HOLOGRES_PASSWORD = 'testpass';
  try {
    const client = new HologresClient();
    assert.ok(client.pool);
    assert.equal(client.pool.options.host, 'localhost');
    assert.equal(client.pool.options.port, '5432');
    assert.equal(client.pool.options.database, 'testdb');
    assert.equal(client.pool.options.user, 'testuser');
    assert.equal(client.pool.options.password, 'testpass');
    await client.close();
  } finally {
    Object.assign(process.env, original);
  }
});
```

- [ ] **Step 2: Run tests to see them fail**

Run: `cd fetching-data-via-sql && node --test tests/sql-query.test.js`
Expected: New tests FAIL (constructor doesn't validate or create pool)

- [ ] **Step 3: Implement HologresClient class**

Replace the placeholder `HologresClient` class in `fetching-data-via-sql/sql-query.js` with:

```js
import pg from 'pg';

// ... (existing .env loader, constants, helpers stay the same) ...

export class HologresClient {
  constructor() {
    const env = process.env;
    const host = env.HOLOGRES_HOST;
    const port = env.HOLOGRES_PORT;
    const database = env.HOLOGRES_DATABASE;
    const user = env.HOLOGRES_USER;
    const password = env.HOLOGRES_PASSWORD;

    const missing = [
      !host && 'HOLOGRES_HOST',
      !port && 'HOLOGRES_PORT',
      !database && 'HOLOGRES_DATABASE',
      !user && 'HOLOGRES_USER',
      !password && 'HOLOGRES_PASSWORD',
    ].filter(Boolean);

    if (missing.length > 0) {
      throw new Error(
        `缺少环境变量: ${missing.join(', ')}\n\n` +
        '配置方法:\n' +
        '  在脚本同级目录（或上级目录）创建 .env 文件:\n' +
        '  HOLOGRES_HOST=xxx.hologres.aliyuncs.com\n' +
        '  HOLOGRES_PORT=80\n' +
        '  HOLOGRES_DATABASE=your_db\n' +
        '  HOLOGRES_USER=access_id\n' +
        '  HOLOGRES_PASSWORD=access_key'
      );
    }

    this.pool = new pg.Pool({
      host,
      port: Number(port),
      database,
      user,
      password,
      max: 5,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
    });
  }

  async testConnection() {
    const client = await this.pool.connect();
    try {
      await client.query('SELECT 1');
    } finally {
      client.release();
    }
    return { ok: true, message: '数据库连接成功' };
  }

  async getTableSchema(tableName, schema = 'public') {
    const templateSql = readFileSync(SCHEMA_SQL_PATH, 'utf-8');
    const sql = templateSql
      .replace(/'schema_name'/g, `'${schema}'`)
      .replace(/'table_name'/g, `'${tableName}'`);
    const result = await this.pool.query(sql);
    return result.rows;
  }

  async query(sql) {
    const result = await this.pool.query(sql);
    const columns = result.fields.map(f => ({ name: f.name, dataTypeID: f.dataTypeID }));
    return { columns, rows: result.rows };
  }

  async close() {
    await this.pool.end();
  }
}
```

**Important:** Add `import pg from 'pg';` at the top of the file, after the existing imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd fetching-data-via-sql && node --test tests/sql-query.test.js`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add fetching-data-via-sql/sql-query.js fetching-data-via-sql/tests/sql-query.test.js
git commit -m "feat(via-sql): HologresClient with connection, schema, and query methods"
```

---

### Task 4: CLI Commands — test-connection, schema, query

**Files:**
- Modify: `fetching-data-via-sql/sql-query.js` (replace placeholder CLI switch cases)

This task wires up the CLI entry point to call the real methods.

- [ ] **Step 1: Implement CLI commands**

Replace the placeholder CLI switch block in `fetching-data-via-sql/sql-query.js` with:

```js
if (command) {
  (async () => {
    try {
      const client = new HologresClient();

      switch (command) {
        case 'test-connection': {
          const result = await client.testConnection();
          console.log(JSON.stringify(result, null, 2));
          await client.close();
          break;
        }
        case 'schema': {
          const [tableName, ...schemaArgs] = cliArgs;
          if (!tableName) {
            console.error('用法: node sql-query.js schema <tableName> [--schema <schemaName>]');
            process.exit(1);
          }
          let schemaName = 'public';
          for (let i = 0; i < schemaArgs.length; i++) {
            if (schemaArgs[i] === '--schema') {
              schemaName = schemaArgs[++i] || 'public';
            }
          }
          const rows = await client.getTableSchema(tableName, schemaName);
          console.log(JSON.stringify(rows, null, 2));
          await client.close();
          break;
        }
        case 'query': {
          const { filePath, keep, savePath } = parseQueryArgs(cliArgs);
          try {
            const sql = readSqlFile(filePath);
            const result = await client.query(sql);
            if (savePath) {
              await saveResult(result, savePath);
              console.error(`结果已保存到: ${savePath}`);
            } else {
              console.log(JSON.stringify(result, null, 2));
            }
          } finally {
            if (shouldDeleteSqlFile(filePath, keep) && existsSync(filePath)) {
              unlinkSync(filePath);
            }
          }
          await client.close();
          break;
        }
        default:
          console.error(`未知命令: ${command}\n`);
          console.error('用法: node sql-query.js <命令> [参数]');
          console.error('');
          console.error('命令:');
          console.error('  test-connection              测试数据库连接');
          console.error('  schema <tableName>           获取表结构');
          console.error('  query --file <file_path>     从 SQL 文件读取并执行查询');
          process.exit(1);
      }
    } catch (err) {
      console.error(err.message);
      process.exit(1);
    }
  })();
}
```

- [ ] **Step 2: Verify CLI help output**

Run: `cd fetching-data-via-sql && node sql-query.js bogus`
Expected: Prints "未知命令: bogus" and usage help, exits with code 1.

- [ ] **Step 3: Commit**

```bash
git add fetching-data-via-sql/sql-query.js
git commit -m "feat(via-sql): wire CLI commands to HologresClient methods"
```

---

### Task 5: Result Saving — saveResult function with csv/json/xlsx

**Files:**
- Modify: `fetching-data-via-sql/sql-query.js` (add saveResult function)
- Modify: `fetching-data-via-sql/tests/sql-query.test.js` (add saveResult tests)

- [ ] **Step 1: Write tests for saveResult**

Add to `fetching-data-via-sql/tests/sql-query.test.js`:

```js
test('saveResult saves JSON file', async () => {
  const { saveResult } = await importModule();
  const { readFileSync, rmSync } = await import('node:fs');
  const result = {
    columns: [{ name: 'id' }, { name: 'name' }],
    rows: [{ id: 1, name: 'Alice' }, { id: 2, name: 'Bob' }],
  };
  const path = join(process.cwd(), 'cache', 'test-output.json');
  await saveResult(result, path);
  try {
    const saved = JSON.parse(readFileSync(path, 'utf-8'));
    assert.deepEqual(saved, result);
  } finally {
    rmSync(path, { force: true });
  }
});

test('saveResult saves CSV file', async () => {
  const { saveResult } = await importModule();
  const { readFileSync, rmSync } = await import('node:fs');
  const result = {
    columns: [{ name: 'id' }, { name: 'name' }],
    rows: [{ id: 1, name: 'Alice' }, { id: 2, name: 'Bob' }],
  };
  const path = join(process.cwd(), 'cache', 'test-output.csv');
  await saveResult(result, path);
  try {
    const csv = readFileSync(path, 'utf-8');
    assert.ok(csv.includes('id,name'));
    assert.ok(csv.includes('1,Alice'));
    assert.ok(csv.includes('2,Bob'));
  } finally {
    rmSync(path, { force: true });
  }
});

test('saveResult throws on unsupported extension', async () => {
  const { saveResult } = await importModule();
  const result = { columns: [], rows: [] };
  await assert.rejects(
    () => saveResult(result, join(process.cwd(), 'cache', 'out.txt')),
    /不支持的文件格式/
  );
});
```

- [ ] **Step 2: Run tests to see them fail**

Run: `cd fetching-data-via-sql && node --test tests/sql-query.test.js`
Expected: New tests FAIL (saveResult not defined)

- [ ] **Step 3: Implement saveResult**

Add this exported function to `fetching-data-via-sql/sql-query.js`, after the existing exported helpers:

```js
export async function saveResult(result, savePath) {
  const ext = savePath.slice(savePath.lastIndexOf('.')).toLowerCase();

  if (ext === '.json') {
    writeFileSync(savePath, JSON.stringify(result, null, 2), 'utf-8');
  } else if (ext === '.csv') {
    const { columns, rows } = result;
    const header = columns.map(c => c.name).join(',');
    const dataRows = rows.map(row => columns.map(c => {
      const val = row[c.name];
      const str = val === null || val === undefined ? '' : String(val);
      return str.includes(',') || str.includes('"') || str.includes('\n')
        ? `"${str.replace(/"/g, '""')}"`
        : str;
    }).join(','));
    writeFileSync(savePath, [header, ...dataRows].join('\n'), 'utf-8');
  } else if (ext === '.xlsx') {
    let XLSX;
    try {
      XLSX = await import('xlsx');
    } catch {
      throw new Error('xlsx 格式需要安装 xlsx 依赖: npm install xlsx');
    }
    const { columns, rows } = result;
    const header = columns.map(c => c.name);
    const dataRows = rows.map(row => columns.map(c => row[c.name]));
    const ws = XLSX.utils.aoa_to_sheet([header, ...dataRows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
    XLSX.writeFile(wb, savePath);
  } else {
    throw new Error(`不支持的文件格式: ${ext}（支持 .json / .csv / .xlsx）`);
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd fetching-data-via-sql && node --test tests/sql-query.test.js`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add fetching-data-via-sql/sql-query.js fetching-data-via-sql/tests/sql-query.test.js
git commit -m "feat(via-sql): saveResult with csv/json/xlsx export"
```

---

### Task 6: SKILL.md

**Files:**
- Create: `fetching-data-via-sql/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: fetching-data-via-sql
description: 从 Hologres/PostgreSQL 数据库查询数据，文件驱动 SQL 执行，支持结果导出
---

# SQL 数据获取

从 Hologres (PostgreSQL) 数据库查询数据，使用 pg 驱动直连

## 触发条件

- 用户需要从数据库查询数据
- 其他 skill 需要数据库数据时引用
- 用户使用 `/fetching-data-via-sql` 命令

## 环境要求

- Node.js 18+
- 数据库凭证（`.env` 文件或环境变量）：`HOLOGRES_HOST`、`HOLOGRES_PORT`、`HOLOGRES_DATABASE`、`HOLOGRES_USER`、`HOLOGRES_PASSWORD`

## CLI 命令

```bash
# 测试连接
node sql-query.js test-connection

# 获取表结构
node sql-query.js schema <tableName> [--schema <schemaName>]

# 执行 SQL 文件
node sql-query.js query --file <file_path> [--keep] [--save <output>]
```

## 核心流程

### Step 1：获取表结构

调用方必须提前提供要使用的表名（本 skill 不负责选择表）。

```bash
node sql-query.js schema <表名>
```

返回字段信息：序号、字段名、数据类型、默认值、是否允许为空、是否为主键、字段注释。

### Step 2：编写 SQL

根据表结构 + 用户需求编写 SQL，写入 `cache/` 目录，文件名格式：

```text
request-YYYYMMDD-HHMMSS-<random>.sql
```

如 `cache/request-20260510-143522-a7f3c98f4k.sql`。

**SQL 编写要点**：
1. 确认涉及的表名和字段名与 schema 返回的一致
2. 注意 Hologres 的分区表特性，WHERE 条件尽量包含分区键
3. 大查询加 LIMIT 控制返回行数
4. 避免全表扫描，善用索引字段过滤

### Step 3：执行查询

```bash
node sql-query.js query --file cache/<Step2生成的文件.sql>
```

默认行为：查询结果以 JSON 输出到 stdout，SQL 文件执行后自动删除。

**保存结果**：

```bash
# 保存为 CSV
node sql-query.js query --file cache/xxx.sql --save output.csv

# 保存为 Excel（需要 npm install xlsx）
node sql-query.js query --file cache/xxx.sql --save output.xlsx

# 保存为 JSON
node sql-query.js query --file cache/xxx.sql --save output.json
```

**调试时保留 SQL 文件**：

```bash
node sql-query.js query --file cache/xxx.sql --keep
```

## 输入

- 表名（由调用方提供，本 skill 不选择表）
- SQL 语句（写入 cache/ 目录的 .sql 文件）

## 输出

JSON 格式：`{ columns: [{name, dataTypeID}], rows: [{col1: val1, col2: val2}] }`

或通过 `--save` 保存为文件（csv / xlsx / json）。
```

- [ ] **Step 2: Commit**

```bash
git add fetching-data-via-sql/SKILL.md
git commit -m "feat(via-sql): skill definition document"
```

---

### Task 7: SQL Style Template

**Files:**
- Create: `fetching-data-via-sql/templates/style.sql`

- [ ] **Step 1: Write style.sql**

```sql
-- ═══════════════════════════════════════════════════
-- SQL 编写风格指南（Hologres / PostgreSQL）
-- ═══════════════════════════════════════════════════

-- 1. 查询结构：SELECT → FROM → JOIN → WHERE → GROUP BY → HAVING → ORDER BY → LIMIT
-- 2. 关键字大写，表名/字段名保持原始大小写
-- 3. 子查询用 WITH (CTE) 代替嵌套，提高可读性
-- 4. 每个查询必须带 LIMIT，防止返回过多数据
-- 5. WHERE 中尽量包含分区键（日期字段等），避免全分区扫描
-- 6. 字符串用单引号，标识符用双引号（仅在需要时）

-- ═══ 示例 ═══

-- 基础查询
SELECT
    column_a,
    column_b,
    COUNT(*) AS cnt
FROM schema_name.table_name
WHERE dt = '2026-05-10'          -- 分区键过滤
    AND status = 'active'
GROUP BY column_a, column_b
ORDER BY cnt DESC
LIMIT 100;

-- 使用 CTE
WITH daily_stats AS (
    SELECT
        dt,
        COUNT(DISTINCT user_id) AS dau
    FROM schema_name.table_name
    WHERE dt BETWEEN '2026-05-01' AND '2026-05-10'
    GROUP BY dt
)
SELECT
    dt,
    dau,
    dau - LAG(dau) OVER (ORDER BY dt) AS dau_diff
FROM daily_stats
ORDER BY dt
LIMIT 100;
```

- [ ] **Step 2: Commit**

```bash
git add fetching-data-via-sql/templates/style.sql
git commit -m "feat(via-sql): SQL style guide template"
```

---

## Self-Review

**Spec coverage:**
- ✅ File structure (package.json, .gitignore, .env, sql-query.js, SKILL.md, templates/style.sql, tests)
- ✅ CLI commands: test-connection, schema, query
- ✅ query flags: --file, --keep, --save
- ✅ HologresClient class: constructor, testConnection, getTableSchema, query, close
- ✅ .env configuration with 5 vars
- ✅ pg dependency
- ✅ xlsx dynamic import (not a hard dependency)
- ✅ Cache auto-deletion (files in cache/ deleted by default, --keep prevents, files outside cache/ never deleted)
- ✅ get_table_schema.sql wrapped in getTableSchema method
- ✅ SKILL.md with workflow

**Placeholder scan:** No TBD, TODO, or "implement later" found. All steps have complete code.

**Type consistency:**
- `parseQueryArgs` returns `{ filePath, keep, savePath }` — used consistently in Task 4 CLI
- `readSqlFile` returns string — used in Task 4 CLI
- `shouldDeleteSqlFile(filePath, keep)` — 2 params matching `parseQueryArgs.keep`
- `saveResult(result, savePath)` — takes `{ columns, rows }` matching `HologresClient.query()` return
- `HologresClient.query()` returns `{ columns: [{name, dataTypeID}], rows: [{...}] }` — consistent across tests and saveResult
