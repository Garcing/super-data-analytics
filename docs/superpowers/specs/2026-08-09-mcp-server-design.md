# MCP 服务化设计 · super-data-analytics

- 日期：2026-08-09
- 状态：设计定稿，待评审 → 转实现计划
- 范围：把本套数据分析技能的 CLI 执行能力做成一个 MCP 服务，供服务器上的 hermes（接飞书/企微）和本地笔记本使用，彻底消除"每台机器调 Python/Node 依赖"的痛苦

---

## 1. 背景与目标

### 1.1 起因
项目此前在云服务器部署、用 hermes 跑时，遭遇严重的 Python 环境冲突。根因不是"缺某个工具"，而是**执行环境散落在多台机器、多个运行时（Node + Python）**，每台都要重新调通。

### 1.2 目标
- 把所有确定性 CLI 执行能力收敛进**一个 Docker 容器**，作为 MCP 服务对外提供；hermes 与笔记本只配置一个 URL，不再本地装依赖。
- 全部技能代码统一为 **Python**（用户是数据分析师，只读 Python），便于长期维护。
- 保留现有方法论/路由层（SKILL.md），MCP 只替代"手"（确定性执行），不替代"脑"（路由、口径对齐、质检）。

### 1.3 非目标（YAGNI）
- 不重写方法论技能（orchestrating-analytics、validating-analyses）——它们无脚本，靠 LLM + 指引。
- 不做 building-reports 的 streamlit 格式（用户已确认不好用）。
- 不做完整 OAuth 2.1 鉴权流程（MCP 规范里鉴权是可选的）。
- 不保留 SQL 的 csv/xlsx 文件导出（chat 场景 LLM 直接吃 JSON 行）。
- 不实现各 `test-connection` 的独立工具（连接错误各工具自身会报）。

---

## 2. 现状盘点

10 个 skill 模块，分两层：

**执行层（有确定性 CLI，MCP 候选）—— 8 个**
| 技能 | 现运行时 | 重写/剥离处理 |
|---|---|---|
| querying-data | Node | 重写为 Python |
| retrieving-context | Node 壳 + Python pipeline | 重写为纯 Python（复用 pipeline 逻辑，去掉 Node→Python IPC） |
| building-reports | Node（html/image/streamlit） | 重写为 Python（仅 html+image） |
| using-templates | Node（包 lark-cli） | 重写为 Python（仍调 lark-cli 子进程） |
| diagnosing-anomalies | Python 标准库 | 剥离纯计算内核 |
| predicting-trends | Python 标准库 | 剥离纯计算内核 |
| evaluating-impact | Python 标准库 | 剥离纯计算内核 |
| visualizing-data | Python（matplotlib） | 剥离渲染内核 |

**方法论层（无脚本，不进 MCP）—— 2 个**
- orchestrating-analytics（路由编排）、validating-analyses（质检）。仍由 hermes 加载 SKILL.md 作指引用。

---

## 3. 总体架构

```
┌────────────── 腾讯云 lighthouse  106.53.74.143 ──────────────┐
│                                                               │
│  笔记本(任意IP)                hermes 网关(v0.19.0, 占:80)     │
│      │ https+Bearer               │ localhost+Bearer          │
│      ▼                            ▼                           │
│   Caddy :443 ──TLS-ALPN证书─────► Docker(网络:host)           │
│   (mcp.super-data-               ┌────────────────────────┐  │
│    analytics.online)             │ FastMCP streamable HTTP │  │
│                                  │ stateless, :3100        │  │
│                                  │ 24 工具, Bearer 校验    │  │
│                                  │ in-process 调用 Python  │  │
│                                  │ 技能内核 + lark-cli子进程│  │
│                                  └───────────┬─────────────┘  │
│                                  127.0.0.1   │ 卷挂载          │
│                          ┌───────────────────┴──────────┐    │
│                          ▼                              ▼    │
│              Neo4j5 容器(127.0.0.1:7687)     config.json      │
│                          │                              (宿主)│
│                          └─ 不改原 skill 代码树 ─────────────┘│
└────────────────────────────┬──────────────────────────────────┘
                  VPN(tun0)  │                  │ HTTPS
                             ▼                  ▼
              Hologres(内网 192.168.x:31223)   Vercel Blob / apimart / Fabric / 飞书
```

