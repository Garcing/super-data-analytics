# querying-data：合并 SQL 与 PowerBI 查询为单一数据源接口

- 日期：2026-06-26
- 状态：设计稿（待评审）
- 背景：现有 `querying-via-sql`（满意版本，单入口 `--query` 支持 inline/@file/stdin）与 `querying-via-powerbi`（封装微软 MCP）分立。后续还要加数据源，每个数据源功能同构，统一成一个接口更省事。
- 方向：把 PowerBI 并入 SQL 的接口风格，**不是**让 SQL 退化成结构化 JSON。

## 设计原则

1. **统一在「接口契约」与「输出约定」，不在「输入序列化格式」。** 每个源的 `--query` 载荷是该源天然的文本形态：SQL 是 SQL 文本，PowerBI 是 JSON 请求文本。
2. **不为对称制造源专属 flag。** 结构化信息（artifactId、maxRows、daxQueries）全埋在 payload 里；CLI 表层只有 `--source` 切驱动。
3. **不跟预览期的 MCP 形状较劲。** PowerBI 的回传结果原样输出、原样保存，不做归一。
4. **SQL 的满意版本零改动。** `--query` 三模式、stdin 超时保护、`@文件` 读 `.sql`、输出 envelope 全部保留。

## 目录与 skill 布局

合并后单一 skill，命名 **`querying-data`**：

```
querying-data/
  SKILL.md                    # 入口路由：识别上游数据源 → references/<source>.md
  scripts/
    query.js                  # 唯一入口：node query.js <命令> --source <sql|powerbi> ...
    lib/sql.js                # SQL 驱动（从现 sql-query.js 迁入，逻辑不变）
    lib/powerbi.js            # PowerBI 驱动（从现 powerbi-mcp.js 迁入，内部仍组 JSON 调 MCP）
    package.json              # 合并依赖：pg + @azure/identity
  references/
    sql.md                    # SQL 的 CLI + payload 约定 + stdin/heredoc 路由示例
    powerbi.md                # PowerBI 的 CLI + JSON payload schema + DAX 函数参考
    get_table_schema.sql      # SQL schema 查询模板（保留原位）
  templates/style.sql         # SQL 风格模板（保留）
```

注：原 `querying-via-powerbi/semantic-model-ids.json` 不再单独存文件，并入 config.json（见「config.json 凭证与配置统一」）。

旧的 `querying-via-sql/`、`querying-via-powerbi/` 在新 skill 验证稳定后删除。

## 统一 CLI 契约

每个数据源都实现这组动词；`--source` 必填，无默认值。

```bash
node scripts/query.js test-connection --source <sql|powerbi>
node scripts/query.js schema          --source <sql|powerbi> <源专属参数...>
node scripts/query.js query           --source <sql|powerbi> --query <inline|@file|-> [--save <path>]
```

- `--query` 三种来源两个源一致：inline / `@文件` / `-`（stdin）。
- `schema` 的参数语义按源走（见下表），不强制对齐。
- PowerBI 专属子命令 `list-tools`（预览期保留，用于发现 MCP 后续新增工具）：`node scripts/query.js list-tools --source powerbi`。

### 各源行为

| | `--query` 载荷 | schema 参数 | stdout | `--save` |
|---|---|---|---|---|
| **sql** | SQL 文本 | `<schema.table> [schema.table ...]` | `{source,row_count,columns,rows}`（不变） | json/csv/xlsx |
| **powerbi** | JSON 请求 `{artifactId,maxRows,daxQueries[1..4]}` | `<artifactId>`（单个 GUID） | 原始 MCP JSON（不变） | **仅 json** |

## 输入侧细节

### SQL（不变）
- inline：`--query "<SQL>"`
- 文件：`--query @<path>`，读 `.sql`
- stdin：`--query -`，bash 用 quoted heredoc `<<'EOF'`，PowerShell 用单引号 here-string + UTF-8
- 含 `$` 或反引号的 SQL 不建议 inline；尽量 stdin 优先，避免落盘临时文件
- stdin 首字节超时保护（`SQL_QUERY_STDIN_TIMEOUT_MS`，默认 15s）保留

### PowerBI（新增三模式，内部行为不变）
- inline：`--query '{"artifactId":"...","maxRows":250,"daxQueries":["EVALUATE ..."]}'`
- 文件：`--query @request.json`
- stdin：`--query -`，heredoc/stdin 喂 JSON
- `artifactId` 由 agent 填入 payload，**不进 CLI flag**；上游没给时脚本回落到 config.json 的 `powerbi-semantic-models`（保底，见下文）
- 内部仍组装 MCP 请求并走 202 轮询，逻辑零改动

**偏好**：PowerBI inline JSON 在 shell 里引号/换行转义很丑，实际以 `@file` 与 stdin/heredoc 为主，inline 仅用于极短请求。references/powerbi.md 要写明此偏好。

## 输出侧与 `--save`

### stdout
各源保持原生输出，**不统一**：
- SQL：`{source,row_count,columns,rows,[result_path?]}`
- PowerBI：原始 MCP JSON

理由：MCP 接口处于预览阶段，微软频繁改动回传结构，归一成本高且易碎；agent 能直接理解两种形状。

### `--save`
- **仅在传 `--save <path>` 时落盘**，否则只输出 stdout。
- 保存目录与命名两边一致：`<工作区>/.super-data-analytics/results/`，命名由 agent 决定，参考 `query-result-YYYYMMDD-HHMMSS-<主题>.<ext>`。
- **sql**：支持 `.json` / `.csv` / `.xlsx`，逻辑不变。
- **powerbi**：**只支持 `.json`**（原样落盘 MCP 结果）。csv/xlsx 暂不支持——PowerBI 原始 MCP JSON 不是简单表格（多条 DAX → 多张表，结构会随微软改），强行拍平等于赌形状稳定，现在不做。后续若需要，再加一个「提取首张表」的归一器。
- **删除** PowerBI 现有强制写 `cache/dax-queries-*.json` + `KEEP_DAX_FILE` / `KEEP_DAX_RESULT` 那套：payload 现经 `--query` 传入，不再需要强制落盘请求文件。

