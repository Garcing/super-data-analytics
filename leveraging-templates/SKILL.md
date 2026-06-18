---
name: leveraging-templates
description: 数据分析报告模板的全生命周期管理（列表/查询/增加/删除/修改）。模板存储在飞书个人文件夹中，通过 scripts/templates.js CLI 工具进行增删改查，报告模板分为数据播报、周期性报告、复盘性报告、专题分析报告；当用户提到"数据播报"、"参照/按照xxx报告模板"时使用此 skill
metadata: 
  skill-series: super-data-analytics
  chinese-name: 调用报告模板
---

# 调用报告模板

工具类SKILL，负责调用数据报告模板，获取数据分析上下文，提供Agent执行生成数据报告。模板存储在飞书个人文件夹中，支持对模板列表/查询/增加/删除/修改操作。

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
| ”删除xxxx模板“ | 删除 |

如果用户提到的播报主题在飞书文件夹中找不到匹配的模板，引导用户先创建。

## CLI 工具

所有模板操作通过 `scripts/templates.js`，其中 `content_file` 是生成临时文件的路径，默认保存在  `cache/` 目录下

```bash
# 列出所有播报模板
node scripts/templates.js list

# 读取模板内容
node scripts/templates.js read <doc_id>

# 创建新模板（默认保留临时文件，加 --drop 执行后删除）
node scripts/templates.js create --title "播报主题" --file <content_file> [--drop]

# 更新模板（覆盖同一文档，ID 不变，默认保留临时文件，加 --drop 执行后删除）
node scripts/templates.js update <doc_id> --file <content_file> [--drop]

# 删除模板（需要密码）
node scripts/templates.js delete <doc_id> --password <密码>
```

## 临时文件命名规范

新建模板（read）和更新模板（update）时要求先将内容写入 `cache/` 目录，文件具体命名格式如下：

其中 `YYYYMMDD-HHMMSS` 使用当前时间，`<random>` 使用至少 10 位随机字母数字，如 `cache/create-20260510-143522-a7f3c98f4k.md`，不要和已有的文件命名冲突。

- read：`cache/create-<播报主题>-YYYYMMDD-HHMMSS.md`
- update：`cache/update-<播报主题>-YYYYMMDD-HHMMSS.md`

## 核心流程

### 定位模板

公共步骤，查看、编辑、删除报告模板前，都必须先执行 `node scripts/templates.js list` 获取最新模板列表，再按用户提到的名称或 ID 匹配到 `doc_id`。若找不到匹配项，引导用户从已有选择或新建。

### 列出

执行 `node scripts/templates.js list`，向用户展示名称、数据源类型、最后修改时间。

### 新建

1. 按照播报模板规范，向用户收集业务信息，总结出播报主题。
2. 生成模板内容，写入 `cache/create-<播报主题>-YYYYMMDD-HHMMSS.md`
3. `node scripts/templates.js create --title "播报主题" --file cache/create-<播报主题>-YYYYMMDD-HHMMSS.md`
4. 向用户展示创建结果（名称、doc_id、飞书链接）

### 查看

定位模板 → `node scripts/templates.js read <doc_id>` → 返回 Markdown 内容

### 编辑

定位模板 → `read` 获取当前内容 → 按用户要求修改，写入 `cache/update-<播报主题>-YYYYMMDD-HHMMSS.md` → `node scripts/templates.js update <doc_id> --file cache/update-<播报主题>-YYYYMMDD-HHMMSS.md`

### 删除

定位模板 → 确认要删除的模板 → 向用户索取密码 → `node scripts/templates.js delete <doc_id> --password <密码>`
