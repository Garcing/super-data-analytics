# MCP 技能套件重写设计（mcp/skills/）

日期：2026-08-14
状态：已与用户逐节确认
前置：`2026-08-09-mcp-server-design.md`（MCP 服务已上线，19 工具）

## 0. 背景与目标

MCP 服务（`mcp/`，19 个工具）已完成原 CLI 执行能力的迁移与升级。原仓库 10 个 skill 目录是给「本地跑 CLI 的 agent」写的，接口已过时（using-templates 已无对应工具、building-reports 的 image 接口全部换火山方舟、三态输入约定消失）。

目标：**基于当前 19 个 MCP 工具重新撰写一套 agent-facing 技能文档**，存放于 `mcp/skills/`。不是翻译旧文档——是先理解工具现状，仅参考旧技能的方法论思路，全新重写 SKILL.md 与 references。

铁律不变：原 skill 目录树零改动；所有新文件只进 `mcp/`。

## 1. 目录结构（9 个技能）

```
mcp/skills/                      # agent-facing 技能套件（纯文档，无代码）
├── README.md                    # 套件总览 + 路由图 + 统一约定 + 工具覆盖表
├── orchestrating-analytics/     # 入口路由：轻重分流、消歧、流程编排（纯方法论）
│   └── SKILL.md
├── retrieving-context/          # 语义层 6 工具
│   ├── SKILL.md
│   └── references/
│       ├── sync-and-maintenance.md
│       └── cypher-guide.md
├── querying-data/               # 取数 4 工具
│   ├── SKILL.md
│   └── references/
│       └── powerbi.md
├── diagnosing-anomalies/        # contribute
│   ├── SKILL.md
│   └── references/
│       └── attribution-methods.md
├── predicting-trends/           # forecast
│   ├── SKILL.md
│   └── references/
│       └── target-setting.md
├── evaluating-impact/           # impact
│   ├── SKILL.md
│   └── references/
│       └── experiment-design.md
├── visualizing-data/            # chart
│   ├── SKILL.md
│   └── references/
│       └── chart-spec.md        # 13 图型 type/encoding/options 全契约
├── building-reports/            # 报告 5 工具
│   ├── SKILL.md
│   └── references/
│       ├── html-report-contract.md
│       └── image-report-prompting.md
└── validating-analyses/         # 交付质检（纯方法论）
    └── SKILL.md
```

- 目录名沿用原名便于对照；内容全新基于 19 个工具重写。
- using-templates 不复现：模板语义拆入 retrieving-context（模板=语义层多维表行+docx 正文）与 building-reports（读模板→填数→发布）各一小节。
- orchestrating / validating 为纯方法论技能，无 references。

## 2. 统一风格模板

每个 SKILL.md 严格按以下段落顺序，中文行文，工具名/参数名/代码保持英文：

1. frontmatter（见 §2.1）
2. `## 何时使用 / 何时不用`：正面触发 + 边界（交给哪个技能）
3. `## 决策流程`：编号步骤/流程图，方法论精华浓缩于此（判断规则、选择分支，不含实现细节）
4. `## 工具契约`：表格列出本技能 owns 的工具——用途 / 关键入参 / 返回要点
5. `## 调用示例`：1-2 个最小可跑示例，入参 JSON + 返回结构摘要 + 下一步动作
6. `## 陷阱与注意`：每条一句话 + 规避方式（浓缩原 SKILL.md 与 mcp/README.md 踩坑记录）
7. `## 深入参考`：references 链接 + 何时需要读

SKILL.md 目标 ~150 行内；深度内容进 references 按需加载。

### 硬约定

1. **工具调用段必须有「输入指引」和「输出指引」**：入参给类型/枚举/默认值；输出说明关键字段含义和 agent 下一步动作（如「`fusion_score` 只用于排序，不是概率」）。
2. **一个工具只在一个技能主讲（owns）**：其他技能引用时只写工具名 + 一句用途，不重复契约——单一真相源。
3. **错误处理写行为不写原理**：`SkillError` → `isError:true` + 可操作提示，按提示修参重试。
4. 套件 README 承担：路由图、工具→技能映射总表、统一约定（工具名前缀因客户端而异——本机 `mcp__sda__sql_query`、hermes `mcp_sda_sql_query`，正文统一写裸名；三态输入已消失，全部 JSON 参数；产物 URL 时效）。

### 2.1 frontmatter metadata

```yaml
---
name: retrieving-context
description: <一句话触发描述>
metadata:
  skill-series: super-data-analytics
  chinese-name: 检索业务知识
  mcp-server: sda
  mcp-tools:
    owns:
      - retrieve_search
      - retrieve_cypher
      - retrieve_schema
      - retrieve_doc_read
      - retrieve_doc_update
      - sync
    uses: []
---
```

