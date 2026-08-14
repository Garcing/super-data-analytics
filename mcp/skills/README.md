# super-data-analytics 技能套件（MCP 版）

## 1. 套件定位

本套件是 super-data-analytics 的 MCP 版技能文档，指导 agent 使用 `sda` MCP 服务（19 个工具）完成「检索 → 取数 → 分析 → 可视化 → 报告 → 质检」全链路数据分析。仓库根目录下的原 CLI 技能目录（`querying-data/`、`retrieving-context/` 等）仅作历史对照，其描述的命令行接口已过时，不要按它们调用。

## 2. 工具名前缀约定

MCP 客户端会自动给工具名加前缀：本机 Claude Code 中为 `mcp__sda__sql_query`，hermes 中为 `mcp_sda_sql_query`。本套件所有 SKILL.md 正文统一写**裸名**（如 `sql_query`），agent 按所在客户端自行补全前缀。

## 3. 路由图

```
用户请求
  → orchestrating-analytics 分流
     ├─ 直连：querying-data（先 retrieving-context 解析受治理口径）
     └─ 编排：retrieving-context → querying-data → 分析三选一
        （diagnosing / predicting / evaluating）→ visualizing-data
        → building-reports → validating-analyses 质检 → 交付
任何环节卡住：orchestrating 中途补编排；检索为空 → sync
```

## 4. 工具 → 技能覆盖表

| 工具 | owns 技能 |
|---|---|
| retrieve_search / retrieve_cypher / retrieve_schema / retrieve_doc_read / retrieve_doc_update / sync | retrieving-context |
| sql_query / sql_schema / powerbi_schema / powerbi_query | querying-data |
| contribute | diagnosing-anomalies |
| forecast | predicting-trends |
| impact | evaluating-impact |
| chart | visualizing-data |
| report_html_publish / report_html_list / report_html_get / report_html_delete / report_image_generate | building-reports |

## 5. 统一约定

1. **无三态输入**：CLI 时代的 `-` / `@file` / inline 三态输入已消失，MCP 工具全部为 JSON 参数。
2. **产物 URL 时效**：`chart` 产出的 Vercel Blob URL 长期有效；`report_image_generate` 产出的方舟 URL 仅 24 小时有效（`X-Tos-Expires=86400`），需要留存须及时下载。
3. **失败处理**：工具失败统一返回 `isError:true` + 可操作提示，按提示修正参数后重试，不要盲目换工具。
4. **部署运维**：服务部署、容器、凭证等运维事项见 `mcp/README.md`，本文档不重复。
