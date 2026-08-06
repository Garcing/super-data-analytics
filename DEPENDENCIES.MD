# Dependencies

本文件是 1.0 项目的依赖、安装目录与运行配置总表。具体命令仍以各子 Skill 的 `SKILL.md` 为准；两者不一致时，应同步修正，不能让代码依赖隐式依靠父目录或全局环境。

## 统一约定

- Node.js：`>=20.0.0`。有 `package-lock.json` 的目录使用 `npm ci`，不要用全局包代替项目直接依赖。
- Python：`>=3.10`。始终使用目标解释器执行 `python -m pip install -r ...`；GraphRAG 的目标解释器由 `config.json` 的 `env.PYTHON_PATH` 指定。
- 业务凭证：统一写入 `~/.super-data-analytics/config.json` 的 `env`，脚本不读 `.env`。
- 图谱结构：仅 `retrieving-context` 使用 `config.json` 的 `graph-config`。
- 动态产物：写到 `<工作区>/.super-data-analytics/{results,scratch,cache}/`，不写入 Skill 目录。
- 进程级代理/超时不是业务凭证，可按需使用 `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY`、`SQL_QUERY_STDIN_TIMEOUT_MS`、`QUERY_STDIN_TIMEOUT_MS`、`SDA_STDIN_TIMEOUT_MS`。

外部工具使用自身配置：`lark-cli` 通过 `lark-cli config init` 与 `lark-cli auth login` 授权；Vercel CLI 使用自身登录状态或调用者提供的 `VERCEL_TOKEN`。项目运行脚本不会从 `config.json` 加载 `VERCEL_TOKEN`。

## 运行时与外部服务

| 类别 | 版本 / 服务 | 用途 |
| --- | --- | --- |
| Node.js | 20+ | 查询、GraphRAG Node 壳、模板管理、报告 CLI、HTML 前端 |
| Python | 3.10+ | GraphRAG pipeline、归因/预测/评估脚本、图表、Streamlit |
| Neo4j | 5.x | 业务知识图谱与向量索引 |
| Hologres | PostgreSQL 协议 | SQL 取数 |
| Power BI / Fabric MCP | Azure AD Application 鉴权 | 语义模型 schema 与 DAX 查询 |
| 飞书 | `lark-cli` | 多维表格数据源、模板、文档/幻灯片交付 |
| Vercel + Blob | Public Blob Store | HTML/Streamlit 报告数据发布与前端托管 |
| Streamlit Community Cloud | `Garcing/streamlit-reports` | Streamlit 多页报告托管 |
| apimart gpt-image-2 | HTTP API | 图片报告生成 |

## 各 Skill 依赖

### orchestrating-analytics

纯方法论，无脚本、无 Node/Python 第三方依赖、无环境变量。

### querying-data

安装目录：`querying-data/scripts/`。

- Node：`@azure/identity`、`pg`、`pg-protocol`、`xlsx`。
- `pg-protocol` 是 `lib/sql.js` 的直接 import，用于 Hologres 空字段名兼容，必须作为直接依赖声明，不能只依赖 `pg` 的传递安装。
- 清单：`package.json` + `package-lock.json`，两者根依赖已对齐。
- 配置：
  - Hologres：`HOLOGRES_HOST`、`HOLOGRES_PORT`、`HOLOGRES_DATABASE`、`HOLOGRES_USER`、`HOLOGRES_PASSWORD`。
  - Power BI：`POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID`。

### retrieving-context

Node 安装目录：`retrieving-context/scripts/`。

- Node：`neo4j-driver`；清单为 `package.json` + `package-lock.json`。
- Python 安装文件：`retrieving-context/scripts/pipeline/requirements.txt`。
- Python：`neo4j`、`sentence-transformers`。代码不 import PyYAML，已从 requirements 删除。
- 模型：默认 `BAAI/bge-small-zh-v1.5`，首次 `python scripts/pipeline/sync.py --download-model` 会下载到 `scripts/pipeline/models/`。
- 外部：`lark-cli`。
- 配置：`NEO4J_URI`、`NEO4J_DATABASE`、`NEO4J_USER`、`NEO4J_PASSWORD`、`FEISHU_GRAPH_BITABLE_APP_TOKEN`、`PYTHON_PATH`，以及 `graph-config.embedding/entities/relationships`。

