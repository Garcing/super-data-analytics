# super-data-analytics MCP 服务

> Neo4j 2026 的 `SEARCH`、GraphRAG Python、Hybrid Search 与官方 Neo4j MCP 的项目适配结论，见 [`docs/neo4j-graphrag-2026-research.md`](docs/neo4j-graphrag-2026-research.md)。

把整套数据分析技能的确定性执行能力收敛进**一个 Docker 容器**，作为 MCP（Model Context Protocol）服务对外提供。hermes（接飞书/企微）和笔记本只配置一个 URL，不再每台机器调 Python/Node 依赖。

- **实现**：FastMCP（MCP Python SDK v2 `MCPServer`），streamable HTTP（stateless + JSON response），19 个工具。
- **语言**：全部 Python（8 个技能内核 + sync pipeline），in-process 调用。
- **监听**：容器 `0.0.0.0:3100/mcp`，静态 Bearer token 鉴权。
- **对外**：Caddy 反向代理 + 自动 HTTPS，公网入口 `https://mcp.super-data-analytics.online/mcp`。

---

## 1. 架构

```
┌─────────────── 笔记本 / hermes（任意客户端） ──────────────┐
│   本机 Claude        hermes 网关(接飞书/企微)              │
│      │ https+Bearer       │ localhost+Bearer               │
│      ▼                     ▼                               │
│   Caddy :443 ──TLS────► Docker(网络:host)                  │
│   (mcp.super-data-       ┌────────────────────────────┐    │
│    analytics.online)     │ FastMCP streamable HTTP     │    │
│                          │ stateless JSON, :3100       │    │
│                          │ 19 工具, Bearer 校验        │    │
│                          │ in-process 调用 Python 内核 │    │
│                          │ + 飞书开放平台 REST         │    │
│                          └───────────┬────────────────┘    │
│                          127.0.0.1   │ 卷挂载              │
│              ┌───────────────────────┴──────────────┐      │
│              ▼                                     ▼      │
│   Neo4j5(127.0.0.1:7687)              config.json(宿主)    │
│              │                                     （飞书凭证在内）│
│              └─ 不改原 skill 代码树 ─────────────────┘      │
└─────────────────────────┬──────────────────────────────────┘
                VPN(tun0) │                  │ HTTPS
                           ▼                  ▼
          Hologres(内网)        Vercel Blob / 火山方舟 / Power BI / 飞书
```

**两条接入路径，同一 Bearer token：**
- hermes（服务器本地）→ `http://localhost:3100/mcp`
- 笔记本/外部 → `https://mcp.super-data-analytics.online/mcp`（经 Caddy）

### 组件分层

| 层 | 文件 | 职责 |
|---|---|---|
| **服务入口** | `sda_mcp/server.py` | 建 `MCPServer("sda")`、按 `SDA_MCP_TOKEN` 挂 Bearer 鉴权、`run(transport="streamable-http")` |
| **鉴权** | `sda_mcp/auth.py` | `StaticTokenVerifier`（校验 `Authorization: Bearer`，无/错 → 401）|
| **工具注册** | `sda_mcp/tools/` | 5 个分组文件，`@mcp.tool` 把内核包成 19 个工具；`_common.py` 持有唯一 `mcp` 实例 + dataclass→dict |
| **技能内核** | `sda_mcp/skills/` | 8 个干净 Python 内核（纯函数：类型入参 → dataclass → 失败抛 `SkillError`）|
| **配置/错误** | `config.py` / `errors.py` | 读 `~/.super-data-analytics/config.json`；`SkillError` 体系 |

**工具层约定**：入参 Pydantic v2 模型；出参 `dict[str, Any]` 注解（→ structuredContent，不包 `result`）；内核抛 `SkillError` → FastMCP 自动 `isError:true` + 可操作提示；画图返回 `Image` 内容块 + Blob URL 文本（双保险）。工具是 **sync def**，FastMCP 线程池执行。

---

## 2. 19 个工具

hermes 最终看到 `mcp_sda_<工具名>`；本机 Claude 看到 `mcp__sda__<工具名>`。

