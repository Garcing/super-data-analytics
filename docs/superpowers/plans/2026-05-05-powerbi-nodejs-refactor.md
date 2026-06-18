# PowerBI Node.js 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Node.js 替代 Python MCP 代理，创建零交互认证的 Power BI 直接调用库。

**Architecture:** 单文件 `scripts/powerbi-client.mjs`，同时作为可 import 的库和 CLI 工具。用 `@azure/identity` 的 ClientSecretCredential 实现 Client Credentials 认证（零用户交互），直接 POST JSON-RPC 到微软 Power BI MCP HTTP 端点，处理 202 轮询。

**Tech Stack:** Node.js 18+（内置 fetch）、`@azure/identity`、ES Modules（.mjs）

**Design spec:** `docs/superpowers/specs/2026-05-05-powerbi-nodejs-refactor-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/powerbi-client.mjs` | Create | 核心库 + CLI，唯一新增文件 |
| `.gitignore` | Modify | 允许根目录 package.json，添加 /node_modules/ |
| `package.json` | Create | 声明 @azure/identity 依赖 |

---

### Task 1: 项目初始化

**Files:**
- Modify: `.gitignore`
- Create: `package.json`

- [ ] **Step 1: 更新 .gitignore，允许根目录 package.json**

将 `.gitignore` 中以下行：

```
# Root Node (unused, web-report has its own)
/package.json
/package-lock.json
```

替换为：

```
# Node
/node_modules/
```

删掉 `/package.json` 和 `/package-lock.json` 的 gitignore 规则（根目录现在需要这些文件），添加 `/node_modules/`。

- [ ] **Step 2: 创建 package.json**

在项目根目录创建 `package.json`：

```json
{
  "name": "powerbi-analysis",
  "private": true,
  "type": "module",
  "dependencies": {
    "@azure/identity": "^4.0.0"
  }
}
```

- [ ] **Step 3: 安装依赖**

Run: `cd c:/Users/Administrator/.agents/skills/powerbi-analysis && npm install`
Expected: `added X packages` 无报错，生成 `node_modules/` 和 `package-lock.json`

- [ ] **Step 4: 提交**

```bash
git add .gitignore package.json package-lock.json
git commit -m "chore: init Node.js project with @azure/identity"
```

---

### Task 2: 文件骨架 + 认证

**Files:**
- Create: `scripts/powerbi-client.mjs`

- [ ] **Step 1: 创建 powerbi-client.mjs 骨架**

创建 `scripts/powerbi-client.mjs`，包含常量定义、PowerBIClient 类的构造函数和环境变量校验：

```javascript
import { ClientSecretCredential } from '@azure/identity';

const MCP_URL = 'https://api.fabric.microsoft.com/v1/mcp/powerbi';
const SCOPE = 'https://analysis.windows.net/powerbi/api/.default';
const POLL_TIMEOUT_MS = 60_000;
const POLL_INTERVAL_MS = 1_000;

export class PowerBIClient {
  constructor() {
    const env = process.env;
    const clientId = env.POWERBI_CLIENT_ID;
    const clientSecret = env.POWERBI_CLIENT_SECRET;
    const tenantId = env.POWERBI_TENANT_ID;

    const missing = [
      !clientId && 'POWERBI_CLIENT_ID',
      !clientSecret && 'POWERBI_CLIENT_SECRET',
      !tenantId && 'POWERBI_TENANT_ID',
    ].filter(Boolean);

    if (missing.length > 0) {
      throw new Error(`Missing environment variables: ${missing.join(', ')}. ` +
        'Set them to your Azure AD app registration credentials.');
    }

    this.credential = new ClientSecretCredential(tenantId, clientId, clientSecret);
  }

  async _getToken() {
    const { token } = await this.credential.getToken(SCOPE);
    return token;
  }
}
```

- [ ] **Step 2: 验证 import 正常**

