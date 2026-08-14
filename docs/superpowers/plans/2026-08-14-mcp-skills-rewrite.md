# MCP 技能套件重写实施计划（mcp/skills/）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `mcp/skills/` 下全新撰写 9 个基于 19 个 MCP 工具的 agent-facing 技能文档（SKILL.md + references + 套件 README）。

**Architecture:** 纯文档任务，无代码。每技能一个目录，SKILL.md 按 spec §2 统一骨架；工具契约的唯一真相源是 `mcp/sda_mcp/tools/*.py`（Pydantic 模型 + docstring），绝不信旧 SKILL.md 的接口描述。原 skill 目录树只读参考（方法论思路），铁律零改动。

**Tech Stack:** Markdown；验收靠 grep 覆盖审计 + 本机 `mcp__sda__*` 工具冒烟。

**Spec:** `docs/superpowers/specs/2026-08-14-mcp-skills-rewrite-design.md`

---

## 全局约定（每个任务都适用）

- 中文行文，工具名/参数名/代码英文。
- SKILL.md 段落顺序固定：frontmatter → `# 标题（中文名）` → `## 何时使用 / 何时不用` → `## 决策流程` → `## 工具契约` → `## 调用示例` → `## 陷阱与注意` → `## 深入参考`。
- frontmatter 模板（spec §2.1）：`metadata.skill-series: super-data-analytics`、`chinese-name`、`mcp-server: sda`、`mcp-tools.owns/uses`。
- 工具契约段必须含「输入指引」（类型/枚举/默认值）和「输出指引」（关键字段含义 + agent 下一步）。
- 正文工具名一律写裸名（如 `sql_query`），前缀差异只在套件 README 说明一次。
- 每个任务结束 `git commit`，message 用 `docs(skills): ...` 前缀，结尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`。
- 契约事实表（下文各任务已内嵌）如与 `mcp/sda_mcp/tools/*.py` 实际代码冲突，**以代码为准**并更新文档。

---

### Task 1: 套件总览 README.md

**Files:**
- Create: `mcp/skills/README.md`

- [ ] **Step 1: 写入 README**

内容必须包含以下五节（自行组织文字）：

1. **套件定位**：一段话——本套件是 super-data-analytics 的 MCP 版技能文档，指导 agent 使用 `sda` MCP 服务的 19 个工具完成「检索→取数→分析→可视化→报告→质检」全链路。原 CLI 技能目录仅作历史对照。
2. **工具名前缀约定**：客户端自动加前缀——本机 Claude Code 为 `mcp__sda__sql_query`，hermes 为 `mcp_sda_sql_query`；本套件正文统一写裸名。
3. **路由图**（照抄 spec §4）：

```
用户请求
  → orchestrating-analytics 分流
     ├─ 直连：querying-data（先 retrieving-context 解析受治理口径）
     └─ 编排：retrieving-context → querying-data → 分析三选一
        （diagnosing / predicting / evaluating）→ visualizing-data
        → building-reports → validating-analyses 质检 → 交付
任何环节卡住：orchestrating 中途补编排；检索为空 → sync
```

4. **工具→技能覆盖表**：两列表格（工具 / owns 技能），19 行，数据用下表：

| 工具 | owns 技能 |
|---|---|
| retrieve_search / retrieve_cypher / retrieve_schema / retrieve_doc_read / retrieve_doc_update / sync | retrieving-context |
| sql_query / sql_schema / powerbi_schema / powerbi_query | querying-data |
| contribute | diagnosing-anomalies |
| forecast | predicting-trends |
| impact | evaluating-impact |
| chart | visualizing-data |
| report_html_publish / report_html_list / report_html_get / report_html_delete / report_image_generate | building-reports |

5. **统一约定**：① 三态输入（`-`/`@file`/inline）已随 CLI 消失，MCP 工具全部为 JSON 参数；② 产物 URL 时效——chart 的 Blob URL 长期有效，`report_image_generate` 的方舟 URL 仅 24h（`X-Tos-Expires=86400`），需要留存须及时下载；③ 工具失败统一返回 `isError:true` + 可操作提示，按提示修参重试；④ 部署运维见 `mcp/README.md`，本文档不重复。

- [ ] **Step 2: 提交**

```bash
git add mcp/skills/README.md
git commit -m "docs(skills): 套件总览 README"
```

---

### Task 2: retrieving-context（6 工具 + 2 references）

**Files:**
- Create: `mcp/skills/retrieving-context/SKILL.md`
- Create: `mcp/skills/retrieving-context/references/sync-and-maintenance.md`
- Create: `mcp/skills/retrieving-context/references/cypher-guide.md`

- [ ] **Step 1: 读真相源**

读 `mcp/sda_mcp/tools/retrieve_tools.py`（工具注册与入参模型）、`mcp/sda_mcp/skills/retrieving_context.py`（返回结构）、`mcp/sda_mcp/skills/retrieving_context_sync.py`（sync 行为）。方法论思路参考原 `retrieving-context/SKILL.md`（只读，勿改）。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`name: retrieving-context`、`chinese-name: 检索业务知识`、`owns: [retrieve_search, retrieve_cypher, retrieve_schema, retrieve_doc_read, retrieve_doc_update, sync]`、`uses: []`。

工具契约事实（必须核对照代码后写入「工具契约」+「调用示例」段）：

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `retrieve_search` | `question: str`（必填）；`top_k: int=5`（1-20；hybrid 为融合后全局 top_k，vector 为每索引 top_k）；`targets?: list[str]` 限定实体标签（如 `["指标"]`）；`strategy: "vector"\|"hybrid"` 默认 hybrid（向量+CJK 全文+精确命中 WRRF 融合） | 命中数组 + 图上下文。`retrieval` evidence：`fusion_score`（WRRF 融合分，只用于排序、非概率）、`vector_score`/`fulltext_score`（量纲不同禁止直接比较）、`exact_match`（受治理名称/ID/别名精确命中，未命中 null）；顶层 `score` 为兼容字段=vector cosine，仅全文召回时为 0 |
| `retrieve_cypher` | `statement: str`（必填，Cypher 语句；**可写库**，非 readOnly） | rows 数组。写前先 `retrieve_schema` |
| `retrieve_schema` | 无参 | `{nodes: {label: {properties: {名: 类型}, unique: [字段]}}, relationships: ["(:`指标`)-[:`使用`]->(:`表`)"]}`；图为空时报可操作错误→先跑 `sync` |
| `retrieve_doc_read` | `doc: str`（飞书文档 URL 或 token） | 正文 markdown。文档须已共享给飞书自建应用，否则权限错误 |
| `retrieve_doc_update` | `doc: str`（token）、`content: str`（markdown） | **覆盖写**正文（非追加）；文档须给应用开写权限 |
| `sync` | `dry_run: bool=false`；true=只预检（飞书数据、主键、配置、模型、Neo4j 连接）不写库 | 全量重建（清空图→约束→节点→关系→search_text→索引→embedding）。详细契约放 reference，SKILL.md 只留「何时用」：语义层多维表结构变更后、检索为空时 |

「决策流程」段浓缩：① 受治理指标先查口径再下数（何时必须检索）；② 默认 hybrid，仅诊断检索质量问题时回退 vector 做基线；③ 需要图上精确遍历（上下游依赖、层级）→ schema → cypher；④ 报告模板 = 「报告模板」多维表行（retrieve_search/retrieve_cypher 发现）+ 链接 docx 正文（doc_read 读、doc_update 改）——这一小节标题「报告模板（原 using-templates 的替代）」。

「陷阱与注意」候选（核实后取用）：精确命中只匹配受治理 ID/名称/别名，不扫定义长文本；换 embedding 模型/维度必须全量重算不能混用旧向量；`retrieve_doc_update` 是覆盖写；飞书文档/多维表必须共享给自建应用。

- [ ] **Step 3: 写 references/sync-and-maintenance.md**

内容（基于 `retrieving_context_sync.py` 与 `mcp/README.md` §6）：sync 两段式流程（外部准备全在清库前）；dry_run 预检清单；全量重建幂等性；字段类型清洗支持范围（Text/URL/Number/DateTime/Checkbox/单选多选/公式 lookup 按 `data_type` 分派；人员/附件/群组/位置/关联不支持→返回提示文本）；索引契约（`<label>_embedding_index` cosine、`<label>_search_text_index` cjk analyzer、key_field 唯一约束）；embedding 审计字段（`embedding_model`/`embedding_dimensions`/`embedding_updated_at`）。

- [ ] **Step 4: 写 references/cypher-guide.md**

内容：`retrieve_schema` 返回结构逐字段解读（properties 类型、unique 来自现存约束、relationships 是实际有向边）；写 Cypher 规范（label/属性名是中文需反引号；先 schema 后查询；只读查询优先；不要手扫全表算 cosine）；图扩展发生在融合后、每命中每类关系最多 20 邻居（解释为何检索结果里邻居被截断）。

- [ ] **Step 5: 提交**

```bash
git add mcp/skills/retrieving-context/
git commit -m "docs(skills): retrieving-context 技能（6 工具）"
```

---

### Task 3: querying-data（4 工具 + 1 reference）

**Files:**
- Create: `mcp/skills/querying-data/SKILL.md`
- Create: `mcp/skills/querying-data/references/powerbi.md`

- [ ] **Step 1: 读真相源**

读 `mcp/sda_mcp/tools/query_tools.py`、`mcp/sda_mcp/skills/querying_data.py`。DAX 方法论参考原 `querying-data/references/powerbi.md`（只读）。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`chinese-name: 数据查询`、`owns: [sql_query, sql_schema, powerbi_schema, powerbi_query]`、`uses: [retrieve_search]`（查表归属/指标口径时）。

工具契约事实：

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `sql_query` | `sql: str`（必填，单条 SELECT，readOnly） | `{columns, rows, row_count}`；行数据按列序对应 |
| `sql_schema` | `tables: list[str]`（min1，如 `["public.orders"]`） | 每表列定义数组（列名/类型） |
| `powerbi_schema` | `artifact_id: str`（语义模型 GUID，模型清单在 config.json，不另开工具） | 语义模型表/列 schema |
| `powerbi_query` | `artifact_id: str`；`dax_queries: list[str]`（1-4 条）；`max_rows: int=250`（1-1000） | 各查询结果；底层 msal + 202 异步轮询，agent 无感 |

「决策流程」浓缩：SQL（Hologres）默认，用户明确给 DAX / 点名 Power BI / 指定 PBI 模型才走 powerbi 分支；写 SQL 前先 `sql_schema` 确认字段名（空字段名会兜底成 `col_N`）；写 DAX 前必须 `powerbi_schema`。

「陷阱」候选：Hologres 走 VPN 偶发握手慢（connect_timeout 20s，超时先重试一次）；Power BI 是 Application 权限+Admin Consent；多条 DAX 用一次 `powerbi_query` 批量（1-4）而非多次调用。

- [ ] **Step 3: 写 references/powerbi.md**

浓缩原 powerbi.md：DAX 编写规范（先 schema 确认字段名、度量值引用规范、常见错误模式），去掉 CLI 相关内容，入口全部改为 `powerbi_schema`/`powerbi_query` 工具。

- [ ] **Step 4: 提交**

```bash
git add mcp/skills/querying-data/
git commit -m "docs(skills): querying-data 技能（4 工具）"
```

---

### Task 4: diagnosing-anomalies（contribute + 七法 reference）

**Files:**
- Create: `mcp/skills/diagnosing-anomalies/SKILL.md`
- Create: `mcp/skills/diagnosing-anomalies/references/attribution-methods.md`

- [ ] **Step 1: 读真相源**

读 `mcp/sda_mcp/tools/analyze_tools.py`（contribute 注册）、`mcp/sda_mcp/skills/diagnosing.py`（method 枚举、payload 结构、返回 summary/rows/checks）。方法论参考原 `diagnosing-anomalies/SKILL.md` 与其 references/ 七个方法文件（只读）。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`chinese-name: 异动归因`、`owns: [contribute]`、`uses: [sql_query, sql_schema, retrieve_search, chart]`。

工具契约事实（payload 字段以 `diagnosing.py` 实际校验为准）：

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `contribute` | `method: "add"\|"multiply"\|"ratio"`；`payload: dict`（同原 CLI：指标在两组维度值上的当前值/基线值） | `{summary, rows, checks}`——rows 为各维度贡献，checks 为一致性校验；按贡献绝对值排序解读，先看 checks 是否通过 |

「决策流程」浓缩原方法论：复现（确认口径与时间范围）→确认（排除数据延迟/埋点变更）→选拆解方法（可加合维度 add；乘法结构 GMV=流量×转化×客单 multiply；比率指标 ratio）→`contribute` 计算→下钻最大贡献项→事件验证（同期有无运营活动）→结论表达（「X 维度贡献了 Y% 的变动」）。

「陷阱」候选：归因前必须两期口径一致；比率指标不能直接用 add；贡献度解释的是差值分解不是因果关系。

- [ ] **Step 3: 写 references/attribution-methods.md**

七法浓缩成一节一法（每法 ~10 行：适用场景、数据要求、选择判据）——加法分解、乘法/LMDI、比率指标向后分解、漏斗链式、非线性替代、Shapley、监控场景根因排查。以原七个 reference 文件为思路源，重写为 agent 决策视角；与 `contribute` 三种 method 的对应关系要写明（其余方法目前无工具支撑，标注「方法论指导手工/SQL 分析」）。

- [ ] **Step 4: 提交**

```bash
git add mcp/skills/diagnosing-anomalies/
git commit -m "docs(skills): diagnosing-anomalies 技能（contribute）"
```

---

### Task 5: predicting-trends（forecast + reference）

**Files:**
- Create: `mcp/skills/predicting-trends/SKILL.md`
- Create: `mcp/skills/predicting-trends/references/target-setting.md`

- [ ] **Step 1: 读真相源**

读 `mcp/sda_mcp/skills/predicting.py`（payload 字段：metric/grain/horizon/model/series 等，以实际校验为准）。方法论参考原 `predicting-trends/SKILL.md` 与 `references/target-setting.md`（只读）。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`name: predicting-trends`（沿用原 name 下划线风格）、`chinese-name: 趋势预测`、`owns: [forecast]`、`uses: [sql_query, sql_schema, chart]`。

工具契约事实：

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `forecast` | `payload: dict`：时序 series（时间+值）、grain、horizon、model 等（逐字段对照 `predicting.py`） | `{forecast, backtest, confidence, warnings}`——先看 warnings（数据量不足/结构断点），再用 backtest 误差判断可信度，confidence 区间随 horizon 展宽 |

「决策流程」浓缩：预测适用性三查（历史点数够吗；有无结构断点如改版/改口径；季节性明显吗）；用 `sql_query` 取宽表时序→构造 payload→解读回测→置信带表达（「预计 X±Y，80% 区间」不报点值）。

- [ ] **Step 3: 写 references/target-setting.md**

浓缩原版：目标制定的基准选择（同比/环比/趋势外推/自下而上）、保守/中性/激进三档与置信区间的关系；forecast 工具输出如何映射到目标档位。

- [ ] **Step 4: 提交**

```bash
git add mcp/skills/predicting-trends/
git commit -m "docs(skills): predicting-trends 技能（forecast）"
```

---

### Task 6: evaluating-impact（impact + reference）

**Files:**
- Create: `mcp/skills/evaluating-impact/SKILL.md`
- Create: `mcp/skills/evaluating-impact/references/experiment-design.md`

- [ ] **Step 1: 读真相源**

读 `mcp/sda_mcp/skills/evaluating.py`（**analysis_type 完整枚举**——已知含 ab_rate/did/roi 但不止，必须列全；payload 字段按类型分派，`payload` 可选且平铺到顶层）。方法论参考原 `evaluating-impact/SKILL.md` 与 references 三个文件（只读）。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`chinese-name: 效果评估`、`owns: [impact]`、`uses: [sql_query, sql_schema, retrieve_search]`。

工具契约事实：

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `impact` | `analysis_type: <枚举，从 evaluating.py 列全>`；`payload?: dict`（可选，字段**平铺到顶层**再校验） | 按 analysis_type 分派的结果结构（逐类型在契约表里分小节写） |

「决策流程」浓缩：问题路由（有没有用→AB；没法实验看前后+对照组→DID；投入产出→ROI）；实验前置检查（随机性、同期性、样本量、SRM）；护栏指标；决策建议框架（显著且量级够→推全量；不显著→看功效再定）。

- [ ] **Step 3: 写 references/experiment-design.md**

浓缩原三 references：AB（假设、指标分层、样本量与显著性解读陷阱、SRM）、DID（平行趋势假设、对照选择）、ROI 与业务行动（归因口径、增量计算、续投决策）。

- [ ] **Step 4: 提交**

```bash
git add mcp/skills/evaluating-impact/
git commit -m "docs(skills): evaluating-impact 技能（impact）"
```

---

### Task 7: visualizing-data（chart + 全契约 reference）

**Files:**
- Create: `mcp/skills/visualizing-data/SKILL.md`
- Create: `mcp/skills/visualizing-data/references/chart-spec.md`

- [ ] **Step 1: 读真相源**

读 `mcp/sda_mcp/tools/visualize_tools.py` 与 `mcp/sda_mcp/skills/visualizing/contract.py`（spec 校验：type/title/subtitle/data/encoding/options 的字段与类型）、`renderers/` 目录（13 个图型：area, bar, boxplot, combo, funnel, heatmap, histogram, line, pareto, pie, scatter, table, waterfall）。方法论参考原 `visualizing-data/SKILL.md` 与 `references/developer-guide.md`（只读）。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`chinese-name: 数据可视化`、`owns: [chart]`、`uses: []`。

工具契约事实：

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `chart` | `spec: dict`（`type` 13 枚举 / `title` / `subtitle` / `data` / `encoding` / `options`，逐字段对照 contract.py）；`format: "png"\|"svg"` 默认 png；`dpi: int=144`（72-300） | 多 content 块：ImageContent（图片字节）+ 文本块「图表已生成（WxH）。URL: …」（png 自动上传 Vercel Blob；**上传失败仅返回图片块，不算错误**）。给用户交付时优先转述 URL |

「决策流程」浓缩：数据形态→图型映射表（趋势 line/area、构成 pie/堆叠 bar、对比 bar、分布 histogram/boxplot、相关 scatter、转化 funnel、贡献 waterfall、二八 pareto、矩阵 heatmap、组合 combo、精确数值展示 table）；数值标签可复现、准确优先于 AI 生图（`report_image_generate` 是视觉海报不是数据图，引导到 building-reports）。

「陷阱」候选：spec 校验失败会返回可操作错误，按提示补字段；中文需字体（服务端已内置 CJK 字体，无需关心）；svg 不上传 Blob 只返回图片块。

- [ ] **Step 3: 写 references/chart-spec.md**

从 `contract.py` + `renderers/` 提炼：spec 顶层五字段定义；13 图型逐一：适用场景、encoding 必填/可选通道、options 可选项、最小示例 JSON。这是本套件最大的 reference，宁全勿缺。

- [ ] **Step 4: 提交**

```bash
git add mcp/skills/visualizing-data/
git commit -m "docs(skills): visualizing-data 技能（chart）"
```

---

### Task 8: building-reports（5 工具 + 2 references）

**Files:**
- Create: `mcp/skills/building-reports/SKILL.md`
- Create: `mcp/skills/building-reports/references/html-report-contract.md`
- Create: `mcp/skills/building-reports/references/image-report-prompting.md`

- [ ] **Step 1: 读真相源**

读 `mcp/sda_mcp/tools/report_tools.py`、`mcp/sda_mcp/skills/building_reports/html_reports.py`（report JSON 结构、索引乐观锁）与 `image_gen.py`（方舟 Seedream 契约）。方法论参考原 `building-reports/SKILL.md`（只读；注意其 image 接口描述已全面过时——apimart→火山方舟，不要沿用）。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`chinese-name: 构建报告`、`owns: [report_html_publish, report_html_list, report_html_get, report_html_delete, report_image_generate]`、`uses: [retrieve_search, retrieve_doc_read, chart]`（取模板与配图）。

工具契约事实：

| 工具 | 输入指引 | 输出指引 |
|---|---|---|
| `report_html_publish` | `id: str`（min1，报告唯一标识）；`report: dict`（meta/summary/conclusions，结构见 reference） | `{url, report_id, blob_url}`——**必须打开 url 验证渲染**再交付 |
| `report_html_list` | 无参 | `{reports: [...]}` |
| `report_html_get` | `id: str` | 报告完整 JSON（用于改后重发） |
| `report_html_delete` | `id: str`；**destructive**，删除前确认用户意图 | 删除结果 |
| `report_image_generate` | `prompt: str`（min1）；`model?: str`（Model/Endpoint ID，缺省 config.json `VOLCENGINE_ARK_IMAGE_MODEL`）；`size?: str`（`"2K"` 或 WxH；比例在 prompt 里声明如「3:4」）；`response_format: "url"\|"b64_json"` 默认 url（b64 会返回 MCP ImageContent 块）；`seed?: int`（-1..2^31-1）；`watermark: bool=false` | structuredContent：`{provider, model, status, created, request_id, usage, images[{url, size, format, error}]}`；同步单图、无轮询；**URL 24h 过期，需要留存立即下载**；失败不自动重试（防重复计费） |

「决策流程」浓缩：格式路由（结构化多结论→html；视觉海报/单图播报→image）；模板流程小节（retrieve_search 找「报告模板」行 → doc_read 读正文结构 → 填数 → publish）；发布→`report_html_get`/打开 url 验证→交付链接并附口径说明。

「陷阱」候选：同一 id 重发是覆盖（乐观锁，冲突按提示重试）；image 生成约 60-90s 属正常；冒烟基线 2K+3:4 实测 1776×2368。

- [ ] **Step 3: 写 references/html-report-contract.md**

report JSON 完整结构（meta/summary/conclusions 逐字段、类型、示例），从 `html_reports.py` 校验代码提炼；id 命名建议（日期+主题 slug）。

- [ ] **Step 4: 写 references/image-report-prompting.md**

Seedream 提示词写法：明确图片类型（数据海报/周报头图）、版式比例声明进 prompt、中文 KPI 与趋势数值的写法（实测中文数值渲染准确）、负面模式（不要让它替代 chart 画精确数据图）；URL 时效与下载建议；seed 复用。

- [ ] **Step 5: 提交**

```bash
git add mcp/skills/building-reports/
git commit -m "docs(skills): building-reports 技能（5 工具）"
```

---

### Task 9: orchestrating-analytics（纯方法论）

**Files:**
- Create: `mcp/skills/orchestrating-analytics/SKILL.md`

- [ ] **Step 1: 读参考**

读原 `orchestrating-analytics/SKILL.md`（只读）浓缩方法论；引用的其他技能用新套件名。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`chinese-name: 分析编排`、`owns: []`、`uses: [retrieve_search, sql_query, sql_schema, contribute, forecast, impact, chart, report_html_publish]`。

「决策流程」浓缩原版核心：
- **轻重分流**：直连条件（明确 SQL/DAX；「查一下/跑一下」+具体指标；单源单指标明确时间；用户说直接查）→ 跳过编排但仍走语义层解析口径；编排条件（含「分析/为什么/看看情况」；多指标多维度需拆解；多实体多源；需多轮澄清）。
- **实体消歧**：模糊指标名先 `retrieve_search` 拿受治理定义，与用户确认口径后才进入取数（口径没对齐不给数字结论）。
- **SQL Spec 意识**：编排路径下先写下查询规格（表、过滤、口径、时间）再调 querying-data。
- **串联顺序**：检索→取数→分析三选一→画图→报告→质检；中途发现口径不明回退补检索。
- **交付验收**：必须返回可访问产物（URL/图片/结构化结果）+ 口径说明 + 缺口声明。

「陷阱」：简单问题不进编排（最小必要技能集合）；检索为空→提示可能需要 sync（指向 retrieving-context 的 reference）。

- [ ] **Step 3: 提交**

```bash
git add mcp/skills/orchestrating-analytics/
git commit -m "docs(skills): orchestrating-analytics 技能（入口路由）"
```

---

### Task 10: validating-analyses（纯方法论）

**Files:**
- Create: `mcp/skills/validating-analyses/SKILL.md`

- [ ] **Step 1: 读参考**

读原 `validating-analyses/SKILL.md`（只读）。

- [ ] **Step 2: 写 SKILL.md**

frontmatter：`chinese-name: 分析质检`、`owns: []`、`uses: [sql_query, retrieve_search, report_html_get]`（复算、口径核对、报告复核）。

「决策流程」浓缩五查（每查给可执行动作）：
1. **口径一致**：结论里的指标定义 vs `retrieve_search` 受治理定义 vs 取数 SQL 的实际过滤——三者一致？
2. **可复算**：抽 1-2 个关键数字用 `sql_query` 独立重算（不是重跑原 SQL，是换写法验证）。
3. **陷阱排查**：辛普森悖论（分组与总体方向一致吗）、幸存者偏差、基数效应（小基数增长率）、同期不可比（节假日/活动）。
4. **图表诚实**：轴是否截断误导、比例是否夸张、标签与数据一致（对照 chart spec）。
5. **置信度评级**：高/中/低 + 理由；低置信结论必须显式标注，不得含糊交付。

「输出要求」：质检结果附在交付物后（通过项/未通过项/建议），不是只回复「已完成」。

- [ ] **Step 3: 提交**

```bash
git add mcp/skills/validating-analyses/
git commit -m "docs(skills): validating-analyses 技能（交付质检）"
```

---

### Task 11: 覆盖审计 + 风格一致性检查

**Files:** 无新建，只校验。

- [ ] **Step 1: 工具覆盖审计**

```bash
grep -h -A 20 "owns:" mcp/skills/*/SKILL.md | grep -E "^\s+- (sql_query|sql_schema|powerbi_schema|powerbi_query|retrieve_search|retrieve_cypher|retrieve_schema|retrieve_doc_read|retrieve_doc_update|sync|contribute|forecast|impact|chart|report_html_publish|report_html_list|report_html_get|report_html_delete|report_image_generate)$" | sort | uniq -c
```

Expected: 19 行，每行计数 = 1（无遗漏、无重复主讲）。

- [ ] **Step 2: 结构一致性**

```bash
for f in mcp/skills/*/SKILL.md; do echo "== $f"; grep -c "^## " "$f"; done
```

Expected: 每个 SKILL.md 都有 6 个二级标题（何时使用/决策流程/工具契约/调用示例/陷阱与注意/深入参考；纯方法论技能无「深入参考」则 5 个）。人工浏览一遍 9 个文件确认段落顺序一致。

- [ ] **Step 3: 原目录零改动确认**

```bash
git status --porcelain -- building-reports querying-data retrieving-context visualizing-data using-templates diagnosing-anomalies predicting-trends evaluating-impact orchestrating-analytics validating-analyses
```

Expected: 空输出。

- [ ] **Step 4: 修正发现的问题并提交**

如有遗漏/重复/结构不一致，修文件后：

```bash
git add -A mcp/skills/
git commit -m "docs(skills): 覆盖审计与风格修正"
```

---

### Task 12: 冒烟验证（示例可跑）

**Files:** 无新建；发现问题回改对应 SKILL.md。

- [ ] **Step 1: 冒烟 4 个代表性工具**

在本会话（已配 `mcp__sda__*`）实际调用，对照 SKILL.md 示例与「输出指引」逐字段核对：

1. `mcp__sda__retrieve_search`：`{"question": "GMV 指标的定义", "top_k": 3}` → 核对返回含 `retrieval` evidence 字段。
2. `mcp__sda__sql_schema`：`{"tables": ["public.orders"]}`（表名按实际库调整）→ 核对列定义结构。
3. `mcp__sda__chart`：用 SKILL.md 里的最小示例 spec → 核对返回图片块 + URL 文本块。
4. `mcp__sda__report_html_list`：无参 → 核对 `{reports: [...]}`。

Expected: 4 个调用成功，返回结构与文档一致。外部依赖（VPN/飞书授权）不通时记录哪条 skip，其余必须通过。

- [ ] **Step 2: 按冒烟结果修正文档并提交**

```bash
git add -A mcp/skills/
git commit -m "docs(skills): 冒烟验证后的契约修正"
```

- [ ] **Step 3: 收尾——更新 mcp/README.md 技能文档指引**

在 `mcp/README.md` §9 开发节加一行：agent 技能文档在 `mcp/skills/`（入口 `mcp/skills/README.md`），与内核 `sda_mcp/skills/` 分层。提交：

```bash
git add mcp/README.md
git commit -m "docs(mcp): 指引 agent 技能文档位置"
```
