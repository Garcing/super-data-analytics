# super-data-analytics 技能套件（MCP 版）

## 1. 套件定位

本套件是 super-data-analytics 的 MCP 版技能文档，指导 agent 使用 `sda` MCP 服务（19 个工具）完成「检索 → 取数 → 分析 → 可视化 → 报告 → 质检」全链路数据分析。仓库根目录下的原 CLI 技能目录（`querying-data/`、`retrieving-context/` 等）仅作历史对照，其命令行接口已过时，不要按它们调用。

Skill 与工具分工如下：

- **工具 schema** 说明单次调用的功能、参数、约束和返回结构。
- **SKILL.md** 说明分析流程、选择依据、停止条件、验证方法和交付纪律。
- **references/** 保存按需读取的复杂契约与方法卡，避免在主技能和工具描述中重复。
- **运行时语义图** 保存会持续变化的业务定义、表、维度和关系；Skill 不硬编码具体指标值。

## 2. 工具名前缀约定

MCP 客户端会自动给工具名加前缀：本机 Claude Code 中为 `mcp__sda__sql_query`，hermes 中为 `mcp_sda_sql_query`。本套件所有 SKILL.md 正文统一写**裸名**（如 `sql_query`），agent 按所在客户端自行补全前缀。

## 3. 路由图

```
用户请求
  → orchestrating-analytics 分流
     ├─ 直连：querying-data（先 retrieving-context 解析受治理口径）
     └─ 编排：retrieving-context → querying-data → 分析三选一
        （diagnosing-anomalies / predicting-trends / evaluating-impact）
        → validating-analyses（结论复核）→ visualizing-data / building-reports
        → validating-analyses（最终渲染复核，正式交付时）→ 交付
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
4. **部署运维**：服务部署、容器、凭证等运维事项见仓库根目录 `README.md`，本文档不重复。
5. **语义层优先**：受治理指标先通过 retrieving-context 解析；最新版只有直接「表关系」契约，不存在「表关系链」。
6. **来源说明**：分析交付应标注来源层级、口径、时间范围、新鲜度和未验证项；不存在的所有者或新鲜度信息不得编造。
7. **维护闭环**：MCP 工具、语义层字段或报告合约变化时，同一变更中更新对应 Skill/reference，并运行技能校验与测试。