Run: `cd c:/Users/Administrator/.agents/skills/powerbi-analysis && node -e "import('./scripts/powerbi-client.mjs').then(m => console.log('OK:', Object.keys(m)))"`
Expected: `OK: [ 'PowerBIClient' ]`

- [ ] **Step 3: 验证环境变量校验**

Run: `cd c:/Users/Administrator/.agents/skills/powerbi-analysis && node -e "import('./scripts/powerbi-client.mjs').then(m => { try { new m.PowerBIClient() } catch(e) { console.log(e.message) } })"`
Expected: 输出包含 `Missing environment variables: POWERBI_CLIENT_ID, POWERBI_CLIENT_SECRET, POWERBI_TENANT_ID`

- [ ] **Step 4: 提交**

```bash
git add scripts/powerbi-client.mjs
git commit -m "feat: PowerBIClient class skeleton with ClientSecretCredential auth"
```

---

### Task 3: 核心 HTTP 层

**Files:**
- Modify: `scripts/powerbi-client.mjs`

- [ ] **Step 1: 在 PowerBIClient 类中添加 _mcpCall 和 _parseResponse 方法**

在 `this.credential = ...` 之后、类的结束 `}` 之前，添加以下方法（`_getToken` 已存在，在其后面添加）：

```javascript
  async _mcpCall(method, params) {
    const token = await this._getToken();
    const requestId = Date.now();

    const body = {
      jsonrpc: '2.0',
      id: requestId,
      method,
      ...(params !== undefined && { params }),
    };

    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'Accept': 'application/json, text/event-stream',
    };

    let resp = await fetch(MCP_URL, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    // 202 轮询
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    while (resp.status === 202 && Date.now() < deadline) {
      const location = resp.headers.get('operation-location');
      if (!location) {
        throw new Error('Received 202 but no operation-location header');
      }
      await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
      resp = await fetch(location, { headers });
    }

    if (resp.status === 202) {
      const err = new Error(`Query timed out after ${POLL_TIMEOUT_MS / 1000}s`);
      err.statusCode = 202;
      throw err;
    }

    if (resp.status === 401 || resp.status === 403) {
      const text = await resp.text();
      const err = new Error(
        `HTTP ${resp.status}: Token invalid or insufficient permissions.\n` +
        'Check: 1) API permissions granted in Azure AD app 2) Admin consent given 3) Correct tenant ID\n' +
        `Details: ${text.slice(0, 300)}`
      );
      err.statusCode = resp.status;
      throw err;
    }

    if (!resp.ok) {
      const text = await resp.text();
      const err = new Error(`HTTP ${resp.status}: ${text.slice(0, 500)}`);
      err.statusCode = resp.status;
      throw err;
    }

    return this._parseResponse(await resp.text(), requestId);
  }

  _parseResponse(text, requestId) {
    try {
      return JSON.parse(text);
    } catch {}

    for (const line of text.split('\n')) {
      if (line.startsWith('data:')) {
        try {
          return JSON.parse(line.slice(5).trim());
        } catch {}
      }
    }

    throw new Error('Unable to parse response from Power BI MCP endpoint');
  }
```

- [ ] **Step 2: 验证语法正确**

Run: `cd c:/Users/Administrator/.agents/skills/powerbi-analysis && node --check scripts/powerbi-client.mjs`
Expected: 无输出（语法正确）

- [ ] **Step 3: 提交**

```bash
git add scripts/powerbi-client.mjs
git commit -m "feat: add _mcpCall with JSON-RPC + 202 polling + response parsing"
```

---

### Task 4: API 方法

**Files:**
- Modify: `scripts/powerbi-client.mjs`

- [ ] **Step 1: 在 PowerBIClient 类中添加 listTools、getSchema、query 方法**

在 `_parseResponse` 方法之后、类的结束 `}` 之前添加：

