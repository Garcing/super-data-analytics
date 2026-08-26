# SDA MCP Agent 维护手册

本文件是维护本仓库的 Agent 的主指令。项目对外介绍见 [`README.md`](README.md)，分析 Agent 的 Skill 入口见 [`skills/README.md`](skills/README.md)。

本仓库只维护 Super Data Analytics MCP 服务。拆分前的 CLI Skill 套件已归档到 `Garcing/super-data-analytics-old`；除非任务明确要求兼容旧实现，不要把旧目录或 CLI 代码复制回来。

## 1. 维护目标

- 对外保持一个稳定的 Streamable HTTP MCP 服务和清晰的 19 工具契约。
- 用 `skills/` 承载分析方法、流程和工具编排，用 `sda_mcp/skills/` 承载确定性执行。
- 工具说明应让模型从 tool list 中理解功能、关键约束、入参和返回结果，但“何时使用”的长篇方法论留给对应 Skill。
- 配置、凭证和环境差异留在部署环境，不进入代码、镜像或 Git 历史。
- 对破坏性动作、外部写入和可能产生费用的调用提供明确语义与保守默认值。

## 2. 仓库结构

| 路径 | 维护职责 |
|---|---|
| `sda_mcp/server.py` | FastMCP Streamable HTTP 服务入口 |
| `sda_mcp/auth.py` | 静态 Bearer Token 验证 |
| `sda_mcp/config.py` | `config.json` 加载和必填配置检查 |
| `sda_mcp/errors.py` | 对 Agent 可操作的统一错误类型 |
| `sda_mcp/tools/` | MCP 注册、Pydantic 输入模型、工具说明、结果和内容块组装 |
| `sda_mcp/skills/` | 查询、检索、分析、可视化和报告的 Python 内核 |
| `skills/` | 9 个面向 Agent 的分析工作流 Skill 与 references |
| `tests/` | 单元测试、契约测试和按环境变量启用的集成测试 |
| `docs/` | 当前仍有效的架构调研和设计依据 |
| `Dockerfile`、`docker-compose.yml`、`Caddyfile` | 服务构建、运行和反向代理配置 |

Python 要求 `>=3.10`，依赖、构建和 pytest 配置以 `pyproject.toml` 为准。

仓库是 MCP 项目，但内部 Python 包必须保持 `sda_mcp`。`mcp` 是官方 Python SDK 的顶级包名；把业务包重命名为 `mcp` 会遮蔽 SDK 的 `mcp.server`、`mcp.types` 和 `Client`，禁止这样重构。若以后采用 src layout，使用 `src/sda_mcp/`。

## 3. 架构边界

```text
MCP Client
   │ HTTP + Bearer
   ▼
sda_mcp/tools          参数 schema、工具说明、错误映射、MCP 内容块
   │
   ▼
sda_mcp/skills         确定性业务执行，不感知 MCP 客户端
   │
   ├─ Neo4j + Fastembed       受治理语义层与 Hybrid GraphRAG
   ├─ psycopg / Fabric MCP    Hologres SQL 与 Power BI
   ├─ Matplotlib / Seaborn    准确可复现的图表
   ├─ Feishu OpenAPI          语义源和报告模板正文
   ├─ Vercel Blob             HTML 报告存储
   └─ Volcengine Ark          图片报告生成
```

边界规则：

- 工具层保持薄：校验 MCP 参数、调用内核、转换 dataclass/内容块，不复制业务算法。
- 内核函数以普通 Python 类型为输入，返回 dataclass 或明确结构，失败抛 `SkillError` 子类。
- 工具返回尽量使用结构化内容；图片可以组合 `ImageContent` 与简短文本结果，禁止把大段 Base64 塞入结构化 JSON。
- 工具默认同步定义，由 FastMCP 在线程池中执行；不要无理由把同步外部客户端包装成伪异步。
- 工具名和顶层返回字段视为公共 API。改名、删字段或改变含义属于 breaking change。

## 4. 工具与 Skill 对应关系

当前共 19 个工具。新增或删除工具时，必须同步更新本节、README、工具测试和相关 Skill。