| 分组 | 工具 | 说明 |
|---|---|---|
| **取数** | `sql_query` / `sql_schema` | Hologres SQL（psycopg）|
| | `powerbi_schema` / `powerbi_query` | Power BI Fabric MCP（msal + 202 轮询）；模型列表见 config.json，不另开工具 |
| **语义检索** | `retrieve_search` | 默认 Hybrid（fastembed 向量 + CJK 全文 + RRF + 精确实体名）+ 批量图扩展；`strategy=vector` 可回退 |
| | `retrieve_cypher` / `retrieve_schema` | Cypher / Neo4j 实时精简 schema |
| | `retrieve_doc_read` / `retrieve_doc_update` | 飞书文档读 / 覆盖写正文（模板正文在 docx）|
| | `sync` | 预检或全量重建：飞书多维表 → Neo4j → ONNX 向量 |
| **分析** | `contribute` / `forecast` / `impact` | 贡献度归因 / 时序预测 / 效果评估（AB/DID/ROI）|
| **可视化** | `chart` | matplotlib 渲染 → ImageContent + Blob URL |
| **报告** | `report_html_publish` / `_list` / `_get` / `_delete` | HTML 报告（Vercel Blob，索引乐观锁）|
| | `report_image_generate` | 火山方舟 Seedream 单图生成；默认返回下载 URL，可选 MCP 图片块 |

> 报告模板已并入语义层：模板是「报告模板」多维表里的行（`retrieve_search`/`retrieve_cypher` 发现），正文在链接的 docx（`retrieve_doc_read` 读、`retrieve_doc_update` 改）。不再单列模板工具组。

> `report_image_generate` 走火山方舟。旧 `building-reports` Node CLI 不在 MCP 升级范围内。

### 2.1 图片报告生成契约

`report_image_generate` 保持工具名稳定，但 provider 默认改为火山方舟图片生成 API：

- 单次同步 HTTP 请求，不暴露后台 `task_id/status` 轮询语义。
- 默认 `response_format=url`，结构化结果直接返回方舟提供的 JPEG 下载 URL，不上传 Vercel Blob。
- 调用 Agent 可显式选择 `response_format=b64_json`；服务端将 Base64 解码成 MCP `ImageContent`，不会把大段 Base64 放进结构化结果。
- 首版不发送 `stream` 和 `sequential_image_generation`，使用 API 默认的非流式单图语义，兼容 Seedream 5.0 Pro。
- `model` 可传 Model ID 或 Endpoint ID；不传时读取 `VOLCENGINE_ARK_IMAGE_MODEL`，因此兼容协议内的新模型只需改配置。
- 图片生成 POST 不自动重试，避免响应丢失后重复生成和计费。

**真实冒烟基线（2026-08-14）**：`doubao-seedream-5-0-pro-260628`、`size=2K`、`response_format=url`、提示词指定 3:4，成功返回 `1776x2368` JPEG；耗时约 92 秒，`usage.generated_images=1`、`total_tokens=16428`。返回的 TOS 签名 URL 本次带 `X-Tos-Expires=86400`（24 小时），调用方应在有效期内下载保存。测试图的中文 KPI、8 个趋势数值和结论均核对正确；全程未上传 Vercel Blob。

### 2.2 GraphRAG 检索架构（维护重点）

当前语义检索是一套面向受治理元数据的轻量 Hybrid GraphRAG：使用 Neo4j 2026 的原生索引和查询能力，保留本地 Fastembed，由 SDA 负责多实体路由、排序融合和图上下文组装。当前**没有**引入 `neo4j-graphrag` Python 包，也**没有**部署 Neo4j 官方 MCP Server。

```text
飞书结构化元数据
  → sync 建立实体和关系
  → 按实体配置生成 search_text
  → Fastembed 生成 embedding
  → 每类实体各建一个 vector index 和 CJK full-text index

retrieve_search(question, targets, top_k, strategy="hybrid")
  → 一次 Fastembed query embedding
  → 每个 target 分别执行 vector SEARCH 和 CJK full-text search
  → 从召回候选中识别名称 / ID / 别名的精确命中
  → Weighted RRF 融合并截取全局 top_k
  → 仅对最终候选批量扩展图邻居
  → properties + context + retrieval evidence
```

职责边界：