---

## 4. 关键决策（含理由）

| 决策 | 选择 | 理由 |
|---|---|---|
| 部署形态 | Docker 容器 + streamable HTTP（stateless） | 依赖一次封进镜像，换机只拉镜像；hermes/笔记本零本地依赖 |
| MCP 实现 | FastMCP（Python） | 技能全 Python 后，in-process 调用最干净；streamable HTTP 已确认支持 |
| 技能语言 | 全部统一为 Python | 用户只读 Python；retrieving-context 去掉 Node→Python IPC 后更简单 |
| 容器网络 | `network_mode: host` | Neo4j 只绑 127.0.0.1:7687，host 网络才能连；且 hermes localhost:3100、tailscale/eth0 接口都直通 |
| embedding | ONNX/fastembed（替代 PyTorch） | 服务器仅 3.6GB 内存，PyTorch 有 OOM 风险；ONNX 占用 ~150-250MB，镜像 ~500-700MB |
| 画图交付 | MCP 原生 ImageContent + Vercel Blob URL 双保险 | hermes 能转发图片则直推；不能则用 URL（企微走"上传素材再发"也是吃 URL） |
| 工具命名 | 干净功能名（sql_query…），不加前缀 | hermes 自动加 `mcp_<server>_<工具>` 前缀，自加会双重前缀 |
| hermes server 名 | `sda` | 最终工具名如 `mcp_sda_sql_query`，品牌挂 server 层 |
| 鉴权 | 静态 Bearer token（`Authorization: Bearer`） | MCP 规范头格式；hermes 原生支持自定义 headers；单人内部工具不上 OAuth |
| 笔记本接入 | Caddy + 子域名 `mcp.super-data-analytics.online` + 自动 HTTPS | 用户已有该域名（华为云）；apex/www 仍指 Vercel 不动 |
| 凭证 | 容器挂载宿主 config.json，镜像零密钥 | 敏感信息不入镜像；服务器那份 config.json 所有 key 已是真实值 |
| 原 skill 代码 | 一律不动 | 用户铁律：新代码全放新 `mcp/` 目录，验证通过后再切换 |

---

## 5. 子项目拆分

工作量较大，拆两个独立子项目（各自 spec → 计划 → 实现）：

### 子项目 1：8 技能 → 干净 Python 内核
- 4 个 Node 技能：全新 Python 重写，**严格复刻原 CLI 的 JSON 输出契约**（用契约测试对照原码证明等价）。
- 4 个 Python 技能：剥离纯计算内核，**删除三态输入/argparse/stdin/`{ok:...}` 信封等本机 CLI 死代码**，统一风格，顺带修 bug。
- 产出：`mcp/sda_mcp/skills/*.py`，每个内核是纯函数（Python 类型入参 → dataclass 出参 → 失败抛 `SkillError`）。

### 子项目 2：FastMCP 服务 + 容器化 + hermes 接入
- FastMCP server（24 工具，分两批），工具层把内核 dataclass 包成 `structuredContent`+`outputSchema`，错误 → `isError`。
- Dockerfile + docker-compose（host 网络）+ Caddyfile。
- hermes `~/.hermes/config.yaml` 的 `mcp_servers` 加 `sda` 条目。
- 评估集（10 道只读题）。

**先 1 后 2。** 本 spec 覆盖两者总体设计；实现计划阶段按子项目分别细化。

---

## 6. 新目录结构（原仓库树不动）