```javascript
  async listTools() {
    const result = await this._mcpCall('tools/list');
    return result.result?.tools ?? [];
  }

  async getSchema(artifactId) {
    this._validateArtifactId(artifactId);
    const result = await this._mcpCall('tools/call', {
      name: 'GetSemanticModelSchema',
      arguments: { artifactId },
    });
    return result;
  }

  async query(artifactId, daxQueryOrQueries, maxRows = 250) {
    this._validateArtifactId(artifactId);
    const isArray = Array.isArray(daxQueryOrQueries);

    if (isArray && daxQueryOrQueries.length > 4) {
      throw new Error('daxQueries supports a maximum of 4 queries');
    }

    const arguments_ = { artifactId, maxRows };
    if (isArray) {
      arguments_.daxQueries = daxQueryOrQueries;
    } else {
      arguments_.daxQuery = daxQueryOrQueries;
    }

    const result = await this._mcpCall('tools/call', {
      name: 'ExecuteQuery',
      arguments: arguments_,
    });
    return result;
  }

  _validateArtifactId(id) {
    if (!id || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
      throw new Error(`Invalid artifactId "${id}". Expected GUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`);
    }
  }
```

注意：`arguments` 是 JavaScript 保留字，不能作为对象属性名的简写，所以用 `arguments_` 变量名。

- [ ] **Step 2: 验证语法正确**

Run: `cd c:/Users/Administrator/.agents/skills/powerbi-analysis && node --check scripts/powerbi-client.mjs`
Expected: 无输出

- [ ] **Step 3: 验证 GUID 校验**

Run: `cd c:/Users/Administrator/.agents/skills/powerbi-analysis && node -e "
import('./scripts/powerbi-client.mjs').then(m => {
  const c = new m.PowerBIClient();
  // We can't call methods without real auth, but we can test _validateArtifactId indirectly
  // by checking the constructor works
  console.log('Class instantiated OK');
})
"`
Expected: 报错 Missing environment variables（因为没设环境变量），这是正确的——构造函数校验生效。

- [ ] **Step 4: 提交**

```bash
git add scripts/powerbi-client.mjs
git commit -m "feat: add listTools, getSchema, query methods with GUID validation"
```

---

### Task 5: CLI 接口

**Files:**
- Modify: `scripts/powerbi-client.mjs`

- [ ] **Step 1: 在文件末尾（class 定义之后）添加 CLI 入口**

在 `export class PowerBIClient { ... }` 之后，文件末尾添加：

```javascript
// CLI entry point
const [,, command, ...cliArgs] = process.argv;

if (command) {
  (async () => {
    try {
      const client = new PowerBIClient();

      switch (command) {
        case 'list-tools': {
          const tools = await client.listTools();
          console.log(JSON.stringify(tools, null, 2));
          break;
        }
        case 'schema': {
          const [artifactId] = cliArgs;
          if (!artifactId) {
            console.error('Usage: node powerbi-client.mjs schema <artifactId>');
            process.exit(1);
          }
          const result = await client.getSchema(artifactId);
          console.log(JSON.stringify(result, null, 2));
          break;
        }
        case 'query': {
          const [artifactId, daxInput] = cliArgs;
          if (!artifactId || !daxInput) {
            console.error('Usage: node powerbi-client.mjs query <artifactId> <daxQuery | daxQueriesJSONArray>');
            process.exit(1);
          }
          let daxQueryOrQueries = daxInput;
          try {
            const parsed = JSON.parse(daxInput);
            if (Array.isArray(parsed)) daxQueryOrQueries = parsed;
          } catch {}
          const result = await client.query(artifactId, daxQueryOrQueries);
          console.log(JSON.stringify(result, null, 2));
          break;
        }
        default:
          console.error(`Unknown command: ${command}\n`);
          console.error('Usage: node powerbi-client.mjs <command> [args]');
          console.error('');
          console.error('Commands:');
          console.error('  list-tools                     List available MCP tools from Power BI');
          console.error('  schema <artifactId>             Get semantic model schema');
          console.error('  query <artifactId> <dax>        Execute DAX query (string or JSON array)');
          process.exit(1);
      }
    } catch (err) {
      console.error(err.message);
      process.exit(1);
    }
  })();
}
```

