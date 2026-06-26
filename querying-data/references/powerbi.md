# PowerBI 源用法（Power BI 语义模型）

通过 `node scripts/query.js ... --source powerbi` 直连 Microsoft Fabric MCP HTTP 端点（`https://api.fabric.microsoft.com/v1/mcp/powerbi`），使用 Azure AD Client Credentials 零交互认证。凭证统一来自 `~/.super-data-analytics/config.json` 的 `env` 块（`POWERBI_CLIENT_ID` / `POWERBI_CLIENT_SECRET` / `POWERBI_TENANT_ID`），不读 `.env`、不依赖环境变量导出。

所有命令在 `querying-data/` 目录下执行，前缀为 `node scripts/query.js`。

## CLI 命令

```bash
# 1) 列出 MCP 端点可用工具（探测连通性也用它）
node scripts/query.js list-tools --source powerbi

# 2) 测试连接（内部走 listTools，返回 ok + tool_count）
node scripts/query.js test-connection --source powerbi

# 3) 获取语义模型 schema（artifactId 是 GUID）
node scripts/query.js schema --source powerbi <artifactId>

# 4) 执行 DAX 查询：--query 三种来源，载荷为 JSON（不是单条 DAX 字符串）
node scripts/query.js query --source powerbi --query '<JSON>'         # inline
node scripts/query.js query --source powerbi --query @<file-path>     # 文件
node scripts/query.js query --source powerbi --query -                # stdin（管道）

# 追加 --save <file-path> 可落盘结果；PowerBI 仅支持 .json（原始 MCP 结果）
node scripts/query.js query --source powerbi --query @./payload.json --save ./.super-data-analytics/results/pbi-result-20260626-103000-dau.json
```

> 子命令清单：`list-tools` / `test-connection` / `schema <artifactId>` / `query`。PowerBI 源的 `schema` 接收的是 **artifactId**，不是 schema.table。

## `--query` 载荷

**关键差异**：SQL 源的 `--query` 收 SQL 字符串，PowerBI 源的 `--query` 收 **JSON 对象**（不是单条 DAX 字符串）。三种输入模式（inline / `@file` / stdin）的形态与 SQL 源一致，只是文本是 JSON。

**Shell 友好性提示**：inline JSON 在 shell 里很难写好——引号、换行、嵌套都容易踩坑。优先用 `@file` 或 stdin/heredoc；只有极小的载荷（一两条短 DAX、字段不多）才考虑 inline。

### 载荷 schema

