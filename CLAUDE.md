# CLAUDE.md — super-data-analytics

数据分析技能套件 + MCP 服务。本文件每次新对话自动加载，提供项目上下文。

## 这是什么
- **技能套件**：10 个 skill 模块（取数、检索、分析、画图、报告、模板…），原代码在各自目录（`querying-data/`、`retrieving-context/`、`building-reports/` 等），由 agent 经 SKILL.md 路由调用。
- **MCP 服务**（`mcp/`）：把 8 个执行技能的确定性能力收敛进一个 Docker 容器，作 MCP 服务对外提供，供 hermes（接飞书/企微）和笔记本用，消除每台机器调依赖的痛苦。**这是当前主要工作。**

## 铁律（不可违反）
- **绝不改动原 skill 目录树**（`building-reports/`、`querying-data/`、`retrieving-context/`、`visualizing-data/`、`using-templates/`、`diagnosing-data/`、`predicting-data/`、`evaluating-data/`）——它们是对照基准，保持字节不变。
- 所有 MCP 新代码**只放 `mcp/`**。
- 用户是数据分析师，**只读 Python**；Node 技能已重写为 Python。

## MCP 服务现状（分支 `spec/mcp-server-design`）
- **23 个工具**（`sda_mcp/sql_query`、`retrieve_search`、`sync`、`chart`、`report_html_*`、`template_*` 等），FastMCP（MCP SDK v2 `MCPServer`）streamable HTTP。
- **已部署**在腾讯云服务器：容器 `sda-mcp`（host 网络 :3100），hermes 已接（飞书/企微可用），公网入口 `https://mcp.super-data-analytics.online/mcp`（Caddy 自动 HTTPS，静态 Bearer）。
- **8 个 Python 内核** + sync pipeline 在 `mcp/sda_mcp/skills/`；测试 144 通过 + 7 集成 skip。
- **唯一未启用**：`report_image_generate`（apimart，服务器无代理；本机走代理可用）。

## 关键路径
- 代码：`mcp/sda_mcp/`（`server.py` 入口、`auth.py` 鉴权、`tools/` 工具、`skills/` 内核、`config.py`/`errors.py`）。
- 容器文件：`mcp/Dockerfile`、`mcp/docker-compose.yml`、`mcp/Caddyfile`。
- 详细文档：**`mcp/README.md`**（架构+部署+运维+踩坑，最全）。
- 设计/计划：`docs/superpowers/specs/2026-08-09-mcp-server-design.md`、`docs/superpowers/plans/2026-08-09-subproject-*.md`。
- 配置（凭证）：`~/.super-data-analytics/config.json`（NEO4J/HOLOGRES/POWERBI/BLOB/APIMART/FEISHU_* + graph-config）。

## 部署要点（详见 mcp/README.md）
- 服务器 `~/sda-mcp/`（git archive 传输）；`.env` 存 `SDA_MCP_TOKEN`。
- 卷挂载：仅 `config.json`（飞书走开放平台 REST，凭证 `FEISHU_APP_ID`/`FEISHU_APP_SECRET` 在 config.json，不再挂 lark-cli 密钥链）。
- hermes config.yaml 的 `mcp_servers.sda` → `gateway restart`。
- 构建用中国镜像（tuna apt/PyPI）；fastembed 模型靠 `HF_ENDPOINT=hf-mirror.com` + `HF_HUB_DISABLE_XET=1`。

## 本机接入 MCP
- `~/.claude.json` 的 `mcpServers.sda`（user scope，已配）→ 任何新对话自动有 `mcp__sda__*` 工具。
- token 存在 `~/.sda_mcp_token.txt`。

## 常用命令
```bash
cd mcp && python -m pytest -q                      # 测试
cd ~/sda-mcp && docker compose logs -f             # 服务器日志
cd ~/sda-mcp && docker compose up -d --force-recreate  # 改代码后重建
# hermes 重启：~/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway restart
```

## 踩过的坑（别重蹈）
- 飞书自建应用（`tenant_access_token`）须把模板文件夹 / graph 多维表 / retrieve_doc 目标文档**共享给应用**，否则权限报错；凭证 `FEISHU_APP_ID`/`FEISHU_APP_SECRET` 在 config.json。
- Neo4j `Record.keys()` 是方法（要加 `()`）。
- Vercel Blob head API 不返回 etag → 索引用 `uploaded_at` cache-buster。
- HuggingFace 中国不通 → hf-mirror + 关 Xet。
- apimart 服务器不通（无代理）。
- 飞书 docx↔markdown：读走 `docs/v1/content`（非 docx/v1）；写走 convert + 「创建嵌套块」descendant 接口（body `{children_id, descendants}`，表格 block 剥 `table.property.merge_info`）。

## MCP 权威参考
`/mcp-builder` 技能（Anthropic 官方 MCP 手册）——不确定的 MCP 用法先查它。
