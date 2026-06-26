---
name: querying-data
description: 统一数据查询入口，按 --source（sql / powerbi）路由到对应驱动；支持 inline / @file / stdin 三种查询输入
metadata:
  skill-series: super-data-analytics
  chinese-name: 查询数据
---

# 查询数据

统一数据查询入口，按 `--source`（`sql` / `powerbi`）路由到对应驱动。所有命令在 `querying-data/` 目录下执行，前缀 `node scripts/query.js`。

```bash
node scripts/query.js <命令> --source <sql|powerbi> [参数]
```

## Step 1 识别数据源

按用户请求里的信号词判定 `--source`：

| 信号 | 路由到 |
|---|---|
| DAX / 语义模型 / 度量值 / Power BI / 看板 / 报表 / KPI 指标定义 | `--source powerbi` |
| Hologres / 表 / SQL / 字段 / schema / 数仓分区 / OSS 外表 | `--source sql` |
| 模糊（"查下 DAU"、"看看最近销量"），看不出走哪边 | 先问用户，或调 `retrieving-business-context` 拉业务上下文判定 |

## Step 2 读对应源的用法

**执行查询前，必须先读对应源的 reference**——里面写明 CLI 形态、载荷 schema、`--save` 规则、shell 写法等细节：

- `--source sql` → 读 [`references/sql.md`](references/sql.md)
- `--source powerbi` → 读 [`references/powerbi.md`](references/powerbi.md)

## 通用约定（两个源共同）

- `--query` 三种输入模式（同一套规则，文本内容不同：SQL 收 SQL 字符串，PowerBI 收 JSON 载荷）：
  - `--query "<内容>"` inline
  - `--query @<file-path>` 文件
  - `--query -` 或不传 → stdin（管道）
- `--save <file-path>` 仅在用户明确要求落盘时才传；不传则结果只打到 stdout。
- 结果落盘目录约定 `<工作区>/.super-data-analytics/results/`；命名由 agent 决定。
- 凭证统一来自 `~/.super-data-analytics/config.json` 的 `env` 块——脚本不读 `.env`、不依赖环境变量导出。配置缺失或字段不全时脚本报错指引补全，由 agent 引导用户提供后写回 config.json，再重试。
