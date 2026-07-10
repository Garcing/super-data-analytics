---
name: querying-data
description: 统一数据查询入口，按数据源子命令（sql / powerbi）路由到对应驱动；支持 inline / @file / stdin 三种查询输入
metadata:
  skill-series: super-data-analytics
  chinese-name: 查询数据
---

# 查询数据

统一数据查询入口，按数据源子命令（`sql` / `powerbi`）路由到对应驱动。所有命令在 `querying-data/` 目录下执行，前缀 `node scripts/query.js`。

```bash
node scripts/query.js <sql|powerbi> <命令> [参数]
```

## 运行环境与依赖

- Node.js `>=20.0.0`。
- 在 `querying-data/scripts/` 执行 `npm ci`；依赖以该目录的 `package.json` / `package-lock.json` 为准：`@azure/identity`、`pg`、`pg-protocol`、`xlsx`。
- 凭证只写入 `~/.super-data-analytics/config.json` 的 `env`：
  - SQL/Hologres：`HOLOGRES_HOST`、`HOLOGRES_PORT`、`HOLOGRES_DATABASE`、`HOLOGRES_USER`、`HOLOGRES_PASSWORD`。
  - Power BI：`POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID`；语义模型候选来自 `powerbi-semantic-models`，可用 `node scripts/query.js powerbi list-semantic-models` 查看。
- 可选进程变量 `SQL_QUERY_STDIN_TIMEOUT_MS` 只调整 stdin 超时，不属于凭证。

完整安装矩阵见仓库根目录 `DEPENDENCIES.MD`。


## Step 1 识别数据源

按用户请求里的信号词判定数据源子命令：

| 信号 | 路由到 |
|---|---|
| DAX / 语义模型 / 度量值 / Power BI / 看板 / 报表 / KPI 指标定义 | `powerbi` |
| Hologres / 表 / SQL / 字段 / schema / 数仓分区 / OSS 外表 | `sql` |
| 模糊（"查下 DAU"、"看看最近销量"），看不出走哪边 | 先问用户，或调 `retrieving-context` 拉业务上下文判定 |

## Step 2 读对应源的用法

**执行查询前，必须先读对应源的 reference**——里面写明 CLI 形态、载荷 schema、`--output` 规则、shell 写法等细节：

- `sql` → 读 [`references/sql.md`](references/sql.md)
- `powerbi` → 读 [`references/powerbi.md`](references/powerbi.md)

## 通用约定（两个源共同）

- 正文输入三种模式（同一套规则，文本内容不同：SQL 用 `--sql` 收 SQL 字符串，PowerBI 用 `--payload` 收 JSON 载荷）：
  - `--sql "<SQL>"` / `--payload '<JSON>'` inline
  - `--sql @<file-path>` / `--payload @<file-path>` 文件
  - `--sql -` / `--payload -` 或不传正文 flag → stdin（管道）
- `--output <file-path>` 仅在用户明确要求落盘时才传；不传则结果只打到 stdout。
- 结果落盘目录约定 `<工作区>/.super-data-analytics/results/`；命名由 agent 决定。
- 凭证统一来自 `~/.super-data-analytics/config.json` 的 `env` 块——脚本不读 `.env`、不依赖环境变量导出。配置缺失或字段不全时脚本报错指引补全，由 agent 引导用户提供后写回 config.json，再重试。
