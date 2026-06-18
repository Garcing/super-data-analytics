# 数据分析 Skill 框架设计

**日期**：2026-05-07
**状态**：已批准
**范围**：骨架搭建 + 已有代码迁移

## 背景

当前 `powerbi-analysis` 是一个单一 skill，实现了 PowerBI MCP 连接和 Web 报告生成。现将其升级为一个综合数据分析 skill 框架，包含五个板块（语料、需求、数据、分析、报告），每个板块下有多个子 skill。

## 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 组合方式 | 多个独立 Skill | 模块独立，可单独开发/测试 |
| 通信方式 | 约定式（标准文件格式） | 最简单，零基础设施，LLM agent 天然能衔接 |
| 仓库结构 | 单仓多 Skill | 统一管理，共享 references/ 和 docs/ |
| 语料存储 | 纯飞书文档 | 业务用户直接在飞书编辑 |

## 目录结构

```
powerbi-analysis/
├── CLAUDE.md                            # 全局上下文（整体架构 + 板块说明）
│
├── da-corpus/                           # 板块 0：业务语料
│   ├── SKILL.md                         # 触发词：/da-corpus
│   ├── feishu-client.mjs                # 飞书 API 客户端（骨架）
│   └── templates/                       # 语料模板
│       ├── business-overview.md         # 业务概述模板
│       └── data-assets.md               # 指标/维度/表模板
│
├── da-requirement/                      # 板块 1：需求沟通
│   ├── SKILL.md                         # 触发词：/da-requirement
│   └── templates/
│       └── requirement.md               # 需求文档模板
│
├── da-data/                             # 板块 2：数据获取
│   ├── SKILL.md                         # 板块索引：列出子 skill 及适用场景
│   ├── from-powerbi/                    # ← 已有代码迁入
│   │   ├── SKILL.md                     # 触发词：/da-powerbi
│   │   ├── powerbi-client.mjs           # 从 node_version/ 迁入
│   │   ├── semantic-model-ids.json      # 从根目录迁入
│   │   ├── references/                  # DAX 参考文档（从 references/ 迁入）
│   │   └── package.json
│   └── from-sql/                        # 骨架
│       └── SKILL.md                     # 触发词：/da-sql
│
├── da-analysis/                         # 板块 3：分析
│   ├── SKILL.md                         # 触发词：/da-analysis
│   └── frameworks/                      # 分析框架库（骨架）
│       └── README.md                    # 框架目录说明
│
├── da-report/                           # 板块 4：报告
│   ├── SKILL.md                         # 板块索引：列出子 skill 及适用场景
│   ├── web/                             # ← 已有代码迁入
│   │   ├── SKILL.md                     # 触发词：/da-report-web
│   │   ├── frontend/                    # 从 web-report/ 迁入（React + Vite + Tailwind）
│   │   ├── api/                         # Vercel API routes（从 web-report/api/ 迁入）
│   │   └── uploader/                    # 从 scripts/web_report_builder.py 迁入
│   ├── pdf/                             # 骨架
│   │   └── SKILL.md                     # 触发词：/da-report-pdf
│   ├── ppt/                             # 骨架
│   │   └── SKILL.md                     # 触发词：/da-report-ppt
│   └── image/                           # 骨架
│       └── SKILL.md                     # 触发词：/da-report-image
│
├── references/                          # 全局共享参考文档（SQL 函数、分析方法论等）
└── docs/
    └── superpowers/
        ├── specs/
        └── plans/
```

## 命名约定

- 板块级目录：`da-{板块名}`（da = data analysis）
- 子 skill 目录：板块内的功能子目录（如 `from-powerbi`、`web`）
- 触发词：`/da-{板块}` 或 `/da-{板块}-{功能}`，常用 skill 有简写（如 `/da-powerbi`）
- 每个 SKILL.md 声明：触发词、用途、输入、输出、依赖的其他 skill

## 数据流

```
板块 0              板块 1              板块 2              板块 3            板块 4
da-corpus ──引用──▶ da-requirement ──产出──▶ da-data ──产出──▶ da-analysis ──▶ da-report
    │                    │                    │                   │                │
    └────────────────────┴────────────────────┴───────────────────┘                │
                     所有板块都可以引用板块 0                                   最终交付物
```

### 衔接格式约定

| 衔接点 | 格式 | 说明 |
|--------|------|------|
| 板块 0 → 其他 | 飞书文档内容（Markdown） | skill 内部拉取后转为结构化数据使用 |
| 板块 1 产出 | 需求文档（Markdown） | 包含：场景、目的、指标口径、字段、范围 |
| 板块 1 → 板块 2 | 需求文档中的字段清单 | 明确每个字段从哪取（BI / SQL） |
| 板块 2 产出 | 查询结果 JSON | 统一为 `{ columns: [], rows: [] }` 格式 |
| 板块 2 → 板块 3 | 查询结果 JSON | 作为分析输入 |
| 板块 3 产出 | 分析结论（Markdown + JSON） | 包含洞察描述 + 可视化数据 |
| 板块 3 → 板块 4 | 分析结论 | 转化为报告格式 |
| 板块 4 产出 | 报告 URL / 文件路径 | web: URL; pdf/ppt/image: 本地文件 |

## 各 Skill 定义

### da-corpus（板块 0：业务语料）