| 组件 | 负责 | 不负责 |
|---|---|---|
| Neo4j | vector/full-text 索引、Cypher `SEARCH`、图存储与关系遍历 | embedding 模型托管、业务实体路由、跨来源排序 |
| Fastembed | 本地生成文档和问题的 512 维 embedding | 全文召回、图扩展、融合排序 |
| SDA 检索内核 | `targets` 路由、精确命中、WRRF、批量图扩展、稳定返回契约 | 通用自然语言生成 Cypher |
| SDA FastMCP | 对外暴露受约束的高层工具和结构化结果 | 代理或嵌套 Neo4j 官方 MCP |

这套边界的目的不是重复造一个通用 GraphRAG 框架，而是让 Neo4j 执行底层检索，让 SDA 只维护与八类受治理实体、动态关系配置和业务返回格式有关的薄编排层。

#### 数据与索引契约

- `graph-config.entities.<label>.search_fields` 决定该实体的 `search_text`；字段集合变化后必须重新生成 `search_text` 并重算 embedding。
- `graph-config.entities.<label>.vector_index=false` 的实体不参与向量、全文和 Hybrid 召回。
- 向量索引命名为 `<label>_embedding_index`，索引 `n.embedding`，相似度为 `cosine`。
- 全文索引命名为 `<label>_search_text_index`，索引 `n.search_text`，analyzer 固定为 `cjk`。
- 当前 embedding 默认为 `BAAI/bge-small-zh-v1.5`、512 维；sync 写入 `embedding_model`、`embedding_dimensions` 和 `embedding_updated_at` 便于审计。
- 写入节点和查询问题必须使用同一个 embedding 模型、维度和版本。更换模型或维度时，必须全量重算 embedding 并重建不兼容的向量索引，不能混用旧向量。
- 索引名称不靠配置猜测：查询侧通过 `SHOW VECTOR INDEXES` / `SHOW FULLTEXT INDEXES` 按 label 发现并在 client 生命周期内缓存。
- Neo4j 数据库仅供 SDA 使用。全量 sync 会清空节点/关系、全部约束和所有非 `LOOKUP` 索引，再按当前配置重建；历史实体不会残留 schema 对象。
- sync 为每类实体的 `key_field` 创建唯一约束，使其成为 Neo4j 内可发现的稳定标识字段。

#### 查询、融合与兼容契约

- `strategy=hybrid` 是默认生产路径；`strategy=vector` 保留为故障回退和 A/B 基线。
- Hybrid 对每个 target 的向量和全文各取 `source_k = top_k × 2` 个候选，再融合成**全局** `top_k`；纯向量模式保持历史行为，即每个目标索引取 `top_k` 后按 cosine 排序。
- 精确命中只检查受治理的 ID、名称和别名类字段，不扫描定义等长文本，避免“定义中提到另一个指标”造成错误加权。
- 融合使用 Weighted RRF：向量权重 `1.0`、全文权重 `1.0`、精确命中权重 `1.2`、`rrf_k=60`。cosine 与 Lucene score 量纲不同，禁止直接相加或跨索引比较原始分数。
- Neo4j 2026.01+ 使用 Cypher 25 `SEARCH`；Neo4j 5.x / 2025.x 回退 `db.index.vector.queryNodes`。不要为了消除弃用日志改成逐节点 cosine 全表扫描。
- 图扩展发生在融合和截断之后，按关系及方向批量查询；每个命中、每类关系最多保留 20 个邻居，避免命中数 × 关系数的查询往返。

Hybrid 返回中，顶层 `score` 为向后兼容字段，始终表示 vector cosine；仅被全文召回的结果为 `0`。真实融合顺序应看 `retrieval`：

| 字段 | 含义 |
|---|---|
| `fusion_score` | Weighted RRF 分数，只用于本次候选排序，不是概率 |
| `vector_score` / `fulltext_score` | 各检索源的原始分数；两者不可直接比较 |
| `vector_rank` / `lexical_rank` / `exact_rank` | 候选在各来源中的独立排名 |
| `exact_match` | 命中的受治理名称、ID 或别名；未命中为 `null` |

#### `retrieve_schema` 返回契约

`retrieve_schema` 完全从 Neo4j 实时内省，不读取 `graph-config`。它只返回大模型编写 Cypher 所需的内容：