- `skill-series`：系列声明，所有技能统一。
- `chinese-name`：沿用原约定。
- `mcp-tools.owns`：本技能主讲契约的工具，**唯一定责处**；grep 所有 `owns` 即可审计 19 工具全覆盖、无重复主讲。
- `mcp-tools.uses`：会调用但契约由他技定义的工具，供 agent 快速判断。
- 纯方法论技能 `owns: []`，`uses` 列全链路常用工具。

## 3. 内容分配与工具归属

| 技能 | owns | SKILL.md 方法论核心 | references |
|---|---|---|---|
| orchestrating-analytics | 无 | 轻重分流（直连 vs 编排）、实体消歧（先 retrieve_search 解析口径）、SQL Spec 意识、多技能串联顺序、交付验收（必须返回可访问产物） | 无 |
| retrieving-context | retrieve_search / retrieve_cypher / retrieve_schema / retrieve_doc_read / retrieve_doc_update / sync | 何时检索（受治理指标先查口径再下数）；hybrid vs vector（默认 hybrid；`retrieval` evidence 字段解读）；报告模板=语义层多维表行+docx 正文 | sync-and-maintenance（dry_run 预检、何时重灌、字段清洗支持范围）、cypher-guide（schema 解读 + Cypher 规范） |
| querying-data | sql_query / sql_schema / powerbi_schema / powerbi_query | SQL 默认、PBI 显式才走；先 sql_schema 确认字段再写 SQL；DAX 必须先 powerbi_schema | powerbi.md（DAX 编写规范浓缩） |
| diagnosing-anomalies | contribute | 归因流程：复现→确认→拆解方法选择（add/multiply/ratio）→下钻→结论表达 | attribution-methods.md（七法浓缩：何时用哪种、数据要求） |
| predicting-trends | forecast | 预测适用性判断（历史够不够、结构断点）、回测结果解读、置信带表达 | target-setting.md |
| evaluating-impact | impact | 分析类型路由（ab_rate/did/roi…）、实验前置条件、护栏指标、决策建议框架 | experiment-design.md（AB/DID/ROI 设计浓缩） |
| visualizing-data | chart | 图型选择决策（13 图型→数据形态映射）、spec 构造、PNG/SVG 选择、返回双保险（ImageContent + Blob URL） | chart-spec.md（从 `sda_mcp/skills/visualizing/contract.py` 提炼全契约） |
| building-reports | report_html_publish / _list / _get / _delete / report_image_generate | 格式路由（html 结构化 vs image 视觉单图）；报告 JSON 构造；模板经语义层获取；发布→验证→交付链接 | html-report-contract.md、image-report-prompting.md（Seedream 提示词、URL 24h 时效须及时下载） |
| validating-analyses | 无 | 交付前五查：口径一致、可复算、陷阱（辛普森/幸存者/基数）、图表诚实、置信度评级 | 无 |

## 4. 数据流与验收

### 端到端链路（套件 README 路由图）

```
用户请求
  → orchestrating-analytics 分流
     ├─ 直连：querying-data（先 retrieving-context 解析受治理口径）
     └─ 编排：retrieving-context → querying-data → 分析三选一
        （diagnosing / predicting / evaluating）→ visualizing-data
        → building-reports → validating-analyses 质检 → 交付
任何环节卡住：orchestrating 中途补编排；检索为空 → sync
```

产物链：SQL rows → chart（ImageContent + Blob URL）→ html 报告（公网 URL）/ image 报告（方舟 URL，24h 时效）。交付须附口径说明 + 缺口声明。

### 验收方式

1. **工具覆盖审计**：19 工具 ∪ 各技能 `owns` 恰好相等（grep 可验证）。
2. **契约一致性**：每个工具的入参/返回描述逐条对照 `mcp/sda_mcp/tools/*.py` 的 Pydantic 模型与 docstring；禁止凭旧 SKILL.md 或记忆写参数。
3. **风格一致性**：9 个 SKILL.md 段落结构相同（§2 骨架）。
4. **冒烟**：挑 retrieve_search、sql_query、chart、report_html_publish 按 SKILL.md 示例实调（本机 `mcp__sda__*`），确认示例可跑、返回结构与文档一致。
5. 原 skill 目录树零改动。

## 5. 明确不做（YAGNI）

- 不迁移 using-templates 的模板 CRUD 操作文档（对应工具已不存在）。
- 不写 streamlit 报告文档（MCP 端已砍）。
- 不在技能文档里重复 mcp/README.md 的部署运维内容，仅链接引用。
- references 不复制代码实现，只写 agent 视角的契约与判断规则。