```json
{
  "artifactId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "maxRows": 250,
  "model": "主业务模型",
  "daxQueries": [
    "EVALUATE ROW(\"test\", 1)",
    "EVALUATE ROW(\"test\", 2)"
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `daxQueries` | string[] | 是 | 1 到 4 条 DAX 语句数组，每条非空 |
| `artifactId` | string (GUID) | 否 | 语义模型 ID。缺省时走保底回落（见下） |
| `maxRows` | int | 否 | 1..1000，默认 250 |
| `model` | string | 否 | 按名匹配保底模型；命中不到会 warn 并继续回落 |

### stdin / 文件示例

**bash quoted heredoc（推荐，引号抑制 `$` 展开）：**

```bash
node scripts/query.js query --source powerbi --query - <<'EOF'
{
  "artifactId": "11111111-2222-3333-4444-555555555555",
  "maxRows": 100,
  "daxQueries": ["EVALUATE TOPN(10, 'Sales')"]
}
EOF
```

**@file（payload.json）：**

```bash
node scripts/query.js query --source powerbi --query @./payload.json
```

## artifactId 保底规则

PowerBI 的 `artifactId` 可缺省，脚本按以下顺序解析（见 `scripts/lib/powerbi.js` 的 `resolveArtifactId`）：

1. **payload.artifactId 存在** → 直接使用（正常路径，**优先**）。
2. **payload.artifactId 缺失** → 读 `~/.super-data-analytics/config.json` 的 `powerbi-semantic-models` 数组回落：
   - 若 payload 带 `model` 字段 → 按 `name === model` 命中；命中不到则 `console.error` 警告后继续往下回落。
   - 否则取 `is_default: true` 的条目。
   - 再不行取数组第一个条目。

**原则**：上游能提供 `artifactId` 就提供——`config.json` 只是兜底。`model` 字段在 `config.json` 没匹配到时只是 **stderr 警告**，不会硬失败，会继续回落到默认/首条。

`config.json` 中 `powerbi-semantic-models` 的形态：

```json
{
  "powerbi-semantic-models": [
    {"id": "11111111-2222-3333-4444-555555555555", "name": "主业务模型", "is_default": true},
    {"id": "99999999-aaaa-bbbb-cccc-dddddddddddd", "name": "财务模型"}
  ]
}
```

## 输出

`query` 子命令向 stdout 输出 **MCP 端点的原始 JSON**（不归一化）。Preview API，结构可能随微软更新变化，agent 解析时按实际字段取，不要硬编码路径。

## `--save`（可选落盘）

- 默认不保存；仅当用户明确要求时才传 `--save <file-path>`。
- **仅支持 `.json`**（原样写 MCP 结果）；`.csv` / `.xlsx` 直接报错。
- 落盘目录由 agent 决定，建议 `<工作区>/.super-data-analytics/results/`。
- 命名建议：`pbi-result-YYYYMMDD-HHMMSS-<主题>.json`（agent 按需命名，不是硬规则）。
- 落盘成功时脚本在 **stderr** 打印 `结果已保存到: <path>`，原始 MCP 结果仍正常输出到 stdout。

## DAX 编写检查清单

写 DAX 前对照这 4 步自检：

1. 计算的初始筛选上下文是什么？
2. 涉及哪些表？关系和筛选方向？
3. 是否需要 `CALCULATE` 修改筛选器？
4. 完成后检查：是否复用了已有度量值？表/列/度量值名称是否在 schema 中？

## DAX 函数参考

微软官方文档，按需查阅，不要猜测函数用法。

**语法基础：**

- [DAX 查询语法规范](https://learn.microsoft.com/en-us/dax/dax-queries) — EVALUATE / DEFINE / ORDER BY 等查询编写规范

**函数策略：**

- 不确定用什么函数 → [DAX 函数板块概览](https://learn.microsoft.com/en-us/dax/dax-function-reference)
- 想看某个板块有哪些函数 → 板块概览页（见下表）
- 知道函数名但不确定参数 → 直接查函数页 `https://learn.microsoft.com/en-us/dax/<函数名小写>-function-dax`，例如 CALCULATE 的页面是 `https://learn.microsoft.com/en-us/dax/calculate-function-dax`

**函数板块：**

| 板块 | 地址 | 典型函数 |
|---|---|---|
| 聚合 | `https://learn.microsoft.com/en-us/dax/aggregation-functions-dax` | SUM, SUMX, AVERAGEX, MINX, MAXX |
| 日期时间 | `https://learn.microsoft.com/en-us/dax/date-and-time-functions-dax` | DATEADD, SAMEPERIODLASTYEAR, TOTALMTD |
| 筛选 | `https://learn.microsoft.com/en-us/dax/filter-functions-dax` | CALCULATE, FILTER, ALL, KEEPFILTERS |
| 信息 | `https://learn.microsoft.com/en-us/dax/information-functions-dax` | ISBLANK, HASONEVALUE |
| 逻辑 | `https://learn.microsoft.com/en-us/dax/logical-functions-dax` | IF, SWITCH |
| 关系 | `https://learn.microsoft.com/en-us/dax/relationship-functions-dax` | RELATED, USERELATIONSHIP |
| 表操作 | `https://learn.microsoft.com/en-us/dax/other-functions-dax` | TOPN, SUMMARIZE, VALUES |
