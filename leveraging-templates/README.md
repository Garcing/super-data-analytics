# leveraging-report-templates

数据分析报告模板的全生命周期管理。模板存储在飞书个人文件夹中，通过 `scripts/templates.js` CLI 工具进行增删改查。

## 快速开始

### 1. 安装 lark-cli

```bash
npm install -g lark-cli
lark-cli config init    # 配置飞书应用凭证
lark-cli auth login     # 授权登录
```

详见 [`references/lark-cli-setup.md`](references/lark-cli-setup.md)。

### 2. 配置

编辑 `.env`（不会提交到 git）：

```
FEISHU_FOLDER_TOKEN=你的飞书文件夹token
FEISHU_DELETE_PASSWORD=删除密码（可选）
```

### 3. 验证

```bash
node scripts/templates.js list
```

能返回 JSON 数组即配置成功。

## CLI 命令

```bash
# 列出所有播报模板（含子文件夹，并行查询）
node scripts/templates.js list

# 读取模板内容（返回 Markdown）
node scripts/templates.js read <doc_id>

# 创建新模板（默认保留临时文件，加 --drop 执行后删除）
node scripts/templates.js create --title "播报主题" --file <content_file> [--drop]

# 更新模板（全量覆盖，ID 不变）
node scripts/templates.js update <doc_id> --file <content_file> [--drop]

# 删除模板（需要密码）
node scripts/templates.js delete <doc_id> --password <密码>
```

`--drop` 表示执行后自动删除本地临时文件，默认保留。

## 架构

```
scripts/templates.js (CLI)
  └── lark-cli (飞书文档操作)
      ├── drive files list        → 列出文件夹中的文档（支持子文件夹并行查询）
      ├── docs +create (v2)       → 创建文档（Markdown → 飞书文档）
      ├── docs +fetch (v2)        → 读取文档（飞书文档 → Markdown）
      ├── docs +update (v2)       → 更新文档（覆盖写入）
      └── drive +delete           → 删除文档
```

### 身份策略

调用 lark-cli 时**优先以 user 身份**发起请求，失败后自动**回退到 bot 身份**。首次成功后缓存可用身份，后续调用直接使用，无需重复尝试。

### list 命令的查询逻辑

```
FEISHU_FOLDER_TOKEN（根目录）
  ├── 根目录下的 docx/doc → 直接收集（category 为空）
  └── 子文件夹 → 并行查询（Promise.all），仅深入一层
        └── 子文件夹下的 docx/doc → 收集并标记 category
```

- 子子文件夹及更深层级**忽略**
- 子文件夹之间**并行查询**，总耗时 ≈ 根目录 + 最慢的子文件夹

## 用到的飞书 API

`templates.js` 通过 lark-cli 调用以下飞书开放平台 API：

| lark-cli 命令 | 底层 API | 用途 |
|---|---|---|
| `drive files list --params @file` | `GET /open-apis/drive/v1/files` | 列出文件夹中的文档 |
| `docs +create --api-version v2` | `POST /open-apis/docs_ai/v1/documents` | 创建文档，支持 Markdown 直传 |
| `docs +fetch --api-version v2` | `GET /open-apis/docs_ai/v1/documents/:id` | 读取文档，返回 Markdown |
| `docs +update --api-version v2 --command overwrite` | `PATCH /open-apis/docs_ai/v1/documents/:id` | 全量覆盖更新文档 |
| `drive +delete --file-token --type --yes` | `DELETE /open-apis/drive/v1/files/:token` | 删除文档 |

> **注意**：lark-cli v2 实际调用的是 `docs_ai/v1` 接口（飞书未公开文档的简化 API），支持直接传 Markdown 内容，由飞书后端完成 Markdown ↔ DocxXML 的双向转换。相比官方文档上的 `docx/v1` 接口（需要手动拼 XML），更简洁易用。

### 应用权限要求

飞书开放平台上需要开通以下 scope：

- `docx:document:create` — 创建文档
- `docx:document:readonly` — 读取文档
- `docx:document:write_only` — 编辑文档
- `space:document:retrieve` — 列出文件夹
- `space:document:delete` — 删除文档

## 目录结构

```
leveraging-report-templates/
├── scripts/
│   ├── templates.js      # CLI 工具（lark-cli 封装）
│   ├── package.json      # Node.js ESM 配置
│   └── cache/            # 临时文件（自动清理，gitignore）
├── .env                  # 本地配置（不提交 git）
├── SKILL.md              # Skill 定义（意图识别、工作流）
├── README.md             # 本文件
└── references/
    ├── lark-cli-setup.md     # lark-cli 安装配置指南
    ├── wecom-webhook.md      # 企微 Webhook 消息格式参考
    └── data-brief-template.md # 数据播报模板规范
```

## 推送渠道

播报生成后可通过企微 Webhook 推送，详见 [`references/wecom-webhook.md`](references/wecom-webhook.md)。

推荐使用 `markdown_v2` 类型（支持表格、列表），如需颜色标注异常值则用 `markdown`（v1，支持 `<font color="warning/info/comment">`）。

## 数据流

```
用户请求
  → SKILL.md 意图识别（列出/查看/新建/编辑/删除）
  → scripts/templates.js 操作飞书模板
  → 执行时：读取模板 → 提取数据源 → 调用查询 skill → 填充格式模板 → 输出报告
```
