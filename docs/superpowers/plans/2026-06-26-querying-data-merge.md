# querying-data 合并 SQL 与 PowerBI 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `querying-via-sql` 与 `querying-via-powerbi` 合并为单一 skill `querying-data`，对外只有一个入口 `query.js --source <sql|powerbi>`，统一 `--query`（inline/@file/stdin）、统一 config.json、统一保存约定。

**Architecture:** 一个 dispatcher (`scripts/query.js`) 按 `--source` 路由到 `lib/sql.js` 或 `lib/powerbi.js`。SQL 驱动从现 `sql-query.js` 近原样迁入（逻辑零改动）。PowerBI 驱动从 `powerbi-mcp.js` 迁入，改造点：凭证从 `.env` 改读 config.json、请求从 `--file <json>` 改为 `--query` 三模式、删除 `cache/` 强制落盘与 `KEEP_DAX_*` 逻辑、`--save` 仅 json、新增保底 `powerbi-semantic-models` 回落。凭证/模型路由全并入 `~/.super-data-analytics/config.json`。

**Tech Stack:** Node.js 18+ (ESM)、`pg`（Hologres/PostgreSQL）、`@azure/identity`（PowerBI Client Credentials）、`xlsx`（仅 SQL 保存）。

**测试策略说明（重要）：** 本仓库没有测试框架，且两个数据源都是**线上外部服务**（Hologres、PowerBI MCP 预览端点）。因此本计划不引入伪造的单元测试框架，而是用**线上 smoke 验证**作为每步的验收：每条命令给出确切的运行指令与期望输出形态。`test-connection --source X` 是贯穿全程的真实断言。验证凭据在 `~/.super-data-analytics/config.json`，执行者需有线上访问权限。

**关键全局约束：**
- `pg` 的 Hologres BufferReader monkey-patch（处理 null 字段名）必须原样保留，迁移时一个字符都不能丢。
- SQL 的满意版本逻辑零改动：`--query` 三模式、stdin 15s 超时、envelope `{source,row_count,columns,rows,[result_path?]}`、`--save` json/csv/xlsx 全部保留。
- config.json 路径：`~/.super-data-analytics/config.json`，唯一来源。

**参考 spec：** `docs/superpowers/specs/2026-06-26-querying-data-merge-design.md`

---

## 文件结构

创建：
- `querying-data/scripts/query.js` — 唯一 CLI 入口/dispatcher
- `querying-data/scripts/lib/sql.js` — SQL 驱动（迁自 `querying-via-sql/scripts/sql-query.js`）
- `querying-data/scripts/lib/powerbi.js` — PowerBI 驱动（迁自 `querying-via-powerbi/scripts/powerbi-mcp.js`）
- `querying-data/scripts/package.json` — 合并依赖
- `querying-data/SKILL.md` — 入口路由器
- `querying-data/references/sql.md` — SQL CLI + payload + stdin 路由示例
- `querying-data/references/powerbi.md` — PowerBI CLI + JSON payload schema + DAX 函数参考 + artifactId 保底规则

移动（保留内容）：
- `querying-via-sql/references/get_table_schema.sql` → `querying-data/references/get_table_schema.sql`
- `querying-via-sql/templates/style.sql` → `querying-data/templates/style.sql`

删除（最后清理任务）：
- `querying-via-sql/`、`querying-via-powerbi/` 整个目录

修改：
- `~/.super-data-analytics/config.json` — 加 `POWERBI_*` env、加 `powerbi-semantic-models` 键
- 根 `CLAUDE.md` / `AGENTS.md` — 更新过时的板块名/路径

---

## Task 1: 脚手架与合并依赖

**Files:**
- Create: `querying-data/scripts/package.json`

- [ ] **Step 1: 建目录结构**

```bash
mkdir -p querying-data/scripts/lib querying-data/references querying-data/templates
```

- [ ] **Step 2: 写合并后的 package.json**

Create `querying-data/scripts/package.json`:

```json
{
  "name": "querying-data",
  "private": true,
  "type": "module",
  "dependencies": {
    "@azure/identity": "^4.0.0",
    "pg": "^8.13.0",
    "xlsx": "^0.18.5"
  }
}
```

- [ ] **Step 3: 安装依赖**

Run:
```bash
cd querying-data/scripts && npm install
```
Expected: 生成 `node_modules/` 与 `package-lock.json`，无报错。

- [ ] **Step 4: 把 .gitignore 规则对齐**

确认 `querying-data/scripts/node_modules/` 不会被提交（仓库根 `.gitignore` 已忽略 `node_modules` 即可；若无，在本任务后由 Task 8 统一处理）。

- [ ] **Step 5: Commit**

```bash
git add querying-data/scripts/package.json querying-data/scripts/package-lock.json
git commit -m "feat(querying-data): 脚手架与合并依赖 pg+xlsx+@azure/identity"
```

---

## Task 2: 迁移 SQL 驱动 + dispatcher 的 sql 分支

**Files:**
- Create: `querying-data/scripts/lib/sql.js`（迁自 `querying-via-sql/scripts/sql-query.js`）
- Create: `querying-data/scripts/query.js`（先只实现 `--source sql` 分支）
- Move: `querying-via-sql/references/get_table_schema.sql` → `querying-data/references/get_table_schema.sql`
- Move: `querying-via-sql/templates/style.sql` → `querying-data/templates/style.sql`

