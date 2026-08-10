# super-data-analytics MCP 服务

把整套数据分析技能的确定性执行能力收敛进**一个 Docker 容器**，作为 MCP（Model Context Protocol）服务对外提供。hermes（接飞书/企微）和笔记本只配置一个 URL，不再每台机器调 Python/Node 依赖。

- **实现**：FastMCP（MCP Python SDK v2 `MCPServer`），streamable HTTP（stateless + JSON response），24 个工具。
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
│                          │ 24 工具, Bearer 校验        │    │
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
          Hologres(内网)        Vercel Blob / apimart / Power BI / 飞书
```

**两条接入路径，同一 Bearer token：**
- hermes（服务器本地）→ `http://localhost:3100/mcp`
- 笔记本/外部 → `https://mcp.super-data-analytics.online/mcp`（经 Caddy）

### 组件分层

| 层 | 文件 | 职责 |
|---|---|---|
| **服务入口** | `sda_mcp/server.py` | 建 `MCPServer("sda")`、按 `SDA_MCP_TOKEN` 挂 Bearer 鉴权、`run(transport="streamable-http")` |
| **鉴权** | `sda_mcp/auth.py` | `StaticTokenVerifier`（校验 `Authorization: Bearer`，无/错 → 401）|
| **工具注册** | `sda_mcp/tools/` | 6 个分组文件，`@mcp.tool` 把内核包成 24 个工具；`_common.py` 持有唯一 `mcp` 实例 + dataclass→dict |
| **技能内核** | `sda_mcp/skills/` | 8 个干净 Python 内核（纯函数：类型入参 → dataclass → 失败抛 `SkillError`）|
| **配置/错误** | `config.py` / `errors.py` | 读 `~/.super-data-analytics/config.json`；`SkillError` 体系 |

**工具层约定**：入参 Pydantic v2 模型；出参 `dict[str, Any]` 注解（→ structuredContent，不包 `result`）；内核抛 `SkillError` → FastMCP 自动 `isError:true` + 可操作提示；画图返回 `Image` 内容块 + Blob URL 文本（双保险）。工具是 **sync def**，FastMCP 线程池执行。

---

## 2. 24 个工具

hermes 最终看到 `mcp_sda_<工具名>`；本机 Claude 看到 `mcp__sda__<工具名>`。

| 分组 | 工具 | 说明 |
|---|---|---|
| **取数** | `sql_query` / `sql_schema` | Hologres SQL（psycopg）|
| | `powerbi_list_models` / `powerbi_schema` / `powerbi_query` | Power BI Fabric MCP（msal + 202 轮询）|
| **语义检索** | `retrieve_search` | 向量检索（fastembed ONNX）+ 图扩展上下文 |
| | `retrieve_cypher` / `retrieve_schema` / `retrieve_doc` | Cypher / 图 schema / 飞书文档 |
| | `sync` | 飞书多维表 → Neo4j → ONNX 向量（首次或刷新）|
| **分析** | `contribute` / `forecast` / `impact` | 贡献度归因 / 时序预测 / 效果评估（AB/DID/ROI）|
| **可视化** | `chart` | matplotlib 渲染 → ImageContent + Blob URL |
| **报告** | `report_html_publish` / `_list` / `_get` / `_delete` | HTML 报告（Vercel Blob，索引乐观锁）|
| | `report_image_generate` | apimart gpt-image-2 异步生图（最长 180s）|
| **模板** | `template_list` / `_read` / `_create` / `_update` / `_delete` | 飞书模板文档（开放平台 REST）|

> `report_image_generate` 在**服务器无代理时不可用**（apimart 不通）；本机走代理可用。其余 23 个服务器全可用。

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
验证：`... mcp test sda` → `✓ Connected` + `✓ Tools discovered: 24`。

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
| 重新灌图数据 | 调 `sync` 工具（full）；或 `sync` 带 `force_embed=true` 强制重算向量 |
| 备份 hermes 配置 | `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%s)` |
| 回退 hermes | 删 `mcp_servers` 段 + `gateway restart` |