```
super-data-analytics/                  ← 原 skill 目录树全部不碰
└── mcp/                               ← 全部新代码只在这里
    ├── pyproject.toml                 # fastmcp, httpx, psycopg[binary], msal/azure-identity,
    │                                  # neo4j, matplotlib, pandas, seaborn, scipy, pillow, openpyxl,
    │                                  # fastembed, onnxruntime, pydantic
    ├── Dockerfile                     # python:3.12-slim + fonts-noto-cjk + Node20(仅lark-cli) + bge-onnx
    ├── docker-compose.yml             # network_mode: host, 挂载 config.json
    ├── Caddyfile                      # mcp.super-data-analytics.online -> localhost:3100, Bearer 校验
    ├── sda_mcp/
    │   ├── server.py                  # FastMCP 入口, streamable HTTP stateless, Bearer 中间件
    │   ├── config.py                  # 读 config.json（语义同原 CLI）
    │   ├── errors.py                  # SkillError 基类 + 子类
    │   ├── runner.py                  # 内核调用 → MCP 结果 的胶水
    │   ├── auth.py                    # Bearer token 校验中间件
    │   ├── skills/                    # 8 个干净 Python 内核
    │   │   ├── querying_data.py
    │   │   ├── retrieving_context.py
    │   │   ├── building_reports.py
    │   │   ├── using_templates.py
    │   │   ├── diagnosing.py
    │   │   ├── predicting.py
    │   │   ├── evaluating.py
    │   │   └── visualizing.py
    │   └── tools/                     # MCP 工具定义，按技能分组
    │       ├── query_tools.py
    │       ├── retrieve_tools.py
    │       ├── analyze_tools.py
    │       ├── viz_tools.py
    │       ├── report_tools.py
    │       └── template_tools.py
    └── tests/
```

---

## 7. MCP 工具清单（24 个，干净命名）

hermes 最终看到 `mcp_sda_<工具名>`。

### 第 1 批（核心分析链，18 个）

**取数（querying_data）**
| 工具 | 入参 | 出参 | annotation |
|---|---|---|---|
| `sql_query` | `{sql, max_rows?}` | `{columns, rows, row_count}` | readOnly |
| `sql_schema` | `{tables: ["s.t",...]}` | 列定义[] | readOnly |
| `powerbi_list_models` | `{}` | 模型[] | readOnly |
| `powerbi_schema` | `{artifact_id}` | 语义模型 schema | readOnly |
| `powerbi_query` | `{artifact_id, dax_queries[1..4], max_rows?}` | 查询结果 | readOnly |

**语义检索（retrieving_context）**
| 工具 | 入参 | 出参 | annotation |
|---|---|---|---|
| `retrieve_search` | `{question, top_k?, targets?}` | 命中[]+图上下文 | readOnly |
| `retrieve_cypher` | `{statement}` | rows[] | destructiveHint（原始 Cypher 可写库） |
| `retrieve_schema` | `{}` | 图 schema | readOnly |
| `retrieve_doc` | `{doc: url\|token}` | 文档 markdown | readOnly |

**分析计算（diagnosing/predicting/evaluating 内核）**
| 工具 | 入参 | 出参 |
|---|---|---|
| `contribute` | `{method: add\|multiply\|ratio, ...payload}` | `{summary, rows, checks}` |
| `forecast` | `{metric, grain, horizon, model, series[], ...}` | `{forecast, backtest, confidence, warnings}` |
| `impact` | `{analysis_type, ...payload}` | 对应结果 |

**可视化（visualizing 内核）**
| 工具 | 入参 | 出参 |
|---|---|---|
| `chart` | `{type, title, subtitle, data[], encoding, options?}` | ImageContent + Blob URL（双保险） |

**报告（building_reports，html+image）**
| 工具 | 入参 | 出参 | annotation |
|---|---|---|---|
| `report_html_publish` | `{id, report:{meta,summary,conclusions}}` | 公网 URL | 写 Blob |
| `report_html_list` | `{}` | 报告[] | readOnly |
| `report_html_get` | `{id}` | 报告 JSON | readOnly |
| `report_html_delete` | `{id}` | `{deleted}` | destructive |
| `report_image_generate` | `{prompt, model?, size?, resolution?, n?}` | `{url, task_id, cost}` | 最长 180s |

### 第 2 批（验证凭证/CLI 后接，6 个）

**模板（using_templates，Python 包 lark-cli）**
`template_list` / `template_read` / `template_create` / `template_update` / `template_delete`（依赖 lark-cli 身份绑定）

**图谱同步（retrieving_context sync pipeline）**
| 工具 | 入参 | 出参 |
|---|---|---|
| `sync` | `{only?: fetch\|graph\|embed, dry_run?, force_embed?}` | `{counts}` |

每个工具配 `outputSchema`（Pydantic），FastMCP 自动生成 `structuredContent`。

---

## 8. 画图与图片交付