| Skill / 分组 | 工具 | 维护重点 |
|---|---|---|
| `querying-data` | `sql_query`、`sql_schema` | 默认只读 SQL；限制结果规模并提供可操作错误 |
| `querying-data` | `powerbi_query`、`powerbi_schema` | 仅用于显式 Power BI/DAX；先确认模型 schema |
| `retrieving-context` | `retrieve_search` | 默认 Hybrid 检索；返回检索证据和受控图上下文 |
| `retrieving-context` | `retrieve_cypher`、`retrieve_schema` | 受约束 Cypher 与 Neo4j 实时 schema |
| `retrieving-context` | `retrieve_doc_read`、`retrieve_doc_update` | 读取或覆盖飞书文档正文；更新属于外部写入 |
| `retrieving-context` | `sync` | `dry_run=false` 会全量重建语义图，必须先预检 |
| `diagnosing-anomalies` | `contribute` | 加法、乘法/LMDI、比率贡献度分解 |
| `predicting-trends` | `forecast` | 可解释基线预测、回测和区间 |
| `evaluating-impact` | `impact` | A/B、DID、ROI 和样本量估算 |
| `visualizing-data` | `chart` | 声明式图表 spec 到 PNG/SVG |
| `building-reports` | `report_html_publish`、`report_html_list`、`report_html_get`、`report_html_delete` | Blob 上的 HTML 报告生命周期；删除是外部写入 |
| `building-reports` | `report_image_generate` | 火山方舟同步图片生成，可能产生费用 |
| `orchestrating-analytics` | 无专属工具 | 编排上述检索、查询、分析、验证和报告 Skill |
| `validating-analyses` | 无专属工具 | 独立复核现有证据和产物，按需复用查询工具 |

工具代码分组：

- `sda_mcp/tools/query_tools.py`：4 个查询工具。
- `sda_mcp/tools/retrieve_tools.py`：6 个语义层工具。
- `sda_mcp/tools/analyze_tools.py`：3 个分析工具。
- `sda_mcp/tools/visualize_tools.py`：1 个可视化工具。
- `sda_mcp/tools/report_tools.py`：5 个报告工具。

## 5. Tool、内核与 Skill 的同步规则

修改工具前先确认变化属于哪一层：

1. 算法或外部服务行为放入 `sda_mcp/skills/`，并先补内核测试。
2. MCP 入参、说明、annotations 和输出封装放入 `sda_mcp/tools/`。
3. 工作流、口径选择、执行顺序、失败回退和交付标准放入对应 `skills/*/SKILL.md`。
4. 复杂输入契约或方法说明放入对应 `skills/*/references/`，不要让 `SKILL.md` 无限膨胀。
5. 用户可见的能力、工具数量或启动方式变化时更新 `README.md`。
6. 运维、配置、部署和维护约束变化时更新本文件。

工具说明至少应回答：

- 工具实际做什么，以及不会做什么。
- 关键前置条件和危险副作用。
- 每个非显然参数的含义、格式、默认值和约束。
- 返回对象的关键字段、分页/截断信息和图片等非 JSON 内容块。
- 调用方能够采取行动的错误条件。

“何时使用”保持一两句即可，详细决策交给 Skill。不要在工具说明和 Skill 中复制整段相同内容。

## 6. 语义检索与同步

当前语义层是面向受治理元数据的轻量 Hybrid GraphRAG：

- Neo4j 保存实体、关系、vector index 和 CJK full-text index。
- Fastembed 使用 `BAAI/bge-small-zh-v1.5` 生成 512 维向量。
- `retrieve_search(strategy="hybrid")` 组合 vector、full-text、精确实体命中和 Weighted RRF。
- 融合后只对最终候选批量扩展图邻居，避免命中数乘关系数的往返。
- `retrieve_schema` 从 Neo4j 实时内省，不用配置文件虚构 schema。

更换 embedding 模型、维度、索引策略或融合权重时：

1. 先把真实失败问题加入 `tests/retrieval_gold.json`。
2. 比较 vector 与 hybrid 的 Recall@1、Recall@5、MRR@5、平均延迟和 P95。
3. 检查返回中的 retrieval evidence，不能直接相加 cosine 与 Lucene 原始分数。
4. 先执行 `sync(dry_run=true)`，确认数据源、模型和 Neo4j 均可用。
5. 需要全量同步时再显式执行 `sync(dry_run=false)`。
6. 跑完整测试和真实 Neo4j 冒烟，至少保留一个发布周期的 vector 回退。

`sync` 的行为契约（真相源 `sda_mcp/skills/retrieving_context_sync.py`；字段清洗细节以该模块 docstring 为准）：

- 两段式：先做零写库预检（config 校验、飞书拉数、主键唯一性校验、模型探测、Neo4j 连通），全部通过才开始清库；任一步失败时现有图保持原样。
- 全量重建幂等：清空节点后按当前配置重建约束与索引，改配置不残留历史 schema 对象。
- Neo4j 数据库仅供 SDA 使用：库内手工创建的约束和非 LOOKUP 索引会在全量 sync 时被删除。
- 首次部署后图为空，必须执行一次 `sync` 才能检索。