**关键：SQL 逻辑零改动。** `lib/sql.js` 的内容 = 现 `sql-query.js` 全文照搬，**唯一改动**是把"CLI 入口"那段（文件末尾 `const [,, command, ...cliArgs] = process.argv;` 起的 IIFE）拆出去——`lib/sql.js` 只导出可调用函数，CLI 解析移到 `query.js`。这样 dispatcher 才能统一调度。

- [ ] **Step 1: 移动静态资源**

```bash
git mv querying-via-sql/references/get_table_schema.sql querying-data/references/get_table_schema.sql
git mv querying-via-sql/templates/style.sql querying-data/templates/style.sql
```

- [ ] **Step 2: 创建 lib/sql.js（导出函数，不含 CLI 入口）**

Create `querying-data/scripts/lib/sql.js`，把 `querying-via-sql/scripts/sql-query.js` 的全部逻辑搬过来，**保留** pg-protocol monkey-patch、`loadConfig`、`HologresClient`、`parseQueryArgs`、`readSqlFile`、`readSqlFromStdin`、`readSqlSource`、`resolveQueryOptions`、`createResultEnvelope`、`saveResult` 全部原样。

需要改两处路径/导出：

(a) `SCHEMA_SQL_PATH` 路径——因为文件从 `scripts/sql-query.js` 移到 `scripts/lib/sql.js`，多了一层，改成向上两级：

```js
const ROOT_DIR = dirname(dirname(__dirname)); // scripts/lib/ → querying-data/
const SCHEMA_SQL_PATH = join(ROOT_DIR, 'references', 'get_table_schema.sql');
```

(b) 文件末尾**删除** CLI 入口 IIFE（`const [,, command, ...cliArgs] = process.argv;` 整段），改为导出供 dispatcher 调用的函数：

```js
export {
  loadConfig,
  HologresClient,
  parseQueryArgs,
  resolveQueryOptions,
  readSqlSource,
  createResultEnvelope,
  saveResult,
};
```

- [ ] **Step 3: 创建 query.js dispatcher（先只接 sql）**

Create `querying-data/scripts/query.js`:

```js
import { loadConfig, HologresClient, parseQueryArgs, resolveQueryOptions, readSqlSource, createResultEnvelope, saveResult } from './lib/sql.js';

const SOURCES = new Set(['sql']); // powerbi 在 Task 4 加入

function parseGlobalArgs(args) {
  // 解析 --source，返回 { source, rest }
  let source = null;
  const rest = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--source') {
      source = args[++i];
      if (!source) throw new Error('--source 需要指定值：sql | powerbi');
    } else {
      rest.push(args[i]);
    }
  }
  if (!source) throw new Error('缺少 --source（sql | powerbi）');
  if (!SOURCES.has(source)) throw new Error(`不支持的 --source: ${source}（当前支持：${[...SOURCES].join(', ')}）`);
  return { source, rest };
}

async function runSql(command, cliArgs) {
  let client;
  try {
    loadConfig();
    switch (command) {
      case 'test-connection': {
        client = new HologresClient();
        console.log(JSON.stringify(await client.testConnection(), null, 2));
        break;
      }
      case 'schema': {
        if (cliArgs.length === 0) throw new Error('用法: query.js schema --source sql <schema.table> [schema.table ...]');
        client = new HologresClient();
        const allRows = [];
        for (const arg of cliArgs) {
          const dotIndex = arg.indexOf('.');
          if (dotIndex === -1) throw new Error(`参数格式错误: "${arg}"，应为 schema.table`);
          const schemaName = arg.slice(0, dotIndex);
          const tableName = arg.slice(dotIndex + 1);
          const rows = await client.getTableSchema(tableName, schemaName);
          allRows.push({ schema: schemaName, table: tableName, columns: rows });
        }
        console.log(JSON.stringify(allRows, null, 2));
        break;
      }
      case 'query': {
        const options = resolveQueryOptions(parseQueryArgs(cliArgs));
        if (options.source === 'stdin' && process.stdin.isTTY) {
          throw new Error('未提供 --query 且 stdin 是终端。请用 --query "<SQL>"、--query @<文件> 或管道传入');
        }
        const sql = await readSqlSource(options);
        client = new HologresClient();
        const result = await client.query(sql);
        const envelope = createResultEnvelope({ source: 'sql', resultPath: options.savePath, result });
        if (options.savePath) {
          await saveResult(envelope, options.savePath);
          console.error(`结果已保存到: ${options.savePath}`);
        }
        console.log(JSON.stringify(envelope, null, 2));
        break;
      }
      default:
        throw new Error(`sql 未知命令: ${command}（支持：test-connection / schema / query）`);
    }
  } finally {
    if (client) await client.close();
  }
}

const [,, command, ...afterCommand] = process.argv;
if (!command) {
  console.error('用法: node query.js <命令> --source <sql|powerbi> [参数]');
  console.error('命令: test-connection / schema / query [/ powerbi 专属 list-tools]');
  process.exit(1);
}

(async () => {
  try {
    const { source, rest } = parseGlobalArgs(afterCommand);
    if (source === 'sql') {
      await runSql(command, rest);
    } else {
      throw new Error(`source "${source}" 尚未接入`);
    }
  } catch (err) {
    console.error(err.message);
    process.exitCode = 1;
  }
})();
```

注意：现 `sql-query.js` 里 `parseQueryArgs` 产出的 `options.source` 是 `'inline'|'file'|'stdin'`（查询输入来源），与 dispatcher 的 `--source`（数据源 sql/powerbi）是两个概念，不要混淆。envelope 里的 `source` 字段这里显式传 `'sql'`（原脚本是传查询来源，本计划统一为数据源名）。

