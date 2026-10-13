# SDA 测试环境 Runbook（mcp-test）

独立于生产（3100/7687）的第二套 SDA MCP 实例 + 语义层 Neo4j，用于新项目语义层实体建模验证。2026-10-12 搭建并验收通过。

**边界**：容器编排与凭证全部在服务器 `~/sda-test/`，刻意不进本仓库 Git；仓库内与此环境相关的只有两处——根目录 `Caddyfile` 的 `mcp-test` 站点块和本 runbook。下线时两者一并删除（见文末清单）。

## 拓扑与端口

| 组件 | 容器 | 地址 | 说明 |
|---|---|---|---|
| 测试 MCP | `sda-mcp-test` | `0.0.0.0:3101`（云防火墙未放行，公网不可达） | 复用生产镜像 `sda-mcp-sda-mcp:latest`，独立测试 token |
| 测试 Neo4j | `sda-neo4j-test` | `127.0.0.1:7688`(bolt) / `7475`(http) | `neo4j:5.26-community` 与生产同 tag（镜像层共享），堆 256m / 页缓存 128m |
| 公网入口 | — | `https://mcp-test.super-data-analytics.online/mcp` | Caddy 反代 3101；DNS A 记录 `mcp-test` → 106.53.74.143 |

与生产完全隔离：独立实例、独立 Neo4j、独立 token；`sync` 全量清库只影响测试图。

## 服务器侧文件（`~/sda-test/`）

| 文件 | 用途 |
|---|---|
| `.env`（600） | `SDA_MCP_TOKEN`（测试独立 token，与生产不同）+ `NEO4J_AUTH` |
| `config-test.json`（600） | 生产 `config.json` 副本，当前仅改 `env.NEO4J_URI=bolt://127.0.0.1:7688`；bitable 仍为生产同款（冒烟用） |
| `docker-compose.yml` | 两个测试容器；只引用镜像名，**绝不 build** |

本机工作站的测试 token 存 `~/.sda_mcp_token_test.txt`（与生产 `~/.sda_mcp_token.txt` 同款约定）。

## 日常运维（hermes 上）

```bash
cd ~/sda-test
docker compose -p sda-test ps            # 状态（neo4j 应为 healthy）
docker compose -p sda-test logs -f       # 日志（或 --tail=100）
docker compose -p sda-test restart       # 重启
docker compose -p sda-test up -d         # 改 compose 后应用
```

服务器上直接调用测试实例（不经公网）：

```bash
T=$(sed -n 's/^SDA_MCP_TOKEN=//p' ~/sda-test/.env)
python3 ~/sda-mcp/scripts/mcp_debug.py --url http://127.0.0.1:3101/mcp --token "$T" list
```

本机走公网域名：

```bash
python scripts/mcp_debug.py --url https://mcp-test.super-data-analytics.online/mcp \
  --token "$(cat ~/.sda_mcp_token_test.txt)" list
```

## 切换到新项目 bitable（换语义层）

1. 编辑 `~/sda-test/config-test.json` 三处：
   - `env.FEISHU_GRAPH_BITABLE_APP_TOKEN` → 新多维表 app token
   - `graph-config.entities` → 新实体标签（各表 `table_id` + `key_field`）
   - `graph-config.relationships` → 新关系 match 规则
2. `docker restart sda-mcp-test`——`config.py` 的 `load_config()` 有 `lru_cache`，不重启不重读
3. `sync dry_run=true` 预检 → 通过后 `dry_run=false` 全量重建（分钟级，`mcp_debug.py --timeout 540`）
4. `retrieve_schema` / `retrieve_search` 验证

迭代实体设计 = 改 config → 重启 → 重新 sync，可随时推倒重来（sync 清空整库重建，幂等）。

## 跟随生产升级镜像

生产重新 build 后 `sda-mcp-sda-mcp:latest` 指向新镜像，但运行中的测试容器仍用旧层，需显式重建：

