# PowerBI Node.js 重构设计

> 用 Node.js 替代 Python MCP 代理架构，Client Credentials 零交互认证，直接调用微软 Power BI MCP HTTP 端点。

## 背景

当前架构（Python）的问题：

- Device Code Flow 首次登录需要打开浏览器输入设备码
- Refresh token 过期后（~90天）必须再次手动登录
- 无法在无浏览器环境（服务器、Docker）使用
- 目标：发布到 skill 市场，任何人任何环境都能零交互使用

## 方案：纯库模式（方案 A）

放弃 MCP 代理层，封装一个 Node.js 直接调用库 + CLI。

### 为什么不用 MCP 代理

MCP 代理（STDIO server）是为了让 OpenClaw 通过 MCP 协议发现和调用工具。但微软的 Power BI MCP 端点本身就是一个 HTTP API，完全可以绕过 MCP 协议层直接调用——就像 `test_powerbi.py` 那样。

### 为什么选 Client Credentials

| 方案 | 零交互 | 跨平台 | 安全性 | 配置复杂度 |
|---|---|---|---|---|
| Client Credentials | ✅ | ✅ | ✅（app secret） | 中（需 Azure AD 配置） |
| Device Code Flow | ❌ 需浏览器 | ❌ | ✅ | 低 |
| Username/Password | ✅ | ✅ | ❌ 微软不推荐 | 低 |
| Managed Identity | ✅ | ❌ 仅 Azure | ✅ | 高 |

Client Credentials 是唯一同时满足零交互 + 跨平台 + 安全的方案。

## 项目结构

```
scripts/
├── powerbi-client.mjs     ← 新增：核心库 + CLI（唯一新增文件）
├── chart_generator.py     ← 保留
└── web_report_builder.py  ← 保留
```

用 `.mjs` 后缀直接支持 ES Modules，不需要 `package.json` 的 `type: "module"` 配置。

### 依赖

- `@azure/identity` — 唯一外部依赖，提供 `ClientSecretCredential`
- Node.js 18+ 内置 `fetch` — HTTP 请求

### 配置（环境变量）

```
POWERBI_CLIENT_ID=xxx        # Azure AD 应用注册的 client_id
POWERBI_CLIENT_SECRET=xxx    # Azure AD 应用注册的 client_secret
POWERBI_TENANT_ID=xxx        # Azure AD 租户 ID
```

## PowerBIClient 类

```javascript
class PowerBIClient {
  constructor()
  // 从环境变量读取配置，创建 ClientSecretCredential

  async listTools()
  // 转发 MCP tools/list 到微软，返回工具定义数组

  async getSchema(artifactId)
  // 调用 MCP tools/call → GetSemanticModelSchema
  // 返回语义模型结构（表、列、度量值、关系等）

  async query(artifactId, daxQueryOrQueries, maxRows = 250)
  // daxQueryOrQueries: string → 单条 daxQuery
  //                    string[] → 批量 daxQueries（max 4）
  // 调用 MCP tools/call → ExecuteQuery
  // 处理 202 轮询（每秒重试，最多 60 秒）
}
```

### 认证流程

```
ClientSecretCredential(tenantId, clientId, clientSecret)
  → POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
    grant_type=client_credentials, scope=https://analysis.windows.net/powerbi/api/.default
  → access_token（自动缓存，过期自动刷新，无需手动管理）
```

scope 是 OAuth 的权限声明，告诉 Azure AD 这个 token 用于访问 Power BI API 的所有已授权权限。`/.default` 表示"你在 Azure Portal 里给这个应用授予了哪些 Power BI 权限，都要"。

### HTTP 调用

直接 POST 到 `https://api.fabric.microsoft.com/v1/mcp/powerbi`，body 是 JSON-RPC 格式：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ExecuteQuery",
    "arguments": {
      "artifactId": "...",
      "daxQuery": "EVALUATE ROW(\"test\", 1)",
      "maxRows": 250
    }
  }
}
```

注意：这是微软端点要求的请求格式，不是我们实现了 MCP 协议层。

### 202 轮询

微软处理复杂查询时返回 HTTP 202 + `operation-location` header：

```
POST → 202 + operation-location URL
  → GET operation-location (每秒重试)
  → 200 → 返回结果
  → 超时 60 秒 → 报错
```

## CLI 接口

```bash
# 列出微软返回的可用工具
node scripts/powerbi-client.mjs list-tools

# 获取语义模型结构
node scripts/powerbi-client.mjs schema <artifactId>

# 执行单条 DAX 查询
node scripts/powerbi-client.mjs query <artifactId> "EVALUATE ..."

# 批量执行 DAX 查询（JSON 数组，最多 4 条）
node scripts/powerbi-client.mjs query <artifactId> '["DAX1", "DAX2"]'
```

语义模型 ID 不通过 CLI 命令获取，agent 直接读 `semantic-model-ids.json`。

## 错误处理

| 场景 | 行为 |
|---|---|
| 环境变量缺失 | stderr 输出缺哪个变量，exit 1 |
| Token 获取失败 | stderr 输出 Azure AD 错误，exit 1 |
| HTTP 401/403 | 提示检查应用权限和 admin consent，exit 1 |
| HTTP 5xx | 输出状态码和响应体，exit 1 |
| 202 轮询超时 | "query timeout after 60s"，exit 1 |
| artifactId 格式错误 | 提示需要 GUID 格式，exit 1 |
| daxQueries 超过 4 条 | 提示最多 4 条，exit 1 |

原则：错误信息可操作（告诉用户该检查什么），所有错误走 stderr，stdout 只有成功时的 JSON。

## 不做的事

- 不实现 MCP server（STDIO/HTTP 代理）
- 不实现 `GenerateQuery`（付费功能未开通）
- 不实现交互式 setup 引导
- 不动 `chart_generator.py` 和 `web_report_builder.py`
- 不包一层读 `semantic-model-ids.json`（agent 直接读）

## Azure AD 配置步骤（用户侧）

发布到 skill 市场后，用户需要：

1. 在 Azure Portal 注册应用（或使用已有应用）
2. 添加 client secret
3. 授予 Power BI API 的 Application 类型权限（`Dataset.Read.All`、`SemanticModel.Read.All` 等）
4. 管理员同意（admin consent）
5. 配置 3 个环境变量