- [ ] **Step 4: smoke 验证 test-connection**

Run:
```bash
cd querying-data/scripts && node query.js test-connection --source sql
```
Expected: `{"ok":true,"message":"数据库连接成功"}`

- [ ] **Step 5: smoke 验证 schema**

Run（替换为真实表名）:
```bash
node query.js schema --source sql <schema>.<table>
```
Expected: JSON 数组，含 `{schema, table, columns:[...]}`。

- [ ] **Step 6: smoke 验证 query 三模式**

```bash
# inline
node query.js query --source sql --query "SELECT 1 AS one"
# stdin (heredoc)
node query.js query --source sql --query - <<'EOF'
SELECT 'a$b 中文' AS s;
EOF
# @file
echo 'SELECT 1 AS one;' > /tmp/probe.sql
node query.js query --source sql --query @/tmp/probe.sql
# save
node query.js query --source sql --query "SELECT 1 AS one" --save /tmp/probe.json
```
Expected: 前三条输出 envelope `{source:"sql",row_count:1,columns:[...],rows:[...]}`；第四条额外在 stderr 打印保存路径，`/tmp/probe.json` 存在且为合法 JSON。

- [ ] **Step 7: 验证 stdin 超时保护仍在**

Run（终端直接跑，不喂 stdin，模拟遗漏 --query）:
```bash
node query.js query --source sql --query -
```
Expected: 15s 内报错 `未提供 --query 且 stdin 是终端...`（TTY 分支）。若在非 TTY 管道里且不关闭 stdin，应在 15s 内报 `等待 stdin 超时`。

- [ ] **Step 8: Commit**

```bash
git add querying-data/scripts/lib/sql.js querying-data/scripts/query.js querying-data/references/get_table_schema.sql querying-data/templates/style.sql
git rm -r querying-via-sql/references querying-via-sql/templates 2>/dev/null || true
git commit -m "feat(querying-data): 迁入 SQL 驱动与 dispatcher 的 sql 分支"
```

---

## Task 3: PowerBI 凭证迁移（.env → config.json）

**Files:**
- Modify: `~/.super-data-analytics/config.json`

本任务只做数据迁移，让 PowerBI 凭证就位，供 Task 4 的驱动读取。**先验证再删 `.env`。**

- [ ] **Step 1: 读取现有 .env 现值**

Run:
```bash
cat querying-via-powerbi/.env
```
记录 `POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID` 三个值。

- [ ] **Step 2: 写入 config.json 的 env 块**

编辑 `~/.super-data-analytics/config.json`，在 `env` 块内追加三项（保留已有 HOLOGRES_* 不动）：

```json
{
  "env": {
    "HOLOGRES_HOST": "...", "HOLOGRES_PORT": "...", "HOLOGRES_DATABASE": "...",
    "HOLOGRES_USER": "...", "HOLOGRES_PASSWORD": "...",
    "POWERBI_CLIENT_ID": "<上一步读到的值>",
    "POWERBI_CLIENT_SECRET": "<上一步读到的值>",
    "POWERBI_TENANT_ID": "<上一步读到的值>"
  }
}
```

- [ ] **Step 3: 校验 JSON 合法**

Run:
```bash
node -e "JSON.parse(require('fs').readFileSync(require('os').homedir()+'/.super-data-analytics/config.json','utf-8')); console.log('OK')"
```
Expected: `OK`

- [ ] **Step 4: 暂不删 .env**

`.env` 的删除放到 Task 4 驱动改造并 `test-connection` 通过之后（Task 4 Step 末尾），避免中间状态丢凭证。

- [ ] **Step 5: Commit（config.json 不进仓库，仅记录改动完成）**

config.json 在 `~/.super-data-analytics/`，不属于本仓库，无需 git 提交。本任务无 commit 步骤；执行者在执行日志里记录"三项 POWERBI_* 已写入 config.json"。

---

## Task 4: 迁移 PowerBI 驱动 + dispatcher 的 powerbi 分支

**Files:**
- Create: `querying-data/scripts/lib/powerbi.js`（迁自 `querying-via-powerbi/scripts/powerbi-mcp.js`，含改造）
- Modify: `querying-data/scripts/query.js`（接入 powerbi 分支 + list-tools）
- Delete: `querying-via-powerbi/.env`（验证通过后）

**改造清单（相对原 `powerbi-mcp.js`）：**
1. 删除 `.env` 加载逻辑（文件顶部读 `.env` 的 for 循环）——凭证改由 `lib/sql.js` 同款 `loadConfig` 从 config.json 读。但 `loadConfig` 目前只灌 HOLOGRES_* 的 `CREDENTIAL_KEYS`。**扩展 `loadConfig`** 见 Step 1。
2. 请求输入从 `query --file <json>` 改为 `--query <inline|@file|->`，复用 sql 侧的 `readSqlSource`（语义就是"读一段文本"，对 powerbi 这段文本是 JSON）。
3. 删除 `REQUESTS_DIR`/`cache/`/`isInsideRequestDirectory`/`shouldDeleteRequestFile`/`KEEP_DAX_FILE`/`KEEP_DAX_RESULT` 全部逻辑——不再强制落盘请求文件。
4. `--save` 仅支持 `.json`（原样写 MCP 结果）；csv/xlsx 直接报错指引。
5. `PowerBIClient` 构造校验从 `process.env` 读 `POWERBI_*`（与原一致，因为 `loadConfig` 会把它们灌进 `process.env`）。
6. 新增保底 `artifactId` 回落（Task 5 实现完整；本任务先要求 payload 必须自带 artifactId）。
7. `list-tools` 作为 powerbi 专属子命令。

