import { ClientSecretCredential } from '@azure/identity';
import {
  existsSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { join, dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// 从 scripts/ 和上级（skill 根）目录查找 .env 文件并加载
const __dirname = dirname(fileURLToPath(import.meta.url));
for (const dir of [__dirname, dirname(__dirname)]) {
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

const MCP_URL = 'https://api.fabric.microsoft.com/v1/mcp/powerbi';
const SCOPE = 'https://analysis.windows.net/powerbi/api/.default';
const POLL_TIMEOUT_MS = 60_000;
const POLL_INTERVAL_MS = 1_000;
const REQUESTS_DIR = join(__dirname, '..', 'cache');

export function parseQueryArgs(args) {
  let filePath;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--file') {
      filePath = args[++i];
      if (!filePath) {
        throw new Error('用法: node powerbi-mcp.js query --file <file_path>');
      }
    } else {
      throw new Error(`未知 query 参数: ${arg}\n用法: node powerbi-mcp.js query --file <file_path>`);
    }
  }

  if (!filePath) {
    throw new Error('用法: node powerbi-mcp.js query --file <file_path>');
  }

  return { filePath };
}

export function readQueryRequestFile(filePath) {
  let content;
  try {
    content = readFileSync(filePath, 'utf-8').replace(/^\uFEFF/, '').trim();
  } catch (e) {
    throw new Error(`无法读取查询请求文件 ${filePath}: ${e.message}`);
  }

  if (!content) {
    throw new Error(`查询请求文件为空: ${filePath}`);
  }

  let request;
  try {
    request = JSON.parse(content);
  } catch (e) {
    throw new Error(`查询请求文件不是合法 JSON: ${e.message}`);
  }

  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    throw new Error('查询请求 JSON 必须是对象，格式: { "artifactId": "...", "daxQueries": ["EVALUATE ..."] }');
  }

  const { artifactId, daxQueries, maxRows = 250 } = request;

  if (typeof artifactId !== 'string' || !artifactId.trim()) {
    throw new Error('查询请求 JSON 缺少 artifactId 字符串');
  }

  if (!Array.isArray(daxQueries)) {
    throw new Error('查询请求 JSON 必须包含 daxQueries 数组，不再支持 dax 或 daxQuery 字段');
  }

  if (daxQueries.length === 0 || daxQueries.length > 4) {
    throw new Error('daxQueries 必须包含 1 到 4 条 DAX 查询');
  }

  const normalizedQueries = daxQueries.map((query, index) => {
    if (typeof query !== 'string' || !query.trim()) {
      throw new Error(`daxQueries[${index}] 必须是非空字符串`);
    }
    return query;
  });

  if (!Number.isInteger(maxRows) || maxRows < 1 || maxRows > 1000) {
    throw new Error('maxRows 必须是 1 到 1000 之间的整数');
  }

  return { artifactId, maxRows, daxQueries: normalizedQueries };
}

function isInsideRequestDirectory(filePath) {
  const base = resolve(REQUESTS_DIR);
  const target = resolve(filePath);
  const rel = relative(base, target);
  return rel && !rel.startsWith('..') && !isAbsolute(rel);
}

export function shouldDeleteRequestFile(filePath) {
  const keep = process.env.KEEP_DAX_FILE !== 'false';
  return !keep && isInsideRequestDirectory(filePath);
}

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
      throw new Error(
        `缺少环境变量: ${missing.join(', ')}\n\n` +
        '配置方法:\n' +
        '  1. 前往 https://portal.azure.com → Azure Active Directory → 应用注册\n' +
        '  2. 注册应用，添加客户端密钥，授予 Power BI API 权限\n' +
        '  3. 设置环境变量:\n' +
        '     export POWERBI_CLIENT_ID="你的应用ID"\n' +
        '     export POWERBI_CLIENT_SECRET="你的密钥"\n' +
        '     export POWERBI_TENANT_ID="你的租户ID"\n\n' +
        '或者在脚本同级目录（或上级目录）创建 .env 文件:\n' +
        '  POWERBI_CLIENT_ID=xxx\n' +
        '  POWERBI_CLIENT_SECRET=xxx\n' +
        '  POWERBI_TENANT_ID=xxx'
      );
    }

    this.credential = new ClientSecretCredential(tenantId, clientId, clientSecret);
  }

  async _getToken() {
    const { token } = await this.credential.getToken(SCOPE);
    return token;
  }

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
        throw new Error('收到 202 状态码但缺少 operation-location 头');
      }
      await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
      resp = await fetch(location, { headers });
    }

    if (resp.status === 202) {
      const err = new Error(`查询超时（${POLL_TIMEOUT_MS / 1000}秒）`);
      err.statusCode = 202;
      throw err;
    }

    if (resp.status === 401 || resp.status === 403) {
      const text = await resp.text();
      const err = new Error(
        `HTTP ${resp.status}: Token 无效或权限不足\n` +
        '请检查: 1) Azure AD 应用已授予 Power BI API 权限 2) 已完成管理员同意 3) 租户ID 正确\n' +
        `详情: ${text.slice(0, 300)}`
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

    throw new Error('无法解析 Power BI MCP 端点返回的数据');
  }

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
    const daxQueries = Array.isArray(daxQueryOrQueries)
      ? daxQueryOrQueries
      : [daxQueryOrQueries];

    if (daxQueries.length === 0) {
      throw new Error('至少需要 1 条 DAX 查询');
    }

    if (daxQueries.length > 4) {
      throw new Error('批量查询最多支持 4 条 DAX 语句');
    }

    for (const [index, daxQuery] of daxQueries.entries()) {
      if (typeof daxQuery !== 'string' || !daxQuery.trim()) {
        throw new Error(`第 ${index + 1} 条 DAX 查询为空或不是字符串`);
      }
    }

    const result = await this._mcpCall('tools/call', {
      name: 'ExecuteQuery',
      arguments: { artifactId, maxRows, daxQueries },
    });
    return result;
  }

  _validateArtifactId(id) {
    if (!id || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
      throw new Error(`artifactId 格式错误 "${id}"，应为 GUID 格式: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`);
    }
  }
}

// CLI 入口
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
            console.error('用法: node powerbi-mcp.js schema <artifactId>');
            process.exit(1);
          }
          const result = await client.getSchema(artifactId);
          console.log(JSON.stringify(result, null, 2));
          break;
        }
        case 'query': {
          const { filePath } = parseQueryArgs(cliArgs);
          try {
            const request = readQueryRequestFile(filePath);
            const result = await client.query(request.artifactId, request.daxQueries, request.maxRows);
            const output = JSON.stringify(result, null, 2);
            console.log(output);

            if (process.env.KEEP_DAX_RESULT === 'true') {
              const basename = filePath.replace(/(^.*[\\/])?dax-queries-/, '');
              const resultPath = join(REQUESTS_DIR, `result-${basename}`);
              writeFileSync(resultPath, output, 'utf-8');
            }
          } finally {
            if (shouldDeleteRequestFile(filePath) && existsSync(filePath)) {
              unlinkSync(filePath);
            }
          }
          break;
        }
        default:
          console.error(`未知命令: ${command}\n`);
          console.error('用法: node powerbi-mcp.js <命令> [参数]');
          console.error('');
          console.error('命令:');
          console.error('  list-tools                   列出 Power BI 可用的 MCP 工具');
          console.error('  schema <artifactId>          获取语义模型结构');
          console.error('  query --file <file_path>     从 JSON 请求文件读取 DAX 并执行查询');
          process.exit(1);
      }
    } catch (err) {
      console.error(err.message);
      process.exit(1);
    }
  })();
}