```json
{
  "nodes": {
    "指标": {
      "properties": {"指标ID": "STRING", "指标名称": "STRING"},
      "unique": ["指标ID", "指标名称"]
    }
  },
  "relationships": ["(:`指标`)-[:`使用`]->(:`表`)"]
}
```

- 节点属性和类型来自 `db.schema.nodeTypeProperties()`。
- `unique` 来自当前实际标签对应的唯一约束；无节点的历史约束不会返回。
- 关系路径来自数据库中实际存在的有向边。
- 不返回索引详情、embedding 配置、飞书 `table_id` 或建边规则，避免占用 MCP 上下文。
- `embedding`、`search_text`、`embedding_model`、`embedding_dimensions`、`embedding_updated_at` 属于检索内部属性，会被过滤。
- 图为空时返回可操作错误，提示先执行 `sync`，不会用遗留约束拼凑 schema。

#### 与 Neo4j 官方 GraphRAG / MCP 的关系

| 官方能力 | 当前是否使用 | 后续定位 |
|---|---:|---|
| Neo4j vector index、full-text index、Cypher 25 `SEARCH` | 是 | 当前生产底座 |
| `neo4j-graphrag` 的 `VectorCypherRetriever` / `HybridCypherRetriever` | 否 | 只能通过 feature flag 做查询侧 A/B，评测胜出后再替换 |
| GraphRAG `Embedder` 和云端 embedding provider | 否 | 现有 Fastembed 可薄包装；使用远程 provider 才会产生外部 API、费用和数据出境问题 |
| Neo4j KG Builder / Text2Cypher / GDS FastRP | 否 | 仅在真实失败案例证明有价值时实验，不纳入默认主链 |
| Neo4j 官方 MCP Server | 否 | 可作为开发者只读诊断 sidecar，不代理进 SDA MCP、不暴露给业务 Agent |

完整调研、取舍和候选实验见 [`docs/neo4j-graphrag-2026-research.md`](docs/neo4j-graphrag-2026-research.md)。

---

## 3. 部署

### 前置（服务器：腾讯云 lighthouse，已具备）
- Docker + Compose、Neo4j（`127.0.0.1:7687`）、Caddy（active）。
- `~/.super-data-analytics/config.json`（所有 key 真实值，含飞书自建应用 `FEISHU_APP_ID`/`FEISHU_APP_SECRET`）。
- VPN（openvpn tun0）连 Hologres 内网。

### 3.1 代码就位
代码在分支 `spec/mcp-server-design` 的 `mcp/` 目录。服务器部署目录 `~/sda-mcp/`：
```bash
git archive --format=tar.gz spec/mcp-server-design -o mcp.tgz -- mcp/
# scp 到服务器后：
mkdir -p ~/sda-mcp && tar -xzf mcp.tgz -C ~/sda-mcp --strip-components=1
```

### 3.2 配置 token
`~/sda-mcp/.env`（compose 自动读，**不进镜像、不进 git**）：
```
SDA_MCP_TOKEN=<一个长随机串>
```
生成：`python -c "import secrets; print(secrets.token_urlsafe(32))"`

### 3.3 构建并启动
```bash
cd ~/sda-mcp
docker compose build        # 首次 ~5-10min；含 CJK 字体 + bge ONNX 模型（无 Node/lark-cli）
docker compose up -d        # host 网络，仅挂 config.json
```
镜像 `sda-mcp-sda-mcp:latest`（~1.7GB）。容器 `sda-mcp`，`restart: unless-stopped`。

### 3.4 冒烟测试（服务器本地）
```bash
# 鉴权（无 token 期望 401）
curl -sS -o /dev/null -w '%{http_code}' -X POST http://localhost:3100/mcp -d '{}'
# 工具数 + 只读调用（in-memory，绕过 HTTP/鉴权）
docker exec sda-mcp sh -c "echo <base64 脚本> | base64 -d | python"
#   脚本：async with Client(mcp) as c: print(len((await c.list_tools()).tools))
```

### 3.5 卷挂载（docker-compose.yml 关键项）
```yaml
network_mode: host
environment:
  SDA_MCP_TOKEN: ${SDA_MCP_TOKEN}
  SDA_CONFIG_PATH: /root/.super-data-analytics/config.json
volumes:
  - ${HOME}/.super-data-analytics/config.json:/root/.super-data-analytics/config.json:ro
```
> 飞书走开放平台 REST：凭证（`FEISHU_APP_ID`/`FEISHU_APP_SECRET`）在 config.json 的 `env` 块，无需挂 lark-cli 密钥链。