- **触发词**：`/da-corpus`
- **用途**：从飞书获取业务背景、指标定义、维度说明、表结构
- **输入**：业务名称或飞书文档 URL
- **输出**：结构化业务知识（指标清单、维度清单、表关系、业务背景文本）
- **依赖**：无
- **实现状态**：骨架（飞书 API 客户端待实现）

### da-requirement（板块 1：需求沟通）

- **触发词**：`/da-requirement`
- **用途**：引导用户明确分析需求的场景、目的、指标口径、字段范围
- **输入**：用户的自然语言描述
- **输出**：标准需求文档（Markdown），包含字段清单和数据来源标注（BI/SQL）
- **依赖**：da-corpus（获取业务知识辅助需求确认）
- **实现状态**：骨架（需求模板 + 引导话术）

### da-data/from-powerbi（板块 2a：PowerBI 数据）

- **触发词**：`/da-powerbi`
- **用途**：从 PowerBI 语义模型查询数据
- **输入**：DAX 查询 + 语义模型 ID
- **输出**：`{ columns: [], rows: [] }` 格式的 JSON 数据集
- **依赖**：无（自包含，可引用 da-corpus 获取字段说明）
- **实现状态**：已实现（Node.js 客户端 + MCP 代理）

### da-data/from-sql（板块 2b：SQL 数据）

- **触发词**：`/da-sql`
- **用途**：生成 SQL 并执行查询
- **输入**：需求文档中的字段清单 + 目标数据库
- **输出**：`{ columns: [], rows: [] }` 格式的 JSON 数据集
- **依赖**：da-corpus（获取表结构、字段定义）
- **实现状态**：骨架

### da-analysis（板块 3：分析）

- **触发词**：`/da-analysis`
- **用途**：基于分析框架指导分析方向，产出洞察结论
- **输入**：数据集 JSON + 分析目的
- **输出**：分析结论（洞察描述 + 可视化数据：chart_type + chart_data）
- **依赖**：da-corpus（获取业务特定分析经验）
- **实现状态**：骨架（框架库目录 + 通用分析模板）

### da-report/web（板块 4a：Web 报告）

- **触发词**：`/da-report-web`
- **用途**：生成 Web 报告并发布到 Vercel
- **输入**：分析结论 JSON
- **输出**：报告 URL（如 `https://project-6hzz6.vercel.app/report/xxx`）
- **依赖**：无
- **实现状态**：已实现（React 前端 + Vercel API + 上传脚本）

### da-report/pdf（板块 4b：PDF 报告）

- **触发词**：`/da-report-pdf`
- **用途**：生成本地 PDF 报告文件
- **输入**：分析结论 JSON
- **输出**：本地文件路径
- **依赖**：无
- **实现状态**：骨架

### da-report/ppt（板块 4c：PPT 报告）

- **触发词**：`/da-report-ppt`
- **用途**：生成本地 PPT 报告文件
- **输入**：分析结论 JSON
- **输出**：本地文件路径
- **依赖**：无
- **实现状态**：骨架

### da-report/image（板块 4d：图片报告）

- **触发词**：`/da-report-image`
- **用途**：生成本地图片报告文件
- **输入**：分析结论 JSON
- **输出**：本地文件路径
- **依赖**：无
- **实现状态**：骨架

## 已有代码迁移清单

| 原位置 | 目标位置 | 说明 |
|--------|----------|------|
| `node_version/powerbi-client.mjs` | `da-data/from-powerbi/powerbi-client.mjs` | Node.js 客户端 |
| `node_version/package.json` | `da-data/from-powerbi/package.json` | 依赖声明 |
| `semantic-model-ids.json` | `da-data/from-powerbi/semantic-model-ids.json` | 模型 ID 配置 |
| `references/dax-*.md` | `da-data/from-powerbi/references/` | DAX 参考文档 |
| `web-report/` | `da-report/web/frontend/` | React + Vite + Tailwind 前端 |
| `scripts/web_report_builder.py` | `da-report/web/uploader/` | 上传脚本 |
| `scripts/chart_generator.py` | `da-report/image/chart_generator.py` | matplotlib 图表生成，web 报告用 Recharts 不依赖此文件 |
| `SKILL.md`（根目录） | 保留或归档 | 原 Python 版 skill 定义 |
| `node_version/SKILL.md` | `da-data/from-powerbi/SKILL.md`（改写） | Node.js 版 skill 定义 |

## 板块级 SKILL.md 定位

`da-data/SKILL.md` 和 `da-report/SKILL.md` 是板块索引文件，不定义触发词，只做：
1. 列出该板块下的子 skill 及其适用场景
2. 帮助 agent 根据用户需求选择正确的子 skill

用户不会直接触发板块级 SKILL.md，而是触发具体的子 skill（如 `/da-powerbi`、`/da-report-web`）。

## 不在本次范围

以下内容本次不实现，仅留骨架：
- 飞书 API 集成（da-corpus 的 feishu-client.mjs）
- SQL 查询引擎（da-data/from-sql 的实现）
- PDF/PPT/Image 报告生成（da-report/pdf、ppt、image 的实现）
- 分析框架内容（da-analysis/frameworks/ 的填充）
- Python 版 MCP 代理迁移（scripts/ 下的旧代码，Node.js 版已替代）
