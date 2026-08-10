# 飞书开放平台 API 替换 lark-cli — 设计

- 日期：2026-08-10
- 分支：`spec/mcp-server-design`
- 状态：已批准，待写实现计划
- 相关：`2026-08-09-mcp-server-design.md`（MCP 服务总体设计）

## 1. 背景与动机

MCP 服务（`mcp/sda_mcp/`）当前用 **lark-cli**（Node 子进程）访问飞书，涉及三个内核：

| 内核 | lark-cli 子命令 | 用途 |
|---|---|---|
| `using_templates.py` | `docs +fetch/create/update`、`drive files list`、`drive +delete` | 模板文档 CRUD |
| `retrieving_context.py` | `docs +fetch` | `retrieve_doc` 读飞书文档 |
| `retrieving_context_sync.py` | `base +field-list/record-list` | GraphRAG sync 从多维表取数 |

lark-cli 带来三块部署复杂度：

1. **脆弱的文件密钥链**：真正的加密 token 在 `~/.local/share/lark-cli/`（`master.key` + `*.enc`），`~/.lark-cli/` 只存引用；容器要挂两个卷，少挂一个就 `invalid_client`。
2. **镜像重依赖**：Dockerfile 装 Node + npm + 锁定 `@larksuite/cli@1.0.83`（新版误读旧版 token 格式）。
3. **身份回退逻辑**：`--as user → --as bot` 回退，实例级缓存，状态散落。

**目标**：用飞书开放平台官方 REST API 直接替换全部 lark-cli 调用，鉴权改为自建应用的 `tenant_access_token`（`app_id` + `app_secret`），从而：

- 删掉 lark-cli / Node / npm（Dockerfile 瘦身）。
- 删掉两个密钥挂载卷（compose 简化，部署不再因 lark-cli 配置损坏而挂）。
- 凭证收敛进 `~/.super-data-analytics/config.json`（已是凭证唯一来源、gitignore）。

## 2. 可行性结论（已调研 + 已验证）

| 能力 | 现状（lark-cli） | 替换 API | 难度 |
|---|---|---|---|
| docx → markdown（读） | `docs +fetch --doc-format markdown` | `GET /open-apis/docs/v1/content?doc_type=docx&content_type=markdown` | ⭐ **已用真实文档验证**：`data.content` 直出完整 markdown |
| markdown → docx（建/覆盖） | `docs +create/update --doc-format markdown` | convert + create_doc + insert_children / delete_all_children + convert + insert | ⭐⭐⭐ 中 |
| 文件夹列表 | `drive files list --page-all` | `GET /open-apis/drive/v1/files?folder_token=` | ⭐ 易 |
| 删除文件 | `drive +delete --type docx` | `DELETE /open-apis/drive/v1/files/{token}?type=docx` | ⭐ 易 |
| 多维表字段 | `base +field-list` | `GET /open-apis/bitable/v1/apps/{app}/tables/{t}/fields` | ⭐ 易 |
| 多维表记录 | `base +record-list` | `GET /open-apis/bitable/v1/apps/{app}/tables/{t}/records` | ⭐ 易 |

关键发现：用户此前在开放平台找不到 markdown 选项，是因为该接口在 **`docs/v1`** 命名空间（`docs/v1/content`），而非 `docx/v1`。`docx/v1/documents/{id}/raw_content` 只给纯文本（丢 md 符号），不可用。

读路径已知差异（不影响使用）：
- 标点转义偏重（`1\.`、`sda\_mcp`、`\+`）——渲染一致，喂 LLM 无影响。
- 表格输出为 HTML `<table>` 而非 GFM 管道表——对 LLM 阅读无影响。

## 3. 关键决策

- **D1 鉴权**：纯 `tenant_access_token`（应用/bot 身份）。**去掉 user→bot 回退**。自建应用 `cli_a61c7f2cca7e900d` 已对模板文件夹、graph 多维表、retrieve_doc 目标文档完成授权（文档已共享给应用 + 开通权限范围）。
- **D2 覆盖更新语义**：`update_template` 采用**删全部子块再插入**（GET blocks 取根 children 数 → batch_delete `0..N` → convert → insert），与 lark-cli `--command overwrite` 语义一致，最稳妥。代价是丢失 block 级编辑历史——可接受。
- **D3 上线策略**：分阶段交付，终态硬移除 lark-cli（不做自动兜底）。详见 §6。
- **D4 client 架构**：单一共享 `FeishuClient` 类，对齐现有 `VercelBlobClient` 模式（httpx + `_headers()` + 抛 `ConfigError`/`ExternalAPIError` + dataclass）。集中鉴权/错误/重试，最易测。
- **D5 token 缓存**：模块级（进程级）缓存 token + 过期点，剩 ≤5min 刷新。FastMCP stateless 每次调用新建 client 实例，必须模块级缓存才能跨调用复用 token。冗余并发刷新无害，不加锁。

