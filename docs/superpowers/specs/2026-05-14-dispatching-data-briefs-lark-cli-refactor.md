# 数据播报 Skill — lark-cli 重构 + 最佳实践优化

## 概述

重构 `dispatching-data-briefs` skill：将 `feishu-briefs.js` 的后端从原生飞书 HTTP API 改为调用 lark-cli 子进程。引入 DocxXML 格式提升文档美观度，借鉴 lark-doc 官方 skill 的最佳实践增强稳定性。

## 架构变更

### 改动前

```
Claude → node feishu-briefs.js → 原生 fetch() → 飞书 OpenAPI
```

### 改动后

```
Claude → node feishu-briefs.js → execSync('lark-cli ...') → 飞书 OpenAPI
```

feishu-briefs.js 变为 lark-cli 的薄封装层，保留模板管理的领域逻辑（frontmatter 解析、缓存管理、密码验证）。

### 命令映射

| 命令 | lark-cli 调用 |
|---|---|
| `list` | `lark-cli drive +search --query "" --folder-tokens $TOKEN --doc-types docx --format json` |
| `read <doc_id>` | `lark-cli docs +fetch --api-version v2 --doc <id> --doc-format markdown` |
| `create --title "X" --file <path>` | `lark-cli docs +create --api-version v2 --parent-token $TOKEN --content '<xml>'` |
| `update <doc_id> --file <path>` | `lark-cli docs +update --api-version v2 --doc <id> --command overwrite --content '<xml>'` |
| `delete <doc_id> --password <pwd>` | `lark-cli drive files delete --params '{"token":"<id>","type":"docx"}'` |

## 删除的代码

从 feishu-briefs.js 中移除：
- `getTenantToken()` — lark-cli 内部管理认证
- `feishuGet/Post/Patch/Delete` — 不再直接调 HTTP
- `textElement/textBlock/headingBlock/bulletBlock/codeBlock/dividerBlock` — 被 mdToXml 替代
- `mdToBlocks()` — 被 mdToXml 替代
- `checkResponse()` — lark-cli 自行处理 API 错误

## 新增的代码

### `mdToXml(markdown)` 转换器

将 Markdown 模板内容转为 DocxXML 格式。转换规则：

| Markdown | DocxXML |
|---|---|
| `# 标题` | `<h1>标题</h1>` |
| `## 章节` | `<h2>章节</h2>` |
| `### 子节` | `<h3>子节</h3>` |
| `- 列表项` | 连续 `-` 项合并为 `<ul><li>...</li></ul>` |
| `| col | col |` 表格 | `<table><colgroup>...<thead><tr><th bg="light-gray">...<tbody><tr><td>...` |
| `` ```yaml...``` `` | `<pre lang="yaml" caption="配置"><code>...</code></pre>` |
| `` ```...``` `` | `<pre><code>...</code></pre>` |
| `---`（分隔线） | `<hr/>` |
| 普通段落 | `<p>...</p>` |

XML 转义规则（从 lark-doc-xml.md 借鉴）：标签本身不转义，只有标签内文本内容转义（`<` → `&lt;`，`>` → `&gt;`，`&` → `&amp;`）。

### `exec(cmd)` 封装

统一调用 lark-cli 的函数：
- 用 `execSync(cmd, { encoding: 'utf-8' })` 执行
- 检查 exit code，非 0 时抛出包含 stderr 的错误
- stdout 返回 JSON 时解析并返回

### 样式规范（嵌入 mdToXml）

在转换时自动应用以下样式：
- 表格表头单元格加 `background-color="light-gray"`
- YAML frontmatter 用 `<pre lang="yaml">` 包裹
- 分隔线 `---` → `<hr/>`
- 连续列表项合并为单个 `<ul>`

## 稳定性改进

### 1. Update 保持文档 ID 不变

改用 lark-cli `docs +update --command overwrite`，不再删除重建。文档 ID 稳定，外部引用不会失效。

### 2. 错误处理

lark-cli 内部处理：
- Rate limiting（飞书 API 3-5 QPS 限制）
- Token 刷新
- API 错误码解析

feishu-briefs.js 只需检查 lark-cli exit code 和 stderr。

### 3. 长内容分批

如果转换后的 XML 内容超过约 30000 字符，改用 `docs +create` 建骨架 + `docs +update --command append` 分段填充。

## 文件结构

```
dispatching-data-briefs/
├── SKILL.md                 # 更新：加 lark-cli 安装指引
├── feishu-briefs.js         # 重写：改用 lark-cli 后端 + mdToXml
├── package.json             # 保留（type: module）
├── .env                     # 保留（FOLDER_TOKEN, DELETE_PASSWORD；移除 APP_ID/SECRET）
├── cache/                   # 临时文件目录
└── references/
    └── setup.md             # 新增：lark-cli 安装和配置指南
```

## .env 变更

移除飞书应用凭证（认证由 lark-cli 管理），保留：
```
FEISHU_FOLDER_TOKEN=XvG6feei4lr5XFdaGzEcsxGrnkg
FEISHU_DELETE_PASSWORD=
```

## lark-cli 安装指引（references/setup.md）

内容：
1. lark-cli 安装方式（npm install -g @anthropic-ai/lark-cli 或项目指定方式）
2. 初始化配置：`lark-cli config init`
3. 登录授权：`lark-cli auth login --scope "docx:document,drive:drive,search:docs:read"`
4. 验证安装：`lark-cli docs +fetch --api-version v2 --help`

## SKILL.md 更新要点

- 新增前置条件：需要安装 lark-cli 并完成授权
- `create/update` 命令说明中注明缓存文件格式（Markdown，JS 内部转 XML）
- 删除流程保留密码验证逻辑
- 链接到 `references/setup.md` 安装指南

## 保留不变的功能

- CLI 命令接口（list/read/create/update/delete）不变
- 缓存文件命名规则（create-<名称>-YYYYMMDD-HHMMSS.md）
- `--keep`/`--drop` 参数
- 删除密码验证
- 意图识别规则
- 执行播报工作流（读取模板 → 解析 frontmatter → 调 fetching skill → 生成报告）

## 技术约束

- Node.js ESM（`type: module`），`.js` 扩展名
- 使用 `child_process.execSync` 调用 lark-cli
- 缓存文件格式为 Markdown（人类可读），内部转 XML 后传给 lark-cli
- 不需要额外 npm 依赖
