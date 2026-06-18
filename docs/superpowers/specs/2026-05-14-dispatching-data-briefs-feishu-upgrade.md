# 数据播报 Skill — 飞书存储升级

## 概述

将 `dispatching-data-briefs` skill 的模板存储从本地 `references/` 目录升级为飞书个人文件夹。新建一个 Node.js CLI 工具 `feishu-briefs.js`（CommonJS）封装飞书 API，支持模板的增删改查。SKILL.md 同步更新，所有模板操作通过 CLI 工具完成。

## 目录结构

```
dispatching-data-briefs/
├── SKILL.md                 # Skill 定义（更新）
├── feishu-briefs.js         # CLI 工具（新建，ESM）
├── package.json             # 依赖
├── .env                     # 凭证配置
└── references/              # 保留，用于临时文件和迁移参考
```

## 凭证配置

`.env` 文件：
```
FEISHU_APP_ID=cli_a61c7f2cca7e900d
FEISHU_APP_SECRET=<secret>
FEISHU_FOLDER_TOKEN=XvG6feei4lr5XFdaGzEcsxGrnkg
FEISHU_DELETE_PASSWORD=<用户设置的密码>
```

## CLI 工具设计

### 命令

| 命令 | 说明 | 飞书 API |
|---|---|---|
| `node feishu-briefs.js list` | 列出文件夹中所有播报模板 | `GET /drive/v1/files?folder_token=xxx` |
| `node feishu-briefs.js read <doc_id>` | 读取文档原始内容 | `GET /docx/v1/documents/:id/raw_content` |
| `node feishu-briefs.js create --title "XX" --file <path>` | 创建文档并写入内容 | `POST /docx/v1/documents` + `POST .../blocks/:id/children` |
| `node feishu-briefs.js update <doc_id> --file <path>` | 覆盖更新文档内容 | 读取 blocks → 清空 → 重建 |
| `node feishu-briefs.js delete <doc_id>` | 删除文档（需密码） | `DELETE /drive/v1/files/:id?type=docx` |

### Token 管理

不缓存 token，每次 CLI 调用前重新获取 `tenant_access_token`：
- 端点：`POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`
- 请求体：`{ "app_id": "...", "app_secret": "..." }`
- 返回：`{ "tenant_access_token": "...", "expire": 7200 }`

### 删除密码验证

`delete` 命令读取 `.env` 中的 `FEISHU_DELETE_PASSWORD`，与用户提供的密码比对。CLI 交互式提示输入密码，匹配后执行删除。

## 内容读写策略

### 读取

使用 `GET /docx/v1/documents/:id/raw_content` 获取文档纯文本。文档开头包含 YAML frontmatter（`---` 包裹），后续为模板正文。

### 写入（create/update）

CLI 接收一个本地文件路径，读取内容后做基础 Markdown → 飞书 block 转换，写入文档。

转换规则（只处理模板中用到的子集）：

| Markdown | 飞书 Block |
|---|---|
| `# title` | heading1 block |
| `## section` | heading2 block |
| `### subsection` | heading3 block |
| 普通段落 | text block |
| `- item` | bullet block |
| `| col | col |` | table block |
| `` ```code``` `` | code block |
| `---`（分隔线） | divider block |

流程：
1. 创建空文档：`POST /docx/v1/documents` → 获得 `document_id`
2. 读取根 block：`GET /docx/v1/documents/:id/blocks` → 获得 Page block 的 `block_id`
3. 逐个添加子 block：`POST /docx/v1/documents/:id/blocks/:block_id/children`

对于 update，先读取现有 blocks，删除所有子 block，再重新创建。

## SKILL.md 更新要点

- 模板列表：`node feishu-briefs.js list`
- 读取模板：`node feishu-briefs.js read <doc_id>`
- 新建模板：Claude 生成内容 → 写入临时文件 → `node feishu-briefs.js create --title "XX" --file <path>`
- 编辑模板：读取 → 修改 → 写临时文件 → `node feishu-briefs.js update <doc_id> --file <path>`
- 删除模板：`node feishu-briefs.js delete <doc_id>`（CLI 自动提示密码）
- 执行流程不变：读取模板 → 解析 frontmatter → 调对应 fetching skill → 生成报告

## 迁移计划

现有两个模板（`平台治理经营健康数据播报.md`、`质检数据播报.md`）迁移到飞书文件夹作为测试数据：
1. CLI 工具开发完成后
2. 使用 `create` 命令将两个模板上传到飞书文件夹
3. 验证 `list` 和 `read` 能正确获取内容

## 飞书 API 端点汇总

| 操作 | 方法 | 端点 |
|---|---|---|
| 获取 token | POST | `https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal` |
| 列出文件夹 | GET | `https://open.feishu.cn/open-apis/drive/v1/files?folder_token=xxx` |
| 创建文档 | POST | `https://open.feishu.cn/open-apis/docx/v1/documents` |
| 读文档(文本) | GET | `https://open.feishu.cn/open-apis/docx/v1/documents/:id/raw_content` |
| 读文档(块) | GET | `https://open.feishu.cn/open-apis/docx/v1/documents/:id/blocks` |
| 创建子块 | POST | `https://open.feishu.cn/open-apis/docx/v1/documents/:id/blocks/:block_id/children` |
| 批量更新块 | PATCH | `https://open.feishu.cn/open-apis/docx/v1/documents/:id/blocks/batch_update` |
| 删除文档 | DELETE | `https://open.feishu.cn/open-apis/drive/v1/files/:id?type=docx` |

## 技术约束

- Node.js，ESM（`import`/`export`），文件扩展名用 `.js`（通过 `package.json` 的 `"type": "module"` 启用）
- 不缓存 token，每次调用重新获取
- 不需要额外 npm 依赖（用原生 `https` 模块发请求）
- 删除操作需密码验证（配置在 `.env`）