## 4. 架构

### 4.1 组件

```
config.json [env]
  ├─ FEISHU_APP_ID / FEISHU_APP_SECRET   ← 新增（替代 lark-cli 密钥链）
  ├─ FEISHU_TEMPLATE_FOLDER_TOKEN        ← 复用
  ├─ FEISHU_GRAPH_BITABLE_APP_TOKEN      ← 复用
  └─ FEISHU_TEMPLATE_DELETE_PASSWORD     ← 复用

mcp/sda_mcp/feishu.py   ← 新文件
  FeishuClient
    ├─ _tenant_token()          模块级缓存；POST /open-apis/auth/v3/tenant_access_token/internal
    ├─ _request(method, path, **kw)  统一 httpx：Authorization 头、超时、code!=0→ExternalAPIError
    ├─ get_doc_markdown(doc_token)            → docs/v1/content
    ├─ list_folder_files(folder_token)        → drive/v1/files（page_size=200，翻页到 has_more=False）
    ├─ delete_file(token, file_type)          → DELETE drive/v1/files/{token}?type=
    ├─ list_bitable_fields(app_token, table_id)   → bitable/.../fields
    ├─ list_bitable_records(app_token, table_id)  → bitable/.../records（page_size=500，翻页 page_token）
    ├─ convert_markdown_to_blocks(md)         → POST docx/v1/documents/blocks/convert  → blocks[]
    ├─ create_doc(folder_token, title)        → POST docx/v1/documents → document_id
    ├─ insert_children(doc_id, blocks)        → POST .../blocks/{doc_id}/children（分批 ≤1000/次）
    └─ delete_all_children(doc_id)            → GET blocks 取根 children 数 → batch_delete
```

三个内核改为 import `FeishuClient`：
- `using_templates.py`：删 `LarkCliClient`；`list/read/create/update/delete_template` 改调 `FeishuClient` 对应方法。
- `retrieving_context.py`：`doc()` 改调 `get_doc_markdown`（返回 dict 不变，结构按新 API 调整）。
- `retrieving_context_sync.py`：`_lark_cli` + `fetch_table_fields/records` 改调 `list_bitable_fields/records`。

### 4.2 数据流

**读路径**（`template_read`、`retrieve_doc`）：
```
doc_id → FeishuClient.get_doc_markdown(doc_id) → GET docs/v1/content → data.content (markdown str)
```

**sync 取数**（`fetch_table_fields/records`）：
```
app_token+table_id → list_bitable_fields → [{name,type,id}, ...]（过滤 auto_number）
                  → list_bitable_records（翻页）→ [{字段名:值}, ...]
```
注意：开放平台返回结构与 lark-cli 不同（字段名 `field_name`/`field_id` 而非 `name`/`id`；记录是 `fields` map 而非行列数组）。解析逻辑需重写，但输出对齐现有 `fetch_table_*` 的返回契约，保证下游 graph_builder/embedding 不动。

**写路径 — create_template(title, md?)**：
```
1. create_doc(folder_token, title) → document_id
2. md 缺省 → 结束（空文档）
3. convert_markdown_to_blocks(md) → blocks[]
4. 剥表格 block 的 merge_info（只读字段，传则报错）
5. insert_children(document_id, blocks)（>1000 分批）
```

**写路径 — update_template(doc_id, md)**（覆盖）：
```
1. delete_all_children(doc_id)（GET blocks 取根 children 数 N → batch_delete start=0,end=N）
2. convert_markdown_to_blocks(md) → blocks[]
3. 剥 merge_info
4. insert_children(doc_id, blocks)（分批）
```

## 5. 错误处理

- 缺 `FEISHU_APP_ID`/`FEISHU_APP_SECRET` → `ConfigError`（可操作提示，对齐现有缺 key 行为）。
- HTTP 非 2xx 或响应 `code != 0` → `ExternalAPIError`（带飞书 `msg` + 端点路径，截断 300 字）。
- token 刷新失败 → `ExternalAPIError`。
- 沿用 `ValidationError`：空 `doc_id` / 空 `content` / `create` 缺 `title` / `delete` 密码门（`FEISHU_TEMPLATE_DELETE_PASSWORD` 配置则强制校验）。
- 超时：单请求 30s（对齐 `VercelBlobClient._TIMEOUT`）；sync 翻页、convert 大文档可放宽到 60s。