完整取舍见 [`docs/neo4j-graphrag-2026-research.md`](docs/neo4j-graphrag-2026-research.md)。

## 7. 配置与凭证

唯一业务配置来源是 `~/.super-data-analytics/config.json`，容器内由 `SDA_CONFIG_PATH` 指向只读挂载文件。服务鉴权 Token 单独通过 `SDA_MCP_TOKEN` 提供。

常用配置：

| 能力 | 配置键 |
|---|---|
| Neo4j | `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 等 Neo4j 配置 |
| Hologres | `HOLOGRES_HOST`、`HOLOGRES_PORT`、`HOLOGRES_DATABASE`、`HOLOGRES_USER`、`HOLOGRES_PASSWORD` |
| Power BI | `POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID` 及语义模型配置 |
| 飞书 | `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_GRAPH_BITABLE_APP_TOKEN` |
| HTML 报告 | `BLOB_READ_WRITE_TOKEN`、`VERCEL_REPORTS_URL` |
| 图片报告 | `VOLCENGINE_ARK_API_KEY`、`VOLCENGINE_ARK_BASE_URL`、`VOLCENGINE_ARK_IMAGE_MODEL` |
| 语义图 | `graph-config.embedding`、`graph-config.entities`、`graph-config.relationships` |

安全规则：

- 禁止提交 `.env`、`config.json`、Bearer Token、API Key、Client Secret 或真实数据库密码。
- 示例一律使用明显占位符，不要把临时测试密钥写进文档或测试 fixture。
- `config.json` 通过只读卷挂载，不复制进 Docker 镜像。
- Token 通过 `.env` 或运行环境注入；泄露后立即轮换并重建容器。

## 8. 本地开发与验证

安装：

```bash
python -m venv .venv
python -m pip install -e .
```

启动：

```bash
export SDA_MCP_TOKEN="replace-with-a-long-random-token"
python -m sda_mcp.server
```

Windows PowerShell 使用：

```powershell
$env:SDA_MCP_TOKEN = "replace-with-a-long-random-token"
python -m sda_mcp.server
```

基础验证：

```bash
python -m pytest -q
```

当前基线：166 passed、7 skipped。真实外部服务测试默认跳过；配置完备后设置 `SDA_INTEGRATION=1`。不要为了让 CI 通过而把真实服务测试改成隐式联网。

提交前至少执行 `python -m pytest -q` 和 `git diff --check`，并确认：

- tool list 的工具数量和名称符合预期。
- 修改过的工具输入/输出 schema 与说明一致。
- 相关 Skill 和 references 已同步。
- 没有真实密钥、临时结果、虚拟环境或缓存进入暂存区。
- 破坏性或付费工具的 annotations、说明和测试没有弱化。

## 9. 服务器部署

当前部署目录约定为 `~/sda-mcp/`，服务监听 `0.0.0.0:3100/mcp`。`docker-compose.yml` 使用 host 网络，以便连接宿主机 Neo4j 和 VPN 内的 Hologres。单机部署以 Git checkout 为代码真相源；`git archive` 只保留为无 Git 环境的备用方式。

服务器前置条件：

- Docker 与 Docker Compose。
- Neo4j 可从容器 host 网络访问，当前通常为 `127.0.0.1:7687`。
- Git；私有仓库使用只读 SSH Deploy Key，不把 Token 写进 remote URL。
- `~/.super-data-analytics/config.json` 已配置并限制文件权限。
- 如 Hologres 仅内网可达，VPN/tun 路由已经连通。

首次发布代码：

```bash
git clone --depth 1 --branch main --single-branch \
  git@github.com:Garcing/super-data-analytics.git ~/sda-mcp
```

`hermes` 当前到 `github.com:443` 的 HTTPS Git 路径超时，但 GitHub SSH 22 端口和现有密钥认证正常，因此部署 remote 必须保持上述 SSH URL。浅克隆足以支持 main 的日常 fast-forward pull；需要回退到浅历史之外的提交时，先执行 `git fetch --unshallow origin` 或按目标提交加深历史。

如果 `~/sda-mcp` 是旧 archive 解压目录，不要直接在其中 `git init`。先 clone 到同级新目录、复制 `.env`、完成 build 验证后再切换；旧目录保留一个发布周期用于回退。

本机配置是唯一真相源。部署前在本机执行以下命令，将已验证的 JSON 安全同步到服务器；脚本会在服务器保留上一份 `.bak`、设置 600 权限并核对 SHA-256，不打印密钥：

```bash
python scripts/sync_server_config.py --host hermes --dry-run
python scripts/sync_server_config.py --host hermes
```

服务器 `~/sda-mcp/.env`：

```dotenv
SDA_MCP_TOKEN=replace-with-a-long-random-token
HOLOGRES_HOST=192.168.5.121
HOLOGRES_PORT=31223
```

服务器差异只放在 `.env`。容器环境变量由 `get_env()` 覆盖同名 `config.json` 值，因此不维护第二份含密钥的 `config-server.json`。

生成随机 Token：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

构建和启动：

```bash
cd ~/sda-mcp
docker compose build
docker compose up -d
docker compose ps
```

无 Token 请求应返回 401：

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:3100/mcp -d '{}'
```

