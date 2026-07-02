---
name: using-templates
description: 数据分析报告模板的全生命周期管理（列表/查询/增加/删除/修改）。模板存储在飞书个人文件夹中，通过 scripts/templates.js CLI 工具进行增删改查，报告模板分为数据播报、周期性报告、复盘性报告、专题分析报告；当用户提到"数据播报"、"参照/按照xxx报告模板"时使用此 skill
metadata:
  skill-series: super-data-analytics
  chinese-name: 调用报告模板
---

# 调用报告模板

工具类 SKILL，负责调用数据报告模板，获取数据分析上下文，提供 Agent 执行生成数据报告。模板存储在飞书个人文件夹中，支持对模板列表/查询/增加/删除/修改操作。所有命令在 `using-templates/` 目录下执行，前缀 `node scripts/templates.js`。

```bash
node scripts/templates.js <命令> [参数]
```

## 凭证配置

凭证统一来自 `~/.super-data-analytics/config.json` 的 `env` 块——脚本不读 `.env`、不依赖环境变量导出。本 SKILL 用到：

- `FEISHU_TEMPLATE_FOLDER_TOKEN` — 模板所在飞书文件夹
- `FEISHU_TEMPLATE_DELETE_PASSWORD` — 删除模板的密码

配置缺失时脚本报错指引补全，由 agent 引导用户提供后写回 config.json，再重试。

## 前置条件

本 SKILL 依赖 lark-cli 操作飞书文档。如果 `node scripts/templates.js list` 报错 "lark-cli error"，请按 [`references/lark-cli-setup.md`](references/lark-cli-setup.md) 安装和配置 lark-cli。

## 意图识别

收到用户请求后，按以下规则判断意图，并执行 `核心流程` 步骤。

| 用户信号 | 意图 |
|---|---|
| "有哪些报告模板"、"管理报告模板" | 列出 |
| "新建报告模板"、"创建报告模板"、"做一个XX播报模板" | 新建 |
| "查看xxxx模板的内容" | 查看 |
| "编辑XX模板"、"修改模板" | 编辑 |
| "删除xxxx模板" | 删除 |

如果用户提到的播报主题在飞书文件夹中找不到匹配的模板，引导用户先创建。

## CLI 工具

所有模板操作通过 `scripts/templates.js`，其中 `--file` 指向 agent 写入 `<工作区>/.super-data-analytics/scratch/` 的临时 markdown 文件。

```bash
# 列出所有播报模板
node scripts/templates.js list

# 读取模板内容
node scripts/templates.js read <doc_id>

# 创建新模板
node scripts/templates.js create --title "播报主题" --file <content_file>

# 更新模板（覆盖同一文档，ID 不变）
node scripts/templates.js update <doc_id> --file <content_file>

# 删除模板（需要密码）
node scripts/templates.js delete <doc_id> --password <密码>
```

## 临时文件命名规范

新建和编辑模板时，agent 先把内容写入临时 markdown 文件，统一放在 `<工作区>/.super-data-analytics/scratch/`，命名格式：

```
template-YYYYMMDD-HHMMSS-<主题title>.md
```

其中 `YYYYMMDD-HHMMSS` 使用当前时间，`<主题title>` 用简短英文/拼音 slug（如 `pilates`、`vip-broadcast`），不要和已有的文件命名冲突。

scratch 文件的生命周期由 agent 自行管理：创建/更新成功后是否删除该临时文件，由 agent 根据情况判断（脚本不再提供 `--drop`，也不自动清理）。

示例：`.super-data-analytics/scratch/template-20260510-143522-pilates.md`

## 格式与播报参考

### 数据播报模板的格式

当要**新建或修改的模板属于"数据播报"类型**时，模板正文的格式（播报主题、业务背景、数据说明、预警规则、格式模板、SQL 代码等段落结构）必须参照 [`references/data-brief-template.md`](references/data-brief-template.md)。先读它，再据此组织模板内容，避免格式随机。

### 播报渠道的 Webhook 格式

当上下文正在**获取数据播报类型的模板、并准备通过 webhook 推送播报**时，在生成播报正文之前，先按目标渠道读对应的格式参考，把它作为后续播报内容/排版的上下文：

- **企微** → 读 [`references/wecom-webhook.md`](references/wecom-webhook.md)
- **飞书** → 读 [`references/lark-webhook.md`](references/lark-webhook.md)

目的是让播报内容契合各渠道能渲染的语法（如企微 markdown_v2 支持表格、飞书卡片用 `table` 组件而非 markdown 表格语法）、长度/频率限制、颜色强调方式等，避免生成出来发不出去或排版错乱。

## 核心流程

### 定位模板

公共步骤，查看、编辑、删除报告模板前，都必须先执行 `node scripts/templates.js list` 获取最新模板列表，再按用户提到的名称或 ID 匹配到 `doc_id`。若找不到匹配项，引导用户从已有选择或新建。

### 列出

执行 `node scripts/templates.js list`，向用户展示名称、数据源类型、最后修改时间。

### 新建

1. 按照播报模板规范，向用户收集业务信息，总结出播报主题。
2. 生成模板内容，写入 `<工作区>/.super-data-analytics/scratch/template-YYYYMMDD-HHMMSS-<主题>.md`
3. `node scripts/templates.js create --title "播报主题" --file <工作区>/.super-data-analytics/scratch/template-YYYYMMDD-HHMMSS-<主题>.md`
4. 向用户展示创建结果（名称、doc_id、飞书链接）

### 查看

定位模板 → `node scripts/templates.js read <doc_id>` → 返回 Markdown 内容

### 编辑

定位模板 → `read` 获取当前内容 → 按用户要求修改，写入 `<工作区>/.super-data-analytics/scratch/template-YYYYMMDD-HHMMSS-<主题>.md` → `node scripts/templates.js update <doc_id> --file <工作区>/.super-data-analytics/scratch/template-YYYYMMDD-HHMMSS-<主题>.md`

### 删除

定位模板 → 确认要删除的模板 → 向用户索取密码 → `node scripts/templates.js delete <doc_id> --password <密码>`