```bash
cd ~/sda-test && docker compose -p sda-test up -d --force-recreate sda-mcp-test
```

不要在 `~/sda-test` 里 build——测试环境与生产共用镜像，独立构建会多出整套镜像 + BuildKit 缓存（GB 级，40G 盘吃不消）。

## 磁盘

- 新增占用约 550MB，几乎全部是 volume `sda-test_neo4j-test-data`（Neo4j 全新 volume 的系统库 + 事务日志基线 ~540MB，图数据本身很小）。
- 镜像零新增（与生产共享）。回收：`docker compose -p sda-test down -v`。

## 内存与运行策略（2026-10-13 事故后强制）

**事故复盘**：测试栈常驻 + 生产 `sda-mcp` 的 python 进程连续数周运行后从 ~280MB 滞涨至 1.4GB（fastembed/onnx 内存滞留），在仅 3.7GB 内存 + 2GB swap 的机器上耗尽内存，整机 thrash 冻结（load ~100，SSH banner 超时），OOM 杀生产 python 后 `restart` 策略反复拉起形成风暴，生产 MCP 不可用约 30 分钟。停掉测试栈后恢复。

规则：

- **测试栈默认不常驻**：验证时 `docker compose -p sda-test up -d`，用完 `docker compose -p sda-test stop`（volume 保留，数据不丢）。
- 容器内存上限已写入服务器 compose：`sda-mcp-test` `mem_limit: 640m`、`sda-neo4j-test` `mem_limit: 768m`（JVM 堆 256m + 页缓存 128m + 开销）。上限是兜底不是许可，仍按需启停。
- 拉起测试栈前先看 `free -m`：available < 1.5GB 时不要拉。生产 MCP python 的滞涨随运行时长增长，生产容器已运行数周时尤其小心。
- 想双环境同时常驻，先升配（≥8G 内存）再谈。


## 下线流程

1. 仓库：删 `Caddyfile` 的 `mcp-test` 站点块、本文件、AGENTS.md 相应段落，commit/push；服务器 `git pull --ff-only` 后 `sudo cp Caddyfile /etc/caddy/Caddyfile && sudo systemctl restart caddy`。
2. 服务器：`cd ~/sda-test && docker compose -p sda-test down -v`，确认 volume 一并删除。
3. 删服务器 `~/sda-test/` 目录、本机 `~/.sda_mcp_token_test.txt`。
4. DNS 记录 `mcp-test` 可保留（无 Caddy 站点即无服务）或删除。

## 已知坑

- Neo4j 5.x 端口绑定设置是 `server.bolt.listen_address` / `server.http.listen_address`（env 写法 `NEO4J_server_bolt_listen__address`）；写成 `listen_to` 会导致容器 crash 循环。
- `sync` 属长任务，部分 MCP 客户端会超时中断但不代表失败；统一用 `scripts/mcp_debug.py --timeout 540`。
- 证书未签发（DNS 刚生效）：Caddy 自动退避重试，超 5 分钟 `sudo systemctl restart caddy` 立即触发。
- 401 = token 用错（测试/生产 token 独立，注意别混）；3101 直连公网不通是预期，走 443 的 `mcp-test` 域名。
- 域名/证书故障时的后备通道：`ssh -N -L 3101:127.0.0.1:3101 hermes` 后用 `http://127.0.0.1:3101/mcp`。

## 验收清单（新搭/重建后）

1. `docker compose -p sda-test ps`：两容器 running，neo4j `(healthy)`
2. 无 Token POST `https://mcp-test.super-data-analytics.online/mcp` → 401
3. 测试 token → 18 个工具
4. `retrieve_schema` 返回全部实体（sync 之后）
5. `retrieve_search` 冒烟命中目标实体
6. 生产回归：`https://mcp.super-data-analytics.online/mcp` 401 / 工具列表正常，生产图未受影响