### diagnosing-anomalies

Python 3.10+ 标准库实现。`diagnosing-anomalies/requirements.txt` 是注释型空依赖清单，用于明确运行时和测试均无第三方包；不读取配置或环境变量。

### predicting-trends

Python 3.10+ 标准库实现。`predicting-trends/requirements.txt` 是注释型空依赖清单；不使用 NumPy 或 ML 框架，不读取配置或环境变量。

### evaluating-impact

Python 3.10+ 标准库实现。`evaluating-impact/requirements.txt` 是注释型空依赖清单；不读取配置或环境变量。

### visualizing-data

安装文件：`visualizing-data/requirements.txt`。

- 运行：`matplotlib`、`pandas`、`pillow`、`seaborn`。
- 测试：`pytest`。
- 系统字体：中文标签需要任一可用 CJK 字体（推荐 `sudo apt install fonts-noto-cjk`）；字体不属于 pip 依赖，缺失时 CLI 会输出 warning 且图中中文显示为方框。安装字体后需清除 matplotlib 缓存：`rm -rf ~/.cache/matplotlib`。
- 不读取 `config.json` 或环境变量。

### using-templates

- `using-templates/scripts/package.json` 仅声明 ESM 与 Node 20+，代码只使用 Node 内置模块。
- 无第三方 npm 依赖，因此不需要 `package-lock.json`，也无需在该目录执行 `npm install`。
- 外部：`lark-cli`。
- 配置：`FEISHU_TEMPLATE_FOLDER_TOKEN`、`FEISHU_TEMPLATE_DELETE_PASSWORD`。

### building-reports

分为共享 Node CLI、HTML 前端和 Streamlit Python 三层：

- `building-reports/scripts/`：`@vercel/blob`、`undici`，清单为 `package.json` + `package-lock.json`。HTML/Image/Streamlit 的 Node CLI 从此处解析共享依赖。
- `building-reports/scripts/html/`：React 18、React DOM 18、React Router 7、Recharts 2；开发依赖为 Vite 6、React plugin、Tailwind CSS 3、PostCSS、Autoprefixer。清单为独立的 `package.json` + `package-lock.json`。
- `building-reports/scripts/image/`：没有独立 package/lock；`image.js` 使用父级共享依赖，避免重复安装 `undici` 和不必要地把 Node 门槛抬到 22.19。
- `building-reports/scripts/streamlit/requirements.txt`：`streamlit`、`pandas`、`plotly`。
- 配置：`BLOB_READ_WRITE_TOKEN`、`VERCEL_REPORTS_URL`、`APIMART_API_KEY`、`APIMART_BASE_URL`。
- 外部：Vercel CLI（HTML 部署）；Git/Bash（Streamlit subtree 发布）；飞书格式由 `lark-doc` / `lark-slides` 负责。

### validating-analyses

纯方法论，无脚本、无 Node/Python 第三方依赖、无环境变量。需要复算、重画、重发时调用对应 Skill。

## 安装速查

以下命令从仓库根目录执行：

```bash
# Node：仅四个有 lock 的目录
cd querying-data/scripts && npm ci
cd ../../retrieving-context/scripts && npm ci
cd ../../building-reports/scripts && npm ci
cd html && npm ci

# Python
<PYTHON_PATH> -m pip install -r retrieving-context/scripts/pipeline/requirements.txt
python -m pip install -r visualizing-data/requirements.txt
python -m pip install -r building-reports/scripts/streamlit/requirements.txt

# 飞书 CLI
npm install -g @larksuite/cli
lark-cli config init
lark-cli auth login
```