### chart 工具
1. 内核用 matplotlib 渲染到内存 `BytesIO`（`savefig` 到 buffer），不写本地文件、不要 `--output`。默认 PNG（飞书/企微兼容），保留 SVG 能力但 chat 默认 PNG。
2. 返回两个 content block + structuredContent：
   - `{type:"image", data:<base64>, mimeType:"image/png", annotations:{audience:["user"], priority:0.9}}`
   - `{type:"text", text:"图表: <Blob URL>"}` + `structuredContent:{url, format, width, height, warnings}`
3. 顺手上传 PNG 到 Vercel Blob（public）给 URL。
4. 双保险：hermes 能转发 ImageContent 就直推图；不能就用 URL（企微"上传素材再发"也吃 URL）。

### report_image_generate
apimart 已返回公网 URL，直接返回 URL + structuredContent，不必再传 Blob。

---

## 9. 错误处理约定

- `sda_mcp/errors.py`：`SkillError` 基类 + `ConfigError` / `ValidationError` / `DataSourceError` / `ExternalAPIError` / `TimeoutError`。
- **内核只抛异常**（不返回 `{ok:false}`）。MCP 工具层 `try/except`：
  - `SkillError` → MCP `isError:true` + 可操作 text（告诉 LLM 哪里错、怎么修，能自纠重试）。
  - 未预期异常 → `isError:true` + 通用信息 + 服务端记完整堆栈。
- 典型映射：缺凭证→`ConfigError`；Hologres 连不上→`DataSourceError`（检查 VPN/白名单）；Power BI 401/403→`DataSourceError`（查 Azure AD）；apimart 失败→`ExternalAPIError`（带 task 状态）。
- 超时：Power BI ≤60s、apimart ≤180s、embedding 首载 ~1-3s。
- 非致命 `warnings`（forecast/impact）放 structuredContent，不当错误。

---

## 10. 风格统一与 bug 修复

- 统一基线：全类型注解、dataclass/TypedDict 出参、统一 `SkillError` 体系、中文 docstring、一致命名。
- 每个技能重写/剥离时做一次代码审查，找之前未发现的 bug（exploration 已暴露的待查项）：
  - 三个分析脚本错误输出通道不一致（stderr vs stdout）——内核层 CLI 噪音本就消失。
  - `forecast` 预测区间是 `残差RMS×1.28` 启发式带，非严格置信区间——内核标注清楚。
  - Hologres 空字段名兼容（原 JS monkey-patch pg-protocol）——在 psycopg 上 spike 验证。
  - Power BI Fabric MCP 的 202 异步轮询逻辑——Python 重写时严格对照原 `powerbi.js`。
- bug 修复作为每个技能计划的显式步骤，配复审。

---

## 11. 凭证与配置

- 唯一来源：宿主 `~/.super-data-analytics/config.json`（卷挂载进容器，`SDA_CONFIG_PATH` 指向）。
- 服务器那份 config.json 已实测：所有 key 真实（含 `APIMART_API_KEY`）；`HOLOGRES_HOST` 是 VPN 内网 IP（与本机不同），其余凭证两边一致。
- 镜像不含任何密钥。

---

## 12. Docker 镜像

- 基础 `python:3.12-slim`，分层缓存：
  1. 系统包 `fonts-noto-cjk`（CJK 字体，中文图表必需）；Node 20 + `npm i -g @larksuite/cli`（仅 lark-cli 用）。
  2. `pip install`（pyproject 全量依赖；`psycopg[binary]` 免编译）。
  3. 构建期预下载 bge-small ONNX 模型（fastembed 首次拉取），避免运行时下载。
  4. COPY `mcp/` 代码。
- **不含原 skill 树**：4 个 Python 技能内核整体搬迁/提取到新目录，运行时不依赖原目录。
- CMD：FastMCP streamable HTTP，`0.0.0.0:3100`。
- 体积预估 ~500-700MB（ONNX 路线）；后续优化空间小，不再单列。

---

## 13. 网络

- `network_mode: host`：容器共享宿主网络。
  - MCP `0.0.0.0:3100` → hermes（宿主进程）走 `localhost:3100`。
  - MCP 连 Neo4j `127.0.0.1:7687`（Neo4j 容器只绑 localhost）。
  - Caddy `:443` 对外；eth0/tailscale 接口均直通。
- Neo4j：外部 docker 容器 `neo4j:5`，host 网络下直接 127.0.0.1:7687。
- 端口占用实测：80=hermes 网关；7687/7474=Neo4j；3100/443=空闲（MCP+Caddy 用）。