随后使用合法 Token 的 MCP 客户端执行 tool list，并至少冒烟一个不产生写入或费用的工具。不要用 `sync(dry_run=false)`、报告删除或图片生成作为普通健康检查。

## 10. 更新、回退与运维

常规更新：

```bash
cd ~/sda-mcp
git status --short
git pull --ff-only origin main
docker compose up -d --build --force-recreate
docker compose ps
docker compose logs --tail=100
```

`git status --short` 必须没有受跟踪文件改动；若不为空或 `pull --ff-only` 失败，停止部署并检查，不要在服务器上执行 `reset --hard` 或自动合并。`.env` 被 Git 忽略，不影响干净状态。

更新注意事项：

- 改 Python 代码：`git pull --ff-only` 后重新 build/recreate。
- 改 `Dockerfile`、`docker-compose.yml` 或 `pyproject.toml`：同样通过 Git 更新并重新 build。
- 改 `.env` 中的 `SDA_MCP_TOKEN`：执行 `docker compose up -d --force-recreate`。
- 改本机 `config.json`：先本机 `sync(dry_run=true)`，再运行 `scripts/sync_server_config.py`；同步后重建容器以清掉进程缓存。
- 改语义层数据或结构：先 `sync(dry_run=true)`，通过后才执行全量 sync。
- `sync` 属长任务（分钟级），部分 MCP 客户端会超时中断但不代表失败；长调用可用 `scripts/mcp_debug.py call sync`（默认 180 秒超时）。
- 公网入口为 `https://mcp.super-data-analytics.online/mcp`：服务器 Caddy（systemd）终止 TLS 并 `reverse_proxy localhost:3100`，TLS 终止不进 Python 服务；容器内仍监听 `0.0.0.0:3100`。

回退不要修改或强推 Git 历史。服务器切换到已知良好提交并重建：

```bash
cd ~/sda-mcp
git fetch origin
git switch --detach GOOD_COMMIT
docker compose up -d --build --force-recreate
```

恢复跟踪主分支使用 `git switch main && git pull --ff-only origin main`。代码回退不会删除 Neo4j 数据，但如果期间执行过全量 sync，图数据应按对应版本配置重新同步。

常用运维：

| 任务 | 命令或动作 |
|---|---|
| 查看状态 | `docker compose ps` |
| 查看日志 | `docker compose logs -f` 或 `--tail=100` |
| 重启 | `docker compose restart` |
| 重建容器 | `docker compose up -d --force-recreate` |
| 检查本地端点 | 无 Token POST 应为 401，再用 MCP Client tool list |
| 重建语义图 | 先 `sync(dry_run=true)`，再显式 `sync(dry_run=false)` |

部署完成后的验收顺序：

1. 容器处于 running，日志没有循环崩溃。
2. 无 Token 请求返回 401。
3. 合法客户端成功发现 19 个工具。
4. `retrieve_schema`、只读查询或其他低风险代表性工具成功。
5. 若修改语义检索，再运行受治理检索 gold case 或代表性真实问题。
6. 若修改报告/图片能力，只在用户明确允许外部写入或费用时做真实冒烟。

## 11. 文档职责

- `README.md`：面向外部使用者，说明项目价值、能力、架构、快速开始和接入方式。
- `AGENTS.md`：面向维护 Agent，说明代码边界、工具/Skill 映射、变更规则、配置、测试和部署运维。
- `skills/*/SKILL.md`：面向执行分析任务的 Agent，说明何时使用、工作流、证据要求和工具顺序。
- `skills/*/references/`：保存详细契约、方法和可按需加载的背景材料。
- `docs/`：保存仍对架构决策有价值的研究，不堆积已经失效的实施计划。

如果同一内容在多处出现，以代码和测试为行为真相源，以 `AGENTS.md` 为维护流程真相源；更新时减少重复并修正所有指向关系。