### sync（语义层数据）
首次部署后 Neo4j 是空的，**必须跑一次 `sync`** 才能检索：
- 全量：`sync`（清空+重建图+生成 ONNX 向量）。
- 只跑某阶段：`sync` with `only=fetch|graph|embed`。
- 向量用 **fastembed(ONNX)**，与查询侧同源 → 自洽，无 ONNX/PyTorch 混用风险。

---

## 7. 已知限制与踩坑记录

| 项 | 说明 |
|---|---|
| **apimart 生图** | 服务器直连 `api.apimart.ai` 超时（无代理）。`report_image_generate` 仅本机走代理可用。给容器加 `HTTPS_PROXY` 即可服务器启用。 |
| **HuggingFace 不通** | 服务器直连 HF 超时。Dockerfile 固化 `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1`（否则 fastembed 拉模型/Xet 401 失败）。 |
| **中国镜像** | Dockerfile 用 tuna apt/PyPI；否则构建从中国极慢/超时。 |
| **飞书自建应用授权** | 模板文件夹、graph 多维表、retrieve_doc 目标文档须共享给应用（`tenant_access_token` = 应用身份）。凭证 `FEISHU_APP_ID`/`FEISHU_APP_SECRET` 在 config.json。 |
| **sync 字段类型拍平** | 开放平台多维表记录里，超链接(type=15) 返回 `{text,link}` 裸 dict、公式(20)/查找引用(19) 返回 `[{text,type}]` 片段数组。`_simplify_value` 必须全部拍平成可读串再写 Neo4j，否则 `SET n += $props` 报 Map 类型错。旧 lark-cli 把单元格格式化成串，故旧流水线无此问题。 |
| **Hologres** | 走 VPN(tun0)；`connect_timeout=20s`（VPN 偶发握手慢）。空字段名 psycopg 返回空串，内核已 `name or col_N` 兜底。 |
| **Neo4j `Record.keys()`** | 是方法不是属性，`run_cypher` 必须 `rec.keys()`。 |
| **Vercel Blob 索引** | head API 不返回 etag；索引用 `uploaded_at` cache-buster 绕 CDN 60s 陈旧，取 fetch 响应 etag 给写时 ifMatch。 |
| **内存** | 服务器 3.6GB（可用 ~2GB）。选 ONNX 而非 PyTorch；FastMCP 单进程；镜像 ~1.7GB。 |

---

## 8. 配置与凭证

唯一来源：宿主 `~/.super-data-analytics/config.json`（卷挂载，`SDA_CONFIG_PATH` 指向），镜像零密钥。用到：

| 块 | key |
|---|---|
| `env` | `NEO4J_*`、`HOLOGRES_*`、`POWERBI_*`、`BLOB_READ_WRITE_TOKEN`、`VERCEL_REPORTS_URL`、`APIMART_API_KEY`/`APIMART_BASE_URL`、`FEISHU_APP_ID`/`FEISHU_APP_SECRET`（自建应用，tenant token 鉴权）、`FEISHU_GRAPH_BITABLE_APP_TOKEN`、`FEISHU_TEMPLATE_FOLDER_TOKEN`、`FEISHU_TEMPLATE_DELETE_PASSWORD` |
| `graph-config` | `embedding.model`（`BAAI/bge-small-zh-v1.5`）、`entities`、`relationships` |
| `powerbi-semantic-models` | Power BI 语义模型列表 |

缺必填 key → `ConfigError`（可操作提示）；可选 key（如 `APIMART_BASE_URL`）走 `load_config()` 不报错。

---

## 9. 开发

- **铁律**：原 skill 目录树（`building-reports/`、`querying-data/` 等）**零改动**，作对照基准。所有新代码只在 `mcp/`。
- 测试：`cd mcp && python -m pytest -q`（110 通过 + 6 集成 skip）。mock 单元测试 + 可选集成对照（`SDA_INTEGRATION=1`）。
- 计划/设计文档：`docs/superpowers/specs/2026-08-09-mcp-server-design.md`、`docs/superpowers/plans/2026-08-09-subproject-*.md`。
- MCP 设计参考：`/mcp-builder` 技能（Anthropic 权威 MCP 手册）。