- [ ] **Step 1: 扩展 sql.js 的 loadConfig，统一灌所有已知凭证键**

Modify `querying-data/scripts/lib/sql.js` 的 `loadConfig`，把 `CREDENTIAL_KEYS` 扩成两个分组并全灌进 `process.env`（这样 sql/powerbi 共用一份配置加载，单一来源）：

```js
const CREDENTIAL_KEYS = [
  'HOLOGRES_HOST', 'HOLOGRES_PORT', 'HOLOGRES_DATABASE', 'HOLOGRES_USER', 'HOLOGRES_PASSWORD',
  'POWERBI_CLIENT_ID', 'POWERBI_CLIENT_SECRET', 'POWERBI_TENANT_ID',
];
```

并把 `loadConfig` 导出（Task 2 已导出）。`loadConfig` 缺文件/缺键的错误提示文案保持 SQL 风格（指引 agent 补全）。注意：`loadConfig` 目前**不校验**键是否齐全（只灌存在的），齐全性校验由各 `Client` 构造函数负责——这个分工保留。

- [ ] **Step 2: 创建 lib/powerbi.js（导出函数，去 CLI 入口）**

Create `querying-data/scripts/lib/powerbi.js`，从 `querying-via-powerbi/scripts/powerbi-mcp.js` 迁入，做如下改动：

(a) **删除**文件顶部 `.env` 加载的 for 循环（`// 从 scripts/ 和上级...` 到对应 `}` 整段）。凭证由 dispatcher 调 `loadConfig()` 灌入 `process.env`，`PowerBIClient` 构造函数照旧从 `process.env` 读 `POWERBI_*`（不改）。

(b) **删除** `parseQueryArgs`（旧版解析 `--file`）、`readQueryRequestFile`、`isInsideRequestDirectory`、`shouldDeleteRequestFile`、`REQUESTS_DIR`、`POLL_*` 之外的 `cache` 相关常量。保留 `PowerBIClient`、`MCP_URL`、`SCOPE`、`POLL_TIMEOUT_MS`、`POLL_INTERVAL_MS` 与 `_getToken/_mcpCall/_parseResponse/listTools/getSchema/query/_validateArtifactId` 全部方法。

(c) 新增一个**解析 JSON 请求文本**的函数（输入是 `--query` 读到的一段文本，输出 `{artifactId,maxRows,daxQueries}`）：

```js
export function parseDaxPayload(text) {
  let request;
  try {
    request = JSON.parse(text.replace(/^﻿/, '').trim());
  } catch (e) {
    throw new Error(`PowerBI --query 载荷不是合法 JSON: ${e.message}`);
  }
  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    throw new Error('PowerBI 载荷必须是 JSON 对象: { "artifactId": "...", "daxQueries": ["EVALUATE ..."] }');
  }
  const { artifactId, daxQueries, maxRows = 250 } = request;
  if (typeof artifactId !== 'string' || !artifactId.trim()) {
    throw new Error('PowerBI 载荷缺少 artifactId 字符串');
  }
  if (!Array.isArray(daxQueries) || daxQueries.length === 0 || daxQueries.length > 4) {
    throw new Error('daxQueries 必须是 1 到 4 条 DAX 的数组');
  }
  const normalizedQueries = daxQueries.map((q, i) => {
    if (typeof q !== 'string' || !q.trim()) throw new Error(`daxQueries[${i}] 必须是非空字符串`);
    return q;
  });
  if (!Number.isInteger(maxRows) || maxRows < 1 || maxRows > 1000) {
    throw new Error('maxRows 必须是 1 到 1000 之间的整数');
  }
  return { artifactId, maxRows, daxQueries: normalizedQueries };
}

export async function savePowerBiResult(json, savePath) {
  const ext = savePath.slice(savePath.lastIndexOf('.')).toLowerCase();
  if (ext !== '.json') {
    throw new Error(`PowerBI --save 仅支持 .json（原始 MCP 结果）；收到 ${ext}。csv/xlsx 暂不支持`);
  }
  const { mkdirSync, writeFileSync } = await import('node:fs');
  const { dirname } = await import('node:path');
  mkdirSync(dirname(savePath), { recursive: true });
  writeFileSync(savePath, typeof json === 'string' ? json : JSON.stringify(json, null, 2), 'utf-8');
}
```

（`PowerBIClient` 顶部原有 `import { existsSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs'` 等可精简为实际还用到的；`writeFileSync` 在 `savePowerBiResult` 内动态 import 即可，避免顶部冗余。）

(d) 文件末尾**删除** CLI 入口 IIFE，改为导出：

```js
export { PowerBIClient, MCP_URL, SCOPE };
```
（`parseDaxPayload`、`savePowerBiResult` 已在定义处 export。）

- [ ] **Step 3: 在 query.js 接入 powerbi 分支与 list-tools**

Modify `querying-data/scripts/query.js`：

(a) 顶部加 import：
```js
import { PowerBIClient, parseDaxPayload, savePowerBiResult } from './lib/powerbi.js';
import { readSqlSource, parseQueryArgs as parseSqlQueryArgs, resolveQueryOptions } from './lib/sql.js';
```
（`readSqlSource`/`parseQueryArgs` 复用——对 powerbi，"查询来源三模式"与 sql 完全同构，只是读到的文本是 JSON。）

