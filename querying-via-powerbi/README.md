# querying-via-powerbi

从 Power BI 语义模型查询数据，通过微软 Fabric MCP HTTP 端点执行 DAX，Client Credentials 零交互认证。

## 目录结构

```
querying-via-powerbi/
  .env                    # Azure AD 凭证 + 缓存策略（不入库）
  .gitignore
  SKILL.md                # AI Agent 技能定义
  README.md
  semantic-model-ids.json # 语义模型 ID 注册表
  schema-*.json           # 已拉取的语义模型 Schema（参考用）
  cache/                  # DAX 请求文件，执行后行为由 KEEP_DAX_FILE 控制
  scripts/
    powerbi-mcp.js        # 核心：PowerBIClient 类 + CLI
    package.json          # 依赖：@azure/identity
    node_modules/
```

## 环境要求

- Node.js 18+
- Azure AD 应用注册，授予 Power BI API 权限（Application 类型 + Admin Consent）

## 配置

编辑 `.env`，填入 Azure AD 应用凭证：

```env
POWERBI_CLIENT_ID=你的应用ID
POWERBI_CLIENT_SECRET=你的客户端密钥
POWERBI_TENANT_ID=你的租户ID
KEEP_DAX_FILE=true
```

| 变量 | 说明 | 默认值 |
|---|---|---|
| `POWERBI_CLIENT_ID` | Azure AD 应用 ID | 必填 |
| `POWERBI_CLIENT_SECRET` | 客户端密钥 | 必填 |
| `POWERBI_TENANT_ID` | 租户 ID | 必填 |
| `KEEP_DAX_FILE` | 执行后是否保留 DAX 请求文件 | `true`（保留） |
| `KEEP_DAX_RESULT` | 是否将查询结果保存到 cache | `false`（不保存） |

`.env` 查找顺序：`scripts/`（当前目录）→ `querying-data-via-powerbi/`（上级目录），找到即停。

## 安装

```bash
cd scripts && npm install
```

`node_modules/` 随代码携带，拷贝即用，无需再次安装。

## CLI 命令

### 列出可用工具

```bash
node scripts/powerbi-mcp.js list-tools
```

### 获取语义模型架构

```bash
node scripts/powerbi-mcp.js schema <artifactId>
```

返回包含表、列、度量值和关系的完整 JSON Schema。

### 执行 DAX 查询

```bash
node scripts/powerbi-mcp.js query --file cache/dax-queries-xxx.json
```

读取 JSON 请求文件中的 DAX 语句，执行查询并输出 JSON 结果。

**请求文件格式：**

```json
{
  "artifactId": "语义模型ID",
  "maxRows": 1000,
  "daxQueries": [
    "EVALUATE TOPN(10, '表', [度量值], DESC)"
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `artifactId` | string | 语义模型 GUID |
| `daxQueries` | string[] | 1–4 条 DAX 查询 |
| `maxRows` | int | 每条查询最大行数，默认 250，上限 1000 |

## 典型工作流

1. **选模型** → 从 `semantic-model-ids.json` 选取模型 ID
2. **拉 Schema** → `schema <id>` 了解表结构、度量值、关系
3. **写 DAX** → 将查询写入 `cache/dax-queries-YYYYMMDD-HHMMSS-<random>.json`
4. **执行** → `query --file cache/xxx.json` 获取结果

## 依赖

| 包 | 用途 | 必需 |
|---|---|---|
| `@azure/identity` | Azure AD Client Credentials 认证 | 是 |