### 3.6 重新部署（改代码后更新服务器）

服务器 `~/sda-mcp/` 已就绪、`.env`/config.json 已配，日常更新代码只需**覆盖代码层 + 重建容器**：

```bash
# 1) 本机：打包 mcp/（分支 spec/mcp-server-design）
git archive --format=tar.gz spec/mcp-server-design -o mcp.tgz -- mcp/
scp mcp.tgz hermes:~/

# 2) 服务器：解压覆盖（--strip-components=1 去掉 mcp/ 前缀）
ssh hermes
cd ~/sda-mcp && tar -xzf ~/mcp.tgz -C . --strip-components=1

# 3) 重建容器（代码层在 Dockerfile 靠后，分层缓存命中 → 远快于首次）
docker compose build && docker compose up -d --force-recreate

# 4) 冒烟（见 3.4）；若语义层多维表有改动再跑一次 sync（见 §6）
```

**只改了一两个 `.py` 的快路径**（省去 archive 全量传输）：
```bash
scp mcp/sda_mcp/<file>.py hermes:~/sda-mcp/sda_mcp/<file>.py
# 子目录文件记得对齐路径，如 skills/、tools/
ssh hermes 'cd ~/sda-mcp && docker compose build && docker compose up -d --force-recreate'
```

重新部署**要注意**：
- **config.json 新增 key 时**：本机 `~/.super-data-analytics/config.json` 改完后，**同步到服务器宿主**的同名文件（卷挂载的是宿主那份；容器 `:ro` 只读）。改完无需重建容器——下次工具调用即生效，但 sync 等长任务建议重建清掉进程内缓存。
- **`.env`（`SDA_MCP_TOKEN`）改动**：compose 读 `.env`，需 `docker compose up -d --force-recreate` 重建才生效。
- **`Dockerfile`/`docker-compose.yml`/`pyproject.toml` 改动**：必须走 `git archive` 全量覆盖 + `build`（scp 单文件不够）。
- **重建不影响 hermes**：同一 URL + 同一 token，容器名不变，hermes 无需 `gateway restart`。
- **改了飞书多维表结构（加字段/改类型）后**：跑一次 `sync`（全量）刷新 Neo4j + 向量；sync 会先清空图再重建，幂等。
- **回退**：`git checkout <旧commit> -- mcp/` → 重新 archive/覆盖 → 重建。Neo4j 数据不丢（除非 sync 重灌）。

---

## 4. hermes 接入（飞书/企微）

hermes 以 systemd user service 跑（`hermes-gateway.service`），`config.yaml` 加：
```yaml
mcp_servers:
  sda:
    url: "http://localhost:3100/mcp"
    headers:
      Authorization: "Bearer <SDA_MCP_TOKEN>"
```
重启：`~/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway restart`
验证：`... mcp test sda` → `✓ Connected` + `✓ Tools discovered: 19`。

---

## 5. 公网入口（笔记本/外部接入）

### DNS + 防火墙
- 华为云 DNS：`mcp.super-data-analytics.online` A 记录 → 服务器公网 IP（apex/www 仍指 Vercel，不动）。
- 腾讯云安全组：放行入站 TCP 443（80 也开，签证书用）。

### Caddy 站点块（追加到 `/etc/caddy/Caddyfile`）
```
mcp.super-data-analytics.online {
	reverse_proxy localhost:3100
}
```
`sudo systemctl reload caddy` → 自动签 Let's Encrypt 证书（HTTP-01，80 是 Caddy 自己）。
验证：`curl -o /dev/null -w '%{http_code}' -X POST https://mcp.super-data-analytics.online/mcp -d '{}'` → 401。

### 本机 Claude Code 接入
`~/.claude.json` 的 `mcpServers` 加（user scope，跨项目、不进 git）：
```json
{
  "mcpServers": {
    "sda": {
      "type": "http",
      "url": "https://mcp.super-data-analytics.online/mcp",
      "headers": { "Authorization": "Bearer <SDA_MCP_TOKEN>" }
    }
  }
}
```
重启 Claude 会话 → 出现 `mcp__sda__*` 工具。