(b) `SOURCES` 加 `powerbi`：
```js
const SOURCES = new Set(['sql', 'powerbi']);
```

(c) 加 `runPowerBi`：

```js
async function runPowerBi(command, cliArgs) {
  const client = new PowerBIClient();
  switch (command) {
    case 'list-tools': {
      console.log(JSON.stringify(await client.listTools(), null, 2));
      break;
    }
    case 'test-connection': {
      // 复用 list-tools 作为连通性 + 鉴权探针
      const tools = await client.listTools();
      console.log(JSON.stringify({ ok: true, message: 'PowerBI MCP 连接成功', tool_count: tools.length }, null, 2));
      break;
    }
    case 'schema': {
      const [artifactId] = cliArgs;
      if (!artifactId) throw new Error('用法: query.js schema --source powerbi <artifactId>');
      console.log(JSON.stringify(await client.getSchema(artifactId), null, 2));
      break;
    }
    case 'query': {
      const options = resolveQueryOptions(parseSqlQueryArgs(cliArgs));
      if (options.source === 'stdin' && process.stdin.isTTY) {
        throw new Error('未提供 --query 且 stdin 是终端。请用 --query <JSON>、--query @<文件> 或管道传入');
      }
      const text = await readSqlSource(options);
      const { artifactId, maxRows, daxQueries } = parseDaxPayload(text);
      const result = await client.query(artifactId, daxQueries, maxRows);
      const output = JSON.stringify(result, null, 2);
      if (options.savePath) {
        await savePowerBiResult(result, options.savePath);
        console.error(`结果已保存到: ${options.savePath}`);
      }
      console.log(output);
      break;
    }
    default:
      throw new Error(`powerbi 未知命令: ${command}（支持：list-tools / test-connection / schema / query）`);
  }
}
```

(d) 在 dispatcher 的 `(async () => {})()` 里加分支：
```js
if (source === 'sql') {
  await runSql(command, rest);
} else if (source === 'powerbi') {
  await runPowerBi(command, rest);
} else {
  throw new Error(`source "${source}" 尚未接入`);
}
```

(e) **dispatcher 顶部统一调一次 `loadConfig()`**：把现 `runSql` 内的 `loadConfig()` 调用上提到 dispatcher 主入口（sql/powerbi 共用），`runSql` 内删掉那行：

```js
(async () => {
  try {
    loadConfig();               // 统一加载 config.json → process.env
    const { source, rest } = parseGlobalArgs(afterCommand);
    if (source === 'sql') await runSql(command, rest);
    else if (source === 'powerbi') await runPowerBi(command, rest);
    else throw new Error(`source "${source}" 尚未接入`);
  } catch (err) {
    console.error(err.message);
    process.exitCode = 1;
  }
})();
```
（`runSql` 里删除 `loadConfig();` 那一行。）

- [ ] **Step 4: smoke 验证 powerbi list-tools**

Run:
```bash
cd querying-data/scripts && node query.js list-tools --source powerbi
```
Expected: JSON 数组，列出 PowerBI MCP 可用工具（含 `GetSemanticModelSchema`、`ExecuteQuery`）。若报 401/403，回查 config.json 的 `POWERBI_*` 与 admin consent。

- [ ] **Step 5: smoke 验证 test-connection**

Run:
```bash
node query.js test-connection --source powerbi
```
Expected: `{"ok":true,"message":"PowerBI MCP 连接成功","tool_count":<N>}`

- [ ] **Step 6: smoke 验证 query（stdin 喂 JSON，保底前：payload 自带 artifactId）**

Run（artifactId 用 Task 5 之前已知的真实 GUID，即原 `semantic-model-ids.json` 里的默认模型 `c85590e6-770f-411f-a716-10d0147ad68b`）：
```bash
node query.js query --source powerbi --query - <<'EOF'
{"artifactId":"c85590e6-770f-411f-a716-10d0147ad68b","maxRows":10,"daxQueries":["EVALUATE ROW(\"probe\", 1)"]}
EOF
```
Expected: 原始 MCP JSON 结果输出到 stdout。

- [ ] **Step 7: smoke 验证 --save 仅 json + 拒绝非 json**

```bash
# json 保存
node query.js query --source powerbi --query - --save /tmp/pb.json <<'EOF'
{"artifactId":"c85590e6-770f-411f-a716-10d0147ad68b","daxQueries":["EVALUATE ROW(\"probe\", 1)"]}
EOF
# csv 应被拒绝
node query.js query --source powerbi --query - --save /tmp/pb.csv <<'EOF'
{"artifactId":"c85590e6-770f-411f-a716-10d0147ad68b","daxQueries":["EVALUATE ROW(\"probe\", 1)"]}
EOF
```
Expected: 第一条 `/tmp/pb.json` 生成、stderr 打印保存路径；第二条报错 `PowerBI --save 仅支持 .json ... csv/xlsx 暂不支持`。

- [ ] **Step 8: 删除 .env（凭证已迁完且验证通过）**

```bash
git rm querying-via-powerbi/.env
```
（`.env` 是否被 git 跟踪需确认；若已被 `.gitignore` 忽略则改用 `rm`，不进 git。）

- [ ] **Step 9: Commit**