## 6. 分阶段交付

| 阶段 | 内容 | 风险 | 可部署 |
|---|---|---|---|
| **P1** | `feishu.py` 核心：token + 5 个读/删端点（`get_doc_markdown`/`list_folder_files`/`delete_file`/`list_bitable_fields`/`list_bitable_records`）。替换 `template_read/list/delete`、`retrieve_doc`、sync 的 bitable fetch（`fetch_table_fields/records`）。 | 低（读路径已真实验证） | 是 |
| **P2** | 写端点：`convert_markdown_to_blocks` / `create_doc` / `insert_children` / `delete_all_children`。替换 `template_create/update`，含表格 `merge_info` 处理 + insert 分批。 | 中 | 是 |
| **P3** | Dockerfile 删 Node/npm/lark-cli（当前 L8-20）；compose 删两个 lark-cli 密钥挂载卷；更新 `mcp/README.md`、根 `CLAUDE.md`、踩坑表。**部署简化在此落地。** | 低 | 是 |

P1/P2 期间 lark-cli 仍在镜像里（写路径未替换完前不删），但读路径已切新 client。P3 才物理移除。

## 7. 测试策略

- **新 `tests/test_feishu.py`**：mock `FeishuClient._request`（或 httpx），覆盖：
  - token 缓存命中 / 过期前 5min 刷新 / 刷新失败抛错。
  - 8 个端点的方法→URL/参数映射 + 返回解析。
  - `code != 0` → `ExternalAPIError`；缺凭证 → `ConfigError`。
  - bitable records 翻页停止、fields 过滤 auto_number。
  - convert 返回 blocks；insert_children >1000 分批；表格 block 剥 `merge_info`。
- **改写** `tests/test_using_templates.py`、`tests/test_retrieving_context_sync.py`、`test_retrieving_context.py`（doc 部分）：mock 对象从 `subprocess.run` / `_lark_cli` 换成 `FeishuClient` 方法，保持原有断言语义（list 扁平+子目录、密码门、分页计数、select 取值等）。
- **集成对照**（`SDA_INTEGRATION=1`，可选）：真实 tenant token 调 `get_doc_markdown`，对照 lark-cli `docs +fetch --doc-format markdown` 输出，确认保真。
- 目标：维持现有 110 通过的水平（替换 mock，不减少覆盖）。

## 8. 不做（YAGNI）

- 不做 user_access_token / OAuth 刷新流程（部署更复杂，与简化目标相悖）。
- 不做图片 block 上传素材 + `replace_image`（模板无图片）。
- 不做 lark-cli 自动兜底（已选硬移除）。
- 不做分栏/画板等 `docs/v1/content` 不支持的 block 类型的自定义转换器（模板不涉及）。

## 9. 部署变更（P3 落地后）

**Dockerfile** 删除：
```dockerfile
# CJK 字体行保留，删 nodejs/npm
# 整段 lark-cli npm install 删除（L16-20）
```

**docker-compose.yml** 删除两个卷：
```yaml
# - ${HOME}/.lark-cli:/root/.lark-cli
# - ${HOME}/.local/share/lark-cli:/root/.local/share/lark-cli
```

**config.json** `env` 块新增：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`（值已由用户提供，写入宿主 config.json，不进 git/镜像）。

**文档** 更新：`mcp/README.md` 架构图（去掉 "+ lark-cli 子进程"、密钥链挂载说明、lark-cli 踩坑两行）、根 `CLAUDE.md`（部署要点的卷挂载、踩坑表的 lark-cli 条目）。

## 10. 验收标准

- 24 个工具行为不变（入参/出参契约不变），`template_*` 与 `retrieve_doc`、`sync` 走新 client。
- `cd mcp && python -m pytest -q` 全绿（替换后用例数不减、覆盖等价）。
- 集成模式：`retrieve_doc` / `template_read` 对真实文档返回与 lark-cli 一致的 markdown；`sync` 全量跑通（fetch→graph→embed）。
- 镜像不含 Node/lark-cli；compose 不挂 lark-cli 密钥卷；服务在**不挂 `~/.lark-cli`、`~/.local/share/lark-cli`** 的情况下正常工作（核心验收：部署复杂度降低）。