---

## 6. 运维

| 操作 | 命令 |
|---|---|
| 看日志 | `docker compose logs -f`（或 `--tail=50`）|
| 重启容器 | `docker compose restart` |
| 改代码后更新 | 改本地→提交→传 `sda_mcp/` 到 `~/sda-mcp/`→`docker compose build && docker compose up -d --force-recreate`（代码层靠后，重建快）|
| 重新灌图数据 | 调 `sync` 工具；每次都完整重建图、约束、索引和向量 |
| 备份 hermes 配置 | `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%s)` |
| 回退 hermes | 删 `mcp_servers` 段 + `gateway restart` |

### sync（语义层数据）
首次部署后 Neo4j 是空的，**必须跑一次 `sync`** 才能检索：
- `sync` 只保留 `dry_run` 参数，不再支持 `only` 或 `force_embed`；传入旧参数会直接校验失败，避免静默触发全量重建。
- `dry_run=true`：拉取并校验全部飞书数据、主键完整性、配置、Fastembed 模型和 Neo4j 连接，不执行任何数据库写入。
- `dry_run=false`（默认）：预检通过后，清空节点/关系、全部约束和所有非 `LOOKUP` 索引，再完整重建唯一约束、节点、关系、`search_text`、向量/全文索引和 embedding。
- 可能失败的外部准备工作全部发生在清库前；飞书无记录、主键重复、模型不可用或 Neo4j 不可连接时会停止写库。空主键记录沿用跳过行为，并在结果的 `warnings` 中明确报告。
- 向量用 **fastembed(ONNX)**，与查询侧同源 → 自洽，无 ONNX/PyTorch 混用风险。

### 检索基线

`tests/retrieval_gold.json` 保存 30 条受治理实体检索 gold case。评估逻辑已经并入 pytest，
真实质量回归默认跳过；显式启用后会连续评估 vector 与 hybrid，全程只读且不调用 LLM：

```powershell
cd mcp
$env:SDA_INTEGRATION="1"
python -m pytest -q -s tests/test_retrieval_quality.py
```

当前本地图（2026-08-14）Hybrid 相对纯向量：Recall@1 `70% → 80%`、Recall@5 `93.3% → 100%`、MRR@5 `0.794 → 0.889`。

### GraphRAG 维护与升级检查表

任何 embedding 模型、`search_fields`、分词器、候选池、融合权重、RRF 参数、精确命中规则、图扩展规则或 Neo4j/Driver 大版本变更，都按以下顺序验收：

1. 把新发现的真实失败问题先加入 `tests/retrieval_gold.json`，明确目标 label、稳定主键和值；不要只为已有 30 题调参。
2. 先跑 `strategy=vector` 保存基线，再跑 `strategy=hybrid`；至少比较 Recall@1、Recall@5、MRR@5、平均延迟和 P95。
3. 检查 `retrieval` evidence，确认提升来自预期来源，且没有把 Lucene 分数误当 cosine 或把长定义当精确命中。
4. 变更模型、维度或 `search_fields` 时，在测试图执行 `sync(dry_run=true)`，通过后再全量 sync；确认所有 vector/full-text index 为 `ONLINE`。
5. 跑完整测试：`cd mcp && python -m pytest -q`，再用真实 Neo4j 做代表性冒烟；测试通过不等于检索质量通过。
6. 保留 `strategy=vector` 回退至少一个发布周期。只有新方案在质量、P95、镜像体积、外部依赖和错误可观测性上整体更优，才替换默认路径。

建议的升级优先级是：扩充线上失败评测集 → 查询改写/同义词实验 → reranker A/B → 官方 Retriever A/B → 有证据后再考虑 GDS 结构向量。不要仅因官方新增组件而改写主链。

---

## 7. 已知限制与踩坑记录