```bash
git add querying-data/scripts/lib/powerbi.js querying-data/scripts/lib/sql.js querying-data/scripts/query.js
git commit -m "feat(querying-data): 迁入 PowerBI 驱动，--query 三模式 + --save 仅 json，凭证改读 config.json"
```

---

## Task 5: powerbi-semantic-models 并入 config.json + 保底回落

**Files:**
- Modify: `~/.super-data-analytics/config.json`（加 `powerbi-semantic-models` 键）
- Modify: `querying-data/scripts/lib/powerbi.js`（实现保底回落）
- Delete: `querying-via-powerbi/semantic-model-ids.json`

**保底语义（spec 第 5 节）：** payload 带 artifactId → 直接用；没带 → 读 config.json `powerbi-semantic-models`，取 `is_default:true` 或按 `name` 匹配。

- [ ] **Step 1: 把三条模型记录写入 config.json**

读 `querying-via-powerbi/semantic-model-ids.json`（已知三条），补全 `description`，写入 `~/.super-data-analytics/config.json`：

```json
{
  "env": { "...": "..." },
  "powerbi-semantic-models": [
    { "id": "c85590e6-770f-411f-a716-10d0147ad68b", "name": "平台治理经营看板", "is_default": true,  "description": "平台治理主线经营指标" },
    { "id": "3041d238-c8dc-4b8d-aff7-8c262c631b6c", "name": "超级VIP经营看板",  "is_default": false, "description": "超级VIP经营指标" },
    { "id": "05a31944-8f4a-49d3-8168-62ce49da936d", "name": "私域Agent项目",    "is_default": false, "description": "私域 Agent 项目指标" }
  ]
}
```

`description` 文案由执行者按业务实际补，三条都不能缺。

- [ ] **Step 2: 校验 JSON**

```bash
node -e "JSON.parse(require('fs').readFileSync(require('os').homedir()+'/.super-data-analytics/config.json','utf-8')); console.log('OK')"
```
Expected: `OK`

- [ ] **Step 3: 在 lib/powerbi.js 实现保底回落**

新增读取函数（config.json 与 sql 侧 `CONFIG_PATH` 同路径，复用 `os.homedir()`）：

```js
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const CONFIG_PATH = join(homedir(), '.super-data-analytics', 'config.json');

export function resolveArtifactId(payload) {
  // 1) payload 自带 → 直接用（正常路径）
  if (payload.artifactId && typeof payload.artifactId === 'string' && payload.artifactId.trim()) {
    return payload.artifactId;
  }
  // 2) 没带 → 读 config.json powerbi-semantic-models（保底）
  let cfg;
  try {
    cfg = JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
  } catch (e) {
    throw new Error(`保底回落失败：payload 未带 artifactId 且无法读取 ${CONFIG_PATH}: ${e.message}`);
  }
  const models = Array.isArray(cfg['powerbi-semantic-models']) ? cfg['powerbi-semantic-models'] : [];
  if (models.length === 0) {
    throw new Error('payload 未带 artifactId，且 config.json 未配置 powerbi-semantic-models');
  }
  const byName = payload.model && models.find(m => m.name === payload.model);
  const picked = byName || models.find(m => m.is_default) || models[0];
  if (!picked || !picked.id) {
    throw new Error('payload 未带 artifactId，且 config.json 的 powerbi-semantic-models 无可用条目');
  }
  return picked.id;
}
```

并把 `parseDaxPayload` 中对 artifactId 的强校验放宽：artifactId 可缺（交给 `resolveArtifactId` 保底），但 `payload.model`（可选字符串，用于按名回落）允许出现。改 `parseDaxPayload` 的 artifactId 校验段：

```js
const { artifactId, daxQueries, maxRows = 250, model } = request;
// artifactId 不再强制存在；由 resolveArtifactId 保底
const normalizedQueries = ...; // 不变
if (!Number.isInteger(maxRows) || maxRows < 1 || maxRows > 1000) { ... } // 不变
return { artifactId, maxRows, daxQueries: normalizedQueries, model };
```

- [ ] **Step 4: query.js 调用保底回落**

Modify `querying-data/scripts/query.js` 的 `runPowerBi` query 分支：

```js
import { PowerBIClient, parseDaxPayload, savePowerBiResult, resolveArtifactId } from './lib/powerbi.js';
...
case 'query': {
  const options = resolveQueryOptions(parseSqlQueryArgs(cliArgs));
  if (options.source === 'stdin' && process.stdin.isTTY) { ... } // 不变
  const text = await readSqlSource(options);
  const payload = parseDaxPayload(text);
  const artifactId = resolveArtifactId(payload);   // 保底回落
  const result = await client.query(artifactId, payload.daxQueries, payload.maxRows);
  ...
}
```

- [ ] **Step 5: smoke 验证保底回落（payload 不带 artifactId）**

Run:
```bash
cd querying-data/scripts && node query.js query --source powerbi --query - <<'EOF'
{"daxQueries":["EVALUATE ROW(\"probe\", 1)"]}
EOF
```
Expected: 命中 config.json 里 `is_default:true` 的模型，正常返回 MCP 结果（与 Task 4 Step 6 等价）。

- [ ] **Step 6: smoke 验证按 name 回落**

Run:
```bash
node query.js query --source powerbi --query - <<'EOF'
{"model":"超级VIP经营看板","daxQueries":["EVALUATE ROW(\"probe\", 1)"]}
EOF
```
Expected: 命中"超级VIP经营看板"模型，正常返回。

- [ ] **Step 7: 删除原 semantic-model-ids.json**