三个分析脚本的 `requirements.txt` 没有第三方包，不需要执行安装；保留文件是为了明确依赖边界。

## 测试与验证

```bash
python -m pytest diagnosing-anomalies/tests/test_contribution.py -q
python -m pytest predicting-trends/tests/test_forecast.py -q
python -m pytest evaluating-impact/tests/test_impact.py -q
python -m pytest visualizing-data/tests/test_chart_cli.py -q

npm ci --ignore-scripts --no-audit --no-fund --dry-run --prefix querying-data/scripts
npm ci --ignore-scripts --no-audit --no-fund --dry-run --prefix retrieving-context/scripts
npm ci --ignore-scripts --no-audit --no-fund --dry-run --prefix building-reports/scripts
npm ci --ignore-scripts --no-audit --no-fund --dry-run --prefix building-reports/scripts/html
```

## 环境验证日志（2026-08-06）

以下为首次部署时的实测记录，供后续排障参考。

### 全量测试结果

| 测试 | 结果 | 说明 |
| --- | --- | --- |
| `diagnosing-anomalies` pytest | ✅ 3 passed | 标准库实现，无外部依赖 |
| `predicting-trends` pytest | ✅ 10 passed | 标准库实现 |
| `evaluating-impact` pytest | ✅ 9 passed | 标准库实现 |
| `visualizing-data` pytest | ✅ 50 passed, 1 warning | seaborn 0.13 对 matplotlib 3.11 的 `vert` 参数弃用 warning，不影响功能 |
| Node.js 4 目录 npm ci dry-run | ✅ 全部通过 | |
| `querying-data` CLI 冒烟 | ✅ --help 正常 | |
| `retrieving-context` CLI 冒烟 | ✅ schema 正常（Neo4j 已连接） | |
| `querying-data powerbi` test-connection | ✅ 连接成功，4 tools | |
| `building-reports` html/streamlit list | ✅ 报告列表正常 | |
| `building-reports` image dry-run | ✅ 参数校验通过 | |
| `visualizing-data` chart 生成 | ✅ PNG 输出正常（安装 CJK 字体后） | |

### 已修复的文档错误

1. **retrieving-context 模型下载路径**：原文写 `node scripts/sync.js --download-model`（不存在），实际是 `python scripts/pipeline/sync.py --download-model`。已修正。
2. **飞书 CLI 安装包名**：原文写 `npm install -g @anthropic-ai/lark-cli`（不存在），实际是 `npm install -g @larksuite/cli`。已修正。
3. **CJK 字体安装指引不完整**：原文只提"缺失时 CLI 会输出 warning"，未说明安装方法和缓存清理。已补充 `sudo apt install fonts-noto-cjk` + `rm -rf ~/.cache/matplotlib`。

### 已知外部依赖问题（需用户处理）

1. **Hologres 连接**：公网 IP 不在 Hologres 白名单中，需要通过公司 VPN 使用内网地址（如 `192.168.5.121:31223`）连接。VPN 配置文件（`.ovpn` + `ta.key` + `ca.crt`）需放在 `/etc/openvpn/client/`，凭证写入 `/etc/openvpn/client/auth.txt`。建议配置 systemd service 实现开机自启和断线重连。
2. **lark-cli 未绑定 Hermes**：`using-templates` 等依赖飞书的 skill 报 `hermes context detected but lark-cli is not bound`。需要用户确认身份策略后运行 `lark-cli config bind --source hermes --identity bot-only`（或 `user-default`）。
3. **APIMART_API_KEY**：config.json 中该项被占位符 `«redacted:sk-…»` 脱敏，`building-reports image generate` 实际调用会失败。需要用户提供真实 key。

### Python 解释器注意

Ubuntu 24.04 默认 `python3` 可能指向 Hermes venv（无 pip）。安装依赖时应使用系统 Python（如 `python3.12 -m pip install -r ... --break-system-packages`）。`config.json` 的 `PYTHON_PATH` 应指向可用的系统 Python 解释器。
