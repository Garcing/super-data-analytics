---
name: querying-via-powerbi
description: 从 PowerBI 语义模型查询数据，通过 Node.js 直接调用微软 MCP HTTP 端点，Client Credentials 认证
metadata: 
  skill-series: super-data-analytics
  chinese-name: 查询数据通过PowerBI
---

# 查询数据通过PowerBI

从 Power BI 语义模型查询数据，使用 Client Credentials 零交互认证

## 触发条件

- 用户需要从 Power BI 获取数据
- 用户使用 `/querying-via-powerbi` 命令
- 其他 skill 需要查询 Power BI 数据时引用

## 环境要求

- Node.js 18+
- Azure AD 凭证（`.env` 文件或环境变量）：`POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID`

## CLI 命令

```bash
# 列出可用工具
node scripts/powerbi-mcp.js list-tools

# 获取语义模型架构
node scripts/powerbi-mcp.js schema <artifactId>

# 执行 DAX 查询（读取唯一 JSON 请求文件）
node scripts/powerbi-mcp.js query --file <file_path>
```

## 核心流程

Phase 1（读取模型 ID）→ Phase 2（获取 Schema）→ Phase 3（写唯一请求 JSON 文件）→ Phase 4（执行查询）

### Phase 1：读取语义模型 ID

从 `semantic-model-ids.json` 获取模型 ID，默认使用 `is_default: true` 的模型，如果有指定业务线则使用对应模型。

### Phase 2：获取语义模型架构

```bash
node scripts/powerbi-mcp.js schema <artifactId>
```

返回包含表、列、度量值和关系的完整架构。已获取的 Schema 缓存 24 小时。

### Phase 3：生成 DAX 语句

根据用户问题 + 模型架构编写 DAX，写入唯一 JSON 请求文件；请求文件必须放在 `cache/` 目录下，文件名必须使用以下格式：

```text
dax-queries-YYYYMMDD-HHMMSS-<random>.json
```

其中 `YYYYMMDD-HHMMSS` 使用当前时间，`<random>` 使用至少 10 位随机字母数字，如 `cache/dax-queries-20260510-143522-a7f3c98f4k.json`，不要和已有的文件命名冲突。


**请求文件格式（JSON）**

```json
{
  "artifactId": "Phase1获取的语义模型ID",
  "maxRows": 1000,
  "daxQueries": [
    "EVALUATE ROW(\"test\", 1)",
    "EVALUATE ROW(\"test\", 2)",
    "EVALUATE ROW(\"test\", 3)",
    "EVALUATE ROW(\"test\", 4)"
  ]
}
```

`daxQueries` 是唯一支持的 DAX 字段，必须是数组，包含 1 到 4 条 DAX 查询。`maxRows` 默认值是 250，最大值是 1000。

**DAX 编写检查清单**：
1. 计算的初始筛选上下文是什么？
2. 涉及哪些表？关系和筛选方向？
3. 是否需要 CALCULATE 修改筛选器？
4. 完成后检查：是否复用了已有度量值？表/列/度量值名称是否在 schema 中？

### Phase 4：执行查询

```bash
node scripts/powerbi-mcp.js query --file cache/<Phase3生成的文件命名.json>
```

脚本读取请求 JSON，执行查询并输出 JSON 结果。查询结束后是否自动删除缓存文件由 `.env` 中的 `KEEP_DAX_FILE` 控制（默认 `true` 保留，设为 `false` 则执行后自动删除）

## DAX 函数参考

微软官方文档，按需查阅，不要猜测函数用法。

**语法基础：**

- [DAX 查询语法规范](https://learn.microsoft.com/en-us/dax/dax-queries) — EVALUATE / DEFINE / ORDER BY 等查询编写规范

**函数策略：**

- 不确定用什么函数 → [DAX 函数板块概览](https://learn.microsoft.com/en-us/dax/dax-function-reference)
- 想看某个板块有哪些函数 → 板块概览页（见下表）
- 知道函数名但不确定参数 → 直接查函数页 `https://learn.microsoft.com/en-us/dax/<函数名小写>-function-dax`，例如CALCULATE 的页面是  `https://learn.microsoft.com/en-us/dax/calculate-function-dax`

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