---

## 14. 鉴权

- 静态 Bearer token（长随机串）。MCP 侧 `auth.py` 中间件校验 `Authorization: Bearer <token>`，对所有来源（hermes localhost 与笔记本经 Caddy）统一生效。
- hermes 配置原生支持 `headers: {Authorization: "Bearer ***"}`，无需 Caddy 注入。
- Caddy 负责 TLS（笔记本路径），可选附加 token 校验（双保险，非必需）。
- hermes → MCP（localhost）与 笔记本 → Caddy → MCP（443）两路都用同一 Bearer。

---

## 15. 测试策略

- **契约测试（安全网）**：4 个 Node 重写，同输入跑原 Node CLI 与新 Python 内核，断言输出 JSON 语义相等。原码不删，做对照基准。
- **单元测试**：3 个分析脚本已有 pytest → 改造为新内核签名；chart 已有 test_chart_cli → 改造；4 个 Node 技能补合约测试。
- **MCP 层**：FastMCP 工具测试（sample 入参 → 校 structuredContent + outputSchema）。
- **集成**：MCP Inspector 联调。
- **端到端**：容器起来 → hermes 配 `sda` → 飞书/企微发消息 → 验证工具被正确调用、结果/图片送达。

---

## 16. 评估集

按 mcp-builder Phase 4 写 10 道只读、真实、可验证、稳定的评估题（XML），覆盖：语义检索、SQL 查询、贡献度归因、预测、效果评估、画图、html 报告发布。验证 LLM 能正确选用这套工具。

---

## 17. 部署与服务器实测

### 17.1 已实测（2026-08-09 paramiko SSH）
- hermes v0.19.0，`~/.hermes/hermes-agent/venv` 跑 `gateway run`；config 在 `~/.hermes/config.yaml`，`mcp_servers` 当前为空。
- Neo4j=docker `neo4j:5`，只绑 127.0.0.1:7687。
- config.json 在位，所有 key 真实；VPN tun0 在线，Hologres 内网可达。
- 内存 3.6GB（可用 ~1.9GB），磁盘剩 16GB。
- 端口 80=hermes，3100/443 空闲；lark-cli v1.0.83 已装。

### 17.2 部署清单
1. 华为云 DNS 加 A 记录 `mcp.super-data-analytics.online` → `106.53.74.143`（apex/www 不动）。
2. 腾讯云安全组放行 443。
3. 服务器构建镜像 → `docker compose up -d`（host 网络）。
4. Caddy 用 TLS-ALPN-01 签证书（80 被 hermes 占，不抢）。
5. hermes `config.yaml` 加：
   ```yaml
   mcp_servers:
     sda:
       url: "http://localhost:3100/mcp"
       headers:
         Authorization: "Bearer <token>"
   ```
6. 笔记本 MCP 客户端配 `https://mcp.super-data-analytics.online/mcp` + Bearer。

### 17.3 待核实（实现阶段）
- hermes 是否把工具返回的 ImageContent 作为图片消息发飞书/企微（不影响双保险设计，仅决定哪条路为主）。
- ONNX(bge-small) 向量与 Neo4j 现存向量（PyTorch 生成）的一致性；不一致则全量重新 embedding。
- lark-cli 的 hermes 身份绑定（batch 2 模板工具前置）。
- psycopg 对 Hologres 空字段名的兼容。

---

## 18. 风险

| 风险 | 缓解 |
|---|---|
| 4 个 Node 重写引入行为偏差 | 契约测试对照原 CLI；原码保留作回退 |
| ONNX 向量与存量不一致 | 实测余弦相似度；必要时重 embedding |
| 内存 3.6GB 紧张 | 选 ONNX；FastMCP 单进程；监控 |
| Hologres 依赖 VPN | 既有约束，VPN 已配，仅作告警 |
| hermes 不转发图片 | chart 已双保险（URL 兜底） |

---

## 19. 后续（不在本设计内）

- 子项目 1、2 各自的详细实现计划由 writing-plans 阶段产出。
- 切换 SKILL.md 活动入口指向新 Python 实现，作为子项目 1 收尾、经用户同意再做。
- embedding 若未来换更大模型，重评 ONNX vs PyTorch。