```bash
git rm querying-via-powerbi/semantic-model-ids.json
```

- [ ] **Step 8: Commit**

```bash
git add querying-data/scripts/lib/powerbi.js querying-data/scripts/query.js
git commit -m "feat(querying-data): powerbi-semantic-models 并入 config.json 作 artifactId 保底回落"
```

---

## Task 6: 写 references/sql.md 与 references/powerbi.md

**Files:**
- Create: `querying-data/references/sql.md`
- Create: `querying-data/references/powerbi.md`

这两个文件是 agent 被路由后阅读的"该源怎么用"。从原两个 SKILL.md 抽取/改写，去掉过时内容（PowerBI 的"schema 缓存 24h"虚假承诺**不写进来**）。

- [ ] **Step 1: 写 references/sql.md**

内容要点（照搬现 `querying-via-sql/SKILL.md` 的 CLI、路由表、stdin/heredoc/PowerShell 示例、保存约定，把脚本路径改成 `querying-data/scripts/query.js ... --source sql`）：

```markdown
# SQL 数据源（Hologres / PostgreSQL）

经 `query.js --source sql` 直连 Hologres/PostgreSQL。凭证来自 `~/.super-data-analytics/config.json` 的 env 块。

## CLI

\`\`\`bash
node scripts/query.js test-connection --source sql
node scripts/query.js schema --source sql <schema.table> [schema.table ...]
node scripts/query.js query --source sql --query "<SQL>" [--save <path>]
node scripts/query.js query --source sql --query @<file-path> [--save <path>]
node scripts/query.js query --source sql --query -              [--save <path>]
\`\`\`

## --query 三来源路由
（搬原 SKILL.md 的"Agent 路由"表：进程API→spawn stdin / bash→quoted heredoc / PowerShell→单引号 here-string + UTF-8 / 审阅复跑→@文件 / 简短→inline；含 $ 或反引号不建议 inline）

## 输出
stdout: \`{source,row_count,columns,rows,[result_path?]}\`

## --save
传 --save 才落盘，默认只 stdout。支持 .json / .csv / .xlsx。目录 <工作区>/.super-data-analytics/results/，命名由 agent 决定。

## schema
调用方需提前给表名。返回 \`[{schema,table,columns:[...]}]\`。
```

（执行者把原 SKILL.md 里的 bash/PowerShell/JSM 代码示例原样搬入，仅改命令前缀。）

- [ ] **Step 2: 写 references/powerbi.md**

内容要点（搬现 `querying-via-powerbi/SKILL.md` 的 Phase 流程、DAX 函数参考全表；改造请求输入与保存段落）：

```markdown
# PowerBI 数据源（语义模型 / MCP）

经 `query.js --source powerbi` 调微软 Fabric MCP 端点，Client Credentials 认证。凭证来自 config.json 的 env 块（POWERBI_*）。

## CLI

\`\`\`bash
node scripts/query.js list-tools       --source powerbi
node scripts/query.js test-connection  --source powerbi
node scripts/query.js schema           --source powerbi <artifactId>
node scripts/query.js query            --source powerbi --query <JSON> [--save <path>]
node scripts/query.js query            --source powerbi --query @<request.json>
node scripts/query.js query            --source powerbi --query -
\`\`\`

## --query 载荷 = JSON 请求
载荷是 JSON 文本（不是单条 DAX），三来源与 sql 同构（inline / @file / stdin）。
**偏好**：inline JSON 在 shell 里引号/换行转义很丑，实际以 @file 与 stdin/heredoc 为主，inline 仅极短请求。

载荷格式：
\`\`\`json
{ "artifactId": "...", "maxRows": 250, "daxQueries": ["EVALUATE ..."] }
\`\`\`
- daxQueries：1~4 条 DAX
- maxRows：默认 250，最大 1000

## artifactId 保底规则（重要）
1. payload 带 artifactId → 直接用（正常路径，优先）
2. 没带 → 脚本回落 config.json 的 powerbi-semantic-models：可带 "model":"<name>" 按名匹配，否则取 is_default:true
能从上游拿到 artifactId 就别读 config；config 是保底。

## 输出与 --save
stdout：原始 MCP JSON（不归一，预览期形状会变）。
--save：仅支持 .json（原样落盘）。csv/xlsx 不支持。

## DAX 编写清单 + 函数参考
（搬原 SKILL.md 的 4 步检查清单 + 函数策略 + 板块表格 + 微软官方链接，原样保留）
```

- [ ] **Step 3: Commit**

```bash
git add querying-data/references/sql.md querying-data/references/powerbi.md
git commit -m "docs(querying-data): references/sql.md 与 powerbi.md（per-source CLI 与 payload 约定）"
```

---

## Task 7: 写入口路由 SKILL.md

**Files:**
- Create: `querying-data/SKILL.md`

入口 SKILL.md 只做路由：识别数据源 → 指向 references/<source>.md。

- [ ] **Step 1: 写 SKILL.md**

Create `querying-data/SKILL.md`:

```markdown
---
name: querying-data
description: 统一数据查询入口，按 --source（sql / powerbi）路由到对应驱动；支持 inline / @file / stdin 三种查询输入
metadata:
  skill-series: super-data-analytics
  chinese-name: 查询数据
---

# 查询数据

统一入口查询 Hologres/PostgreSQL（sql）或 PowerBI 语义模型（powerbi）。\`--source\` 切换底层驱动，\`--query\` 承载查询载荷（三来源：inline / @文件 / stdin），凭证统一来自 \`~/.super-data-analytics/config.json\`。

## 第一步：识别数据源

收到查询请求，先判断 \`--source\`：

| 信号 | source |
|---|---|
| 提到语义模型 / 度量值 / DAX / PowerBI / 报表 / 看板 | powerbi |
| 提到 Hologres / 表 / SQL / 字段 / schema | sql |
| 模糊 | 问用户，或调 retrieving-business-context 查指标定义与数据源归属 |

## 第二步：读对应源的用法

数据源的 CLI、payload 格式、编写规范各不相同，**先读对应 references 再动手**：

- sql → [references/sql.md](references/sql.md)
- powerbi → [references/powerbi.md](references/powerbi.md)

## 通用约定（两源一致）

- \`--query\` 三来源：inline / @文件 / -（stdin）
- \`--save <path>\` 仅在需要落盘时传，默认只 stdout
- 保存目录 \`<工作区>/.super-data-analytics/results/\`，命名由 agent 决定
- 凭证缺失时脚本报错并指引补全 \`~/.super-data-analytics/config.json\`
```

- [ ] **Step 2: Commit**

```bash
git add querying-data/SKILL.md
git commit -m "docs(querying-data): 入口路由 SKILL.md，识别数据源指向 references"
```

---

## Task 8: 清理旧目录 + 更新根文档

**Files:**
- Delete: `querying-via-sql/`（剩余文件：SKILL.md, README.md, scripts/, .super-data-analytics/ 探针文件）
- Delete: `querying-via-powerbi/`（剩余文件：SKILL.md, README.md, scripts/, cache/）
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

**前置确认：** Task 2–7 全部 smoke 通过后，旧目录才可删。

- [ ] **Step 1: 确认新 skill 端到端可用**

Re-run（双源各一条 query）：
```bash
cd querying-data/scripts
node query.js query --source sql --query "SELECT 1 AS one"
node query.js query --source powerbi --query - <<'EOF'
{"daxQueries":["EVALUATE ROW(\"probe\", 1)"]}
EOF
```
Expected: 两条都正常返回结果（powerbi 走保底默认模型）。失败则**不得**删除旧目录，回到对应 Task 修复。

- [ ] **Step 2: 删除旧 skill 目录**

```bash
git rm -r querying-via-sql querying-via-powerbi
```

- [ ] **Step 3: 更新根 CLAUDE.md 的架构块与触发路由**

Modify `CLAUDE.md`：

(a) 架构块里把
```
querying-data-via-powerbi/      经由 BI 提取（已实现）
querying-via-sql/          经由数据库查询（已实现）
```
两行合并为一行：
```
querying-data/             统一数据查询（sql / powerbi，已实现）
```

(b) 触发路由段里所有 \`querying-via-sql\` / \`querying-data-via-powerbi\` / \`querying-via-powerbi\` 字样改为 \`querying-data\`；"直连路径""对齐路径""完整路径"里提到"同时用 Power BI 和 SQL"的措辞保留语义但引用名换成 \`querying-data --source ...\`。

(c) "DAX 编写"那条注意事项里 `querying-data-via-powerbi/references/` 改为 `querying-data/references/powerbi.md`。

- [ ] **Step 4: 更新 AGENTS.md 同步**

对 `AGENTS.md` 做同样的板块名/路径替换（grep 出所有 `querying-via-sql`、`querying-via-powerbi`、`querying-data-via-powerbi`，逐处替换为 `querying-data`）。

Run 校验无残留：
```bash
grep -nE 'querying-via-sql|querying-via-powerbi|querying-data-via-powerbi' CLAUDE.md AGENTS.md
```
Expected: 无输出（全部已替换）。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 删除旧 querying-via-sql / querying-via-powerbi，根文档指向 querying-data"
```

---

## Self-Review 结论

**Spec 覆盖：**
- 统一 CLI 契约（test-connection/schema/query + powerbi 专属 list-tools）→ Task 2/4 ✓
- `--query` 三模式两源一致 → Task 2 (sql) + Task 4 (powerbi) ✓
- SQL 零改动、monkey-patch 保留 → Task 2 ✓
- stdout 各源原生、不归一 → Task 2/4（envelope 仅 sql 归一，powerbi 原样）✓
- `--save` sql=三格式 / powerbi=仅 json → Task 2 (sql saveResult 不动) + Task 4 (savePowerBiResult) ✓
- config.json 统一凭证 + powerbi-semantic-models 保底 → Task 3 + Task 5 ✓
- 删除 cache/KEEP_DAX/请求文件强制落盘 → Task 4 ✓
- 删除 schema 24h 虚假承诺 → Task 6（不写入 references）✓
- references + 路由 SKILL.md → Task 6 + Task 7 ✓
- 清旧目录 + 根文档 → Task 8 ✓

**类型/命名一致性：** `parseSqlQueryArgs`（dispatcher 里 alias 自 sql 的 `parseQueryArgs`）、`parseDaxPayload`、`resolveArtifactId`、`savePowerBiResult`、`readSqlSource`、`resolveQueryOptions` 在各 Task 间引用一致；`loadConfig` 上提到 dispatcher 主入口，sql/powerbi 共用。已核对。

**残留风险：** Task 3/5 改的是 `~/.super-data-analytics/config.json`（仓库外文件），执行者需有写权限与线上访问权限；smoke 步骤依赖真实 Hologres 与 PowerBI 端点可用。