## config.json 凭证与配置统一

SQL 已用 `~/.super-data-analytics/config.json` 的 `env` 块作为唯一来源。合并后把 PowerBI 的 `.env` 凭证、以及原 `semantic-model-ids.json` 的模型路由表，**全部并入同一个 config.json**：

```json
{
  "env": {
    "HOLOGRES_HOST": "...", "HOLOGRES_PORT": "...", "HOLOGRES_DATABASE": "...",
    "HOLOGRES_USER": "...", "HOLOGRES_PASSWORD": "...",
    "POWERBI_CLIENT_ID": "...", "POWERBI_CLIENT_SECRET": "...", "POWERBI_TENANT_ID": "..."
  },
  "powerbi-semantic-models": [
    { "id": "c85590e6-...", "name": "平台治理经营看板", "is_default": true,  "description": "..." },
    { "id": "3041d238-...", "name": "超级VIP经营看板",  "is_default": false, "description": "..." },
    { "id": "05a31944-...", "name": "私域Agent项目",    "is_default": false, "description": "..." }
  ]
}
```

- PowerBI 侧改为从 config.json 读 `POWERBI_*`，删掉 `.env` 加载逻辑。config.json 缺字段时，脚本报错并指引 agent 引导用户补全后写回（沿用 SQL 现有错误模式）。
- 原 `semantic-model-ids.json` 的三条记录迁入 `powerbi-semantic-models`，**补全 `description` 字段**（现文件里没有）。迁完后删除该文件。

### `powerbi-semantic-models` 是保底手段

`artifactId` 的优先级（references/powerbi.md 要写明）：

1. **上游直接提供**（agent 在 payload 里填好 `artifactId`）——正常路径，脚本直接用。
2. **上游没提供**（被单独调用，或 agent 没给）——脚本回落到读 config.json 的 `powerbi-semantic-models`，取 `is_default: true` 的那条；若 agent 指定了业务线/模型名，按 `name` 匹配。

config.json 里的这张表是**保底**，不是主路径。references/powerbi.md 的规则要体现：能从上游拿到 `artifactId` 就别去读 config，读 config 只是兜底。

## 入口 SKILL.md = 路由器

入口 SKILL.md 只做一件事：**帮 agent 判断上游要查的数据源是哪个**，再指向 `references/<source>.md` 读该源的 CLI 与 payload 格式。

判断信号（启发式，非穷举）：
- 提到语义模型 / 度量值 / DAX / PowerBI / 报表 → **powerbi**
- 提到 Hologres / 表 / SQL / 字段 / schema → **sql**
- 模糊时：问用户，或调 `retrieving-business-context` 查指标定义/数据源归属

per-source 的 CLI、payload schema、DAX 编写清单、stdin/heredoc/PowerShell 路由示例，全部落到 `references/{sql,powerbi}.md`。

## 迁移与清理

1. 新建 `querying-data/`，按上面布局迁入两套脚本，合并依赖。
2. 凭证迁移：先读 `querying-via-powerbi/.env` 现值 → 写入 config.json `env` → `test-connection --source powerbi` 验证通过 → 删 `.env`。
3. 模型路由迁移：读 `querying-via-powerbi/semantic-model-ids.json` 三条记录 → 补全 `description` 后写入 config.json `powerbi-semantic-models` → 验证保底回落能命中默认模型 → 删原文件。
3. 旧 `querying-via-sql/`、`querying-via-powerbi/` 在新 skill 跑通后删除。
4. 更新根 `CLAUDE.md` / `AGENTS.md` 里 `querying-data-via-*`、`querying-via-*` 的过时路径与板块说明。

## 坑清单

1. **PowerBI inline JSON 在 shell 里很丑**：长 JSON + 内嵌 DAX + 引号转义。实际以 `@file` 和 stdin/heredoc 为主，inline 仅极短请求。references 要写明偏好。
2. **凭证迁移别丢可用凭证**：`.env` → config.json，先 `test-connection` 验证再删 `.env`。
3. **PowerBI `--save` 不支持 csv/xlsx**：强行支持 = 赌 MCP 形状稳定，不做。
4. **schema 参数语义两源不同**：SQL 是 `schema.table` 列表，PowerBI 是单个 artifactId GUID。`schema --source X <args>` 的 args 含义按源走，各自 references 写清。
5. **依赖合并**：两个 `node_modules` 合一个；`pg` 的 Hologres BufferReader monkey-patch（处理 null 字段名）必须原样保留。
6. **PowerBI schema「缓存 24h」是现 SKILL.md 写了但代码没有的虚假承诺**：迁移时直接从 references 删掉，不实现、不带进来。
7. **`list-tools` 留作 PowerBI 专属**：预览期保留，用于发现 MCP 后续新工具；不进统一契约。
8. **旧目录与根文档清理**：迁移稳定后删旧 skill 目录，更新 CLAUDE.md / AGENTS.md 过时路径。

## 非目标（YAGNI）

- 不做 PowerBI 输出归一（MCP 预览期形状不稳）。
- 不做 SQL 结构化 JSON 输入（SQL 天然单位是文本，套 JSON 牺牲现有优雅）。
- 不做自动源推断（`--source` 必填，显式优先）。
- 不做多源 join/联邦查询。