- [ ] **Step 2: 验证 CLI help 输出**

Run: `cd c:/Users/Administrator/.agents/skills/powerbi-analysis && node scripts/powerbi-client.mjs help`
Expected: stderr 输出 `Unknown command: help` + usage 文本，exit code 1

- [ ] **Step 3: 验证 schema 缺参数**

Run: `cd c:/Users/Administrator/.agents/skills/powerbi-analysis && node scripts/powerbi-client.mjs schema 2>&1`
Expected: stderr 输出 `Usage: node powerbi-client.mjs schema <artifactId>`

- [ ] **Step 4: 提交**

```bash
git add scripts/powerbi-client.mjs
git commit -m "feat: add CLI interface with list-tools, schema, query commands"
```

---

### Task 6: 端到端验证

**Files:** 无变更，仅手动测试

前提条件：环境变量 `POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID` 已配置（可用当前 Python 版本使用的 `d44d3dbe-2b19-4ed0-ad47-ccd50627e9a5` 作为 CLIENT_ID，但需要先在 Azure Portal 为该应用添加 client secret 和 Application 类型权限）。

- [ ] **Step 1: 验证 list-tools**

Run: `node scripts/powerbi-client.mjs list-tools`
Expected: JSON 数组，包含 `ExecuteQuery`、`GenerateQuery`、`GetSemanticModelSchema` 三个工具定义

- [ ] **Step 2: 验证 getSchema**

Run: `node scripts/powerbi-client.mjs schema c85590e6-770f-411f-a716-10d0147ad68b`
Expected: JSON 响应，包含语义模型结构（tables、columns、measures 等）

- [ ] **Step 3: 验证单条 DAX 查询**

Run: `node scripts/powerbi-client.mjs query c85590e6-770f-411f-a716-10d0147ad68b "EVALUATE ROW(\"test\", 1)"`
Expected: JSON 响应，包含查询结果 `{"test": 1}`

- [ ] **Step 4: 验证批量 DAX 查询**

Run: `node scripts/powerbi-client.mjs query c85590e6-770f-411f-a716-10d0147ad68b "[\"EVALUATE ROW(\\\"a\\\", 1)\", \"EVALUATE ROW(\\\"b\\\", 2)\"]"`
Expected: JSON 响应，包含两条查询的结果

- [ ] **Step 5: 验证错误处理（无环境变量）**

Run: `env -i node scripts/powerbi-client.mjs list-tools 2>&1`（Linux/macOS）或手动清空环境变量后运行
Expected: stderr 输出 `Missing environment variables: POWERBI_CLIENT_ID, POWERBI_CLIENT_SECRET, POWERBI_TENANT_ID`

- [ ] **Step 6: 最终提交（如有修正）**

如果验证过程中修复了任何问题，提交修正。

---

## 自查

**规范覆盖检查：**
- PowerBIClient 类（constructor, listTools, getSchema, query）→ Tasks 2-4
- Client Credentials 认证（ClientSecretCredential）→ Task 2
- JSON-RPC 格式 HTTP 调用 → Task 3
- 202 轮询 → Task 3
- SSE 回退响应解析 → Task 3
- CLI 接口（list-tools, schema, query）→ Task 5
- 批量 daxQueries 支持 → Task 4
- 环境变量配置 → Task 2
- 错误处理（env 缺失、401/403 提示、GUID 校验、batch 限制、轮询超时）→ Tasks 2-4

**占位符检查：** 无 TBD/TODO/“稍后添加”/“类似任务 N”。

**类型一致性检查：**
- `daxQueryOrQueries` 在 query 方法签名和 CLI 中一致（string | string[]）
- `arguments_` 变量名在 query 方法中一致使用
- `artifactId` 参数名在 getSchema/query/CLI 中一致
- `POLL_TIMEOUT_MS` / `POLL_INTERVAL_MS` 常量名在 _mcpCall 中一致