| 项 | 说明 |
|---|---|
| **方舟图片 URL** | 真实冒烟返回的 TOS 签名 URL 有效期为 24 小时；需要长期保留时由调用方及时下载，不自动上传 Blob。 |
| **HuggingFace 不通** | 服务器直连 HF 超时。Dockerfile 固化 `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1`（否则 fastembed 拉模型/Xet 401 失败）。 |
| **中国镜像** | Dockerfile 用 tuna apt/PyPI；否则构建从中国极慢/超时。 |
| **飞书自建应用授权** | graph 多维表、`retrieve_doc_read` 目标文档、报告模板 docx（`retrieve_doc_update` 要写）须共享给应用（`tenant_access_token` = 应用身份）。凭证 `FEISHU_APP_ID`/`FEISHU_APP_SECRET` 在 config.json。 |
| **sync 字段类型清洗** | 开放平台多维表各类型值结构差异大，`_simplify_value` 逐类型拍平成 Neo4j 原生类型（str/int/float/bool/list[str]），否则 `SET n += $props` 报 Map 类型错。**支持**：Text/URL `[{text}]`/`{text,link}`→拼串（换行保留\n）；Number(2) 返回**字符串**→转数字；DateTime(5) ms→格式化；Checkbox bool；单选/多选。**公式/lookup 按结果 `data_type`(int) 分派**（不用 ui_type——设过格式后可能缺失）：文本/数字/日期（ms 毫秒 vs Excel 日序号按量级区分）/单选多选（返回**选项 ID** 用表级 optId→name 映射反查）；防御性兼容文档示例的 `{type,value}` 包装。**不支持**（语义层用不到、值结构复杂）：人员/附件/群组/位置/系统时间/关联 → 返回 `（X字段，暂不支持取值）` 提示给 agent，不做清洗（降低维护成本）。 |
| **Hologres** | 走 VPN(tun0)；`connect_timeout=20s`（VPN 偶发握手慢）。空字段名 psycopg 返回空串，内核已 `name or col_N` 兜底。 |
| **Neo4j `Record.keys()`** | 是方法不是属性，`run_cypher` 必须 `rec.keys()`。 |
| **Vercel Blob 索引** | head API 不返回 etag；索引用 `uploaded_at` cache-buster 绕 CDN 60s 陈旧，取 fetch 响应 etag 给写时 ifMatch。 |
| **内存** | 服务器 3.6GB（可用 ~2GB）。选 ONNX 而非 PyTorch；FastMCP 单进程；镜像 ~1.7GB。 |

---

## 8. 配置与凭证

唯一来源：宿主 `~/.super-data-analytics/config.json`（卷挂载，`SDA_CONFIG_PATH` 指向），镜像零密钥。用到：

| 块 | key |
|---|---|
| `env` | `NEO4J_*`、`HOLOGRES_*`、`POWERBI_*`、`BLOB_READ_WRITE_TOKEN`、`VERCEL_REPORTS_URL`、`VOLCENGINE_ARK_API_KEY`、`VOLCENGINE_ARK_BASE_URL`、`VOLCENGINE_ARK_IMAGE_MODEL`、`FEISHU_APP_ID`/`FEISHU_APP_SECRET`（自建应用，tenant token 鉴权）、`FEISHU_GRAPH_BITABLE_APP_TOKEN` |
| `graph-config` | `embedding.model`（`BAAI/bge-small-zh-v1.5`）、`entities`、`relationships` |

图片生成配置示例：

```json
{
  "env": {
    "VOLCENGINE_ARK_API_KEY": "粘贴方舟 API Key",
    "VOLCENGINE_ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
    "VOLCENGINE_ARK_IMAGE_MODEL": "doubao-seedream-5-0-pro-260628"
  }
}
```

缺必填 key → `ConfigError`（可操作提示）；base URL、默认模型等可选 key 走 `load_config()` 并使用代码默认值。

---

## 9. 开发

- **铁律**：原 skill 目录树（`building-reports/`、`querying-data/` 等）**零改动**，作对照基准。所有新代码只在 `mcp/`。
- 测试：`cd mcp && python -m pytest -q`（当前 157 通过 + 7 集成 skip）。mock 单元测试 + 可选集成对照（`SDA_INTEGRATION=1`）。
- 计划/设计文档：`docs/superpowers/specs/2026-08-09-mcp-server-design.md`、`docs/superpowers/plans/2026-08-09-subproject-*.md`。
- MCP 设计参考：`/mcp-builder` 技能（Anthropic 权威 MCP 手册）。
