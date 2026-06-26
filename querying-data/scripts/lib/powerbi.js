import { ClientSecretCredential } from '@azure/identity';
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

// 凭证由 dispatcher（query.js）调 lib/sql.js 的 loadConfig() 灌进 process.env。
// PowerBIClient 构造函数照旧从 process.env 读 POWERBI_*，本文件不再读 .env。

const MCP_URL = 'https://api.fabric.microsoft.com/v1/mcp/powerbi';

// 保底回落：payload 没带 artifactId 时，从舰队共享 config.json 读默认语义模型
const CONFIG_PATH = join(homedir(), '.super-data-analytics', 'config.json');

// 解析 artifactId：
//   1) payload 自带 → 直接用（正常路径）
//   2) 没带 → 读 config.json 的 powerbi-semantic-models，按 payload.model 命名匹配；
//      命中不到 name 时回落 is_default:true；再不行回落第一个条目
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
      throw new Error(
        `配置缺少: ${missing.join(', ')}\n\n` +
        '请补全舰队共享配置 ~/.super-data-analytics/config.json 的 env 块（缺这几项）:\n' +
        '  {\n' +
        '    "env": {\n' +
        '      "POWERBI_CLIENT_ID": "应用ID",\n' +
        '      "POWERBI_CLIENT_SECRET": "密钥",\n' +
        '      "POWERBI_TENANT_ID": "租户ID"\n' +
        '    }\n' +
        '  }\n' +
        '把缺的几项告诉我，我帮你写入 config.json 后重试。'
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

// PowerBI --query 载荷解析：JSON 对象 { artifactId?, daxQueries, maxRows, model? }
// artifactId 可缺（交给 resolveArtifactId 保底回落）；model 为可选字符串（按名回落）
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
  const { artifactId, daxQueries, maxRows = 250, model } = request;
  // artifactId 可缺（由 resolveArtifactId 兜底）
  if (model !== undefined && typeof model !== 'string') {
    throw new Error('model 必须是字符串');
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
  return { artifactId, maxRows, daxQueries: normalizedQueries, model };
}

// PowerBI --save 仅支持 .json（原样写 MCP 结果）；csv/xlsx 直接报错
export async function savePowerBiResult(json, savePath) {
  const { mkdirSync, writeFileSync } = await import('node:fs');
  const { dirname } = await import('node:path');
  const dotIdx = savePath.lastIndexOf('.');
  const ext = dotIdx === -1 ? '' : savePath.slice(dotIdx).toLowerCase();
  if (ext !== '.json') {
    throw new Error(`PowerBI --save 仅支持 .json（原始 MCP 结果）；收到 ${ext || '(无扩展名)'}。csv/xlsx 暂不支持`);
  }
  mkdirSync(dirname(savePath), { recursive: true });
  writeFileSync(savePath, typeof json === 'string' ? json : JSON.stringify(json, null, 2), 'utf-8');
}

export { MCP_URL, SCOPE };
