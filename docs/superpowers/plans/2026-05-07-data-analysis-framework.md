# 数据分析 Skill 框架骨架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将单一 powerbi-analysis skill 重构为多 skill 数据分析框架（骨架 + 已有代码迁移）

**Architecture:** 约定式多 skill 单仓结构，五个板块（语料/需求/数据/分析/报告）各自独立目录，已有代码从旧位置迁移到对应板块目录下，骨架 skill 只包含 SKILL.md 和模板文件

**Tech Stack:** Node.js（PowerBI 客户端）、Python（报告上传/图表生成）、React + Vite（Web 前端）

---

### Task 1: 创建板块目录结构

**Files:**
- Create: `da-corpus/`、`da-corpus/templates/`
- Create: `da-requirement/`、`da-requirement/templates/`
- Create: `da-data/`、`da-data/from-sql/`
- Create: `da-analysis/`、`da-analysis/frameworks/`
- Create: `da-report/`、`da-report/pdf/`、`da-report/ppt/`、`da-report/image/`

- [ ] **Step 1: 创建所有空目录**

```bash
cd c:/Users/Administrator/.agents/skills/powerbi-analysis
mkdir -p da-corpus/templates da-requirement/templates da-data/from-sql da-analysis/frameworks da-report/pdf da-report/ppt da-report/image
```

- [ ] **Step 2: 验证目录结构**

```bash
find da-corpus da-requirement da-data da-analysis da-report -type d | sort
```

Expected: 列出所有新创建的板块目录

- [ ] **Step 3: Commit**

```bash
git add da-corpus/ da-requirement/ da-data/ da-analysis/ da-report/
git commit -m "chore: create multi-skill framework directory structure"
```

---

### Task 2: 迁移 PowerBI 客户端到 da-data/from-powerbi

**Files:**
- Move: `node_version/powerbi-client.mjs` → `da-data/from-powerbi/powerbi-client.mjs`
- Move: `node_version/package.json` → `da-data/from-powerbi/package.json`
- Move: `node_version/.gitignore` → `da-data/from-powerbi/.gitignore`
- Move: `semantic-model-ids.json` → `da-data/from-powerbi/semantic-model-ids.json`
- Move: `references/dax-*.md` → `da-data/from-powerbi/references/`
- Create: `da-data/from-powerbi/SKILL.md`

- [ ] **Step 1: 创建目标目录并迁移文件**

```bash
cd c:/Users/Administrator/.agents/skills/powerbi-analysis
mkdir -p da-data/from-powerbi/references

# 迁移核心文件
cp node_version/powerbi-client.mjs da-data/from-powerbi/powerbi-client.mjs
cp node_version/package.json da-data/from-powerbi/package.json
cp node_version/.gitignore da-data/from-powerbi/.gitignore
cp semantic-model-ids.json da-data/from-powerbi/semantic-model-ids.json

# 迁移 DAX 参考文档
cp references/dax-aggregation.md da-data/from-powerbi/references/
cp references/dax-datetime.md da-data/from-powerbi/references/
cp references/dax-filter.md da-data/from-powerbi/references/
cp references/dax-logic.md da-data/from-powerbi/references/
cp references/dax-table.md da-data/from-powerbi/references/
cp references/dax-text.md da-data/from-powerbi/references/
```

- [ ] **Step 2: 安装依赖**

```bash
cd da-data/from-powerbi && npm install
```

Expected: `node_modules/` 创建成功，`@azure/identity` 安装完成

- [ ] **Step 3: 写 SKILL.md**

```markdown
---
name: da-powerbi
description: 从 PowerBI 语义模型查询数据，通过 Node.js 直接调用微软 MCP HTTP 端点，Client Credentials 认证
---

# PowerBI 数据获取

从 Power BI 语义模型查询数据，使用 Client Credentials 认证（零交互）。

## 触发条件

- 用户需要从 Power BI 获取数据
- 用户使用 `/da-powerbi` 命令
- 其他 skill 需要查询 Power BI 数据时引用

## 环境要求

- Node.js 18+
- Azure AD 凭证（`.env` 文件或环境变量）：`POWERBI_CLIENT_ID`、`POWERBI_CLIENT_SECRET`、`POWERBI_TENANT_ID`

## CLI 命令

所有命令通过 `node da-data/from-powerbi/powerbi-client.mjs` 执行。

```bash
# 列出可用工具
node da-data/from-powerbi/powerbi-client.mjs list-tools

# 获取语义模型架构
node da-data/from-powerbi/powerbi-client.mjs schema <artifactId>

# 执行 DAX 查询
node da-data/from-powerbi/powerbi-client.mjs query <artifactId> "EVALUATE ..."
```

## 核心流程

Phase 1（读取模型 ID）→ Phase 2（获取 Schema）→ Phase 3（写 DAX）→ Phase 4（执行查询）

### Phase 1：读取语义模型 ID

从 `da-data/from-powerbi/semantic-model-ids.json` 获取模型 ID：
- 默认使用 `is_default: true` 的模型
- 用户指定业务线时使用对应模型

### Phase 2：获取语义模型架构

```bash
node da-data/from-powerbi/powerbi-client.mjs schema <artifactId>
```

返回包含表、列、度量值和关系的完整架构。已获取的 Schema 缓存 24 小时。

### Phase 3：生成 DAX 语句

根据用户问题 + 模型架构编写 DAX。参考 `da-data/from-powerbi/references/` 下的函数文档。

**DAX 编写检查清单**：
1. 计算的初始筛选上下文是什么？
2. 涉及哪些表？关系和筛选方向？
3. 是否需要 CALCULATE 修改筛选器？
4. 完成后检查：是否复用了已有度量值？表/列/度量值名称是否在 schema 中？

### Phase 4：执行查询

```bash
node da-data/from-powerbi/powerbi-client.mjs query <artifactId> "DAX语句"
```

输出格式：`{ columns: [...], rows: [[...], [...]] }` 的 JSON 数据集。

## 输入

- 语义模型 ID（从 `semantic-model-ids.json` 选取）
- DAX 查询语句

## 输出

JSON 数据集，格式：`{ columns: [{Name, Type}], rows: [[val1, val2, ...]] }`

## 依赖

- 无（自包含，但可引用 da-corpus 获取字段说明辅助 DAX 编写）

## 可引用资源

- `references/dax-aggregation.md` — 聚合函数（SUM, SUMX, AVERAGEX 等）
- `references/dax-datetime.md` — 时间智能函数（DATEADD, SAMEPERIODLASTYEAR 等）
- `references/dax-filter.md` — 筛选函数（CALCULATE, FILTER, ALL 等）
- `references/dax-logic.md` — 逻辑函数（IF, SWITCH, ISBLANK 等）
- `references/dax-table.md` — 表函数（TOPN, SUMMARIZE, VALUES 等）
- `references/dax-text.md` — 文本函数（CONCATENATEX, SEARCH 等）
```

Write this content to `da-data/from-powerbi/SKILL.md`.

- [ ] **Step 4: 验证迁移后 CLI 可用**

```bash
cd c:/Users/Administrator/.agents/skills/powerbi-analysis
node da-data/from-powerbi/powerbi-client.mjs --help
```

Expected: 输出用法说明（或未知命令提示，说明 CLI 加载正常）

- [ ] **Step 5: Commit**

```bash
git add da-data/from-powerbi/
git commit -m "feat: migrate powerbi client to da-data/from-powerbi with new SKILL.md"
```

---

### Task 3: 迁移 Web 前端到 da-report/web

**Files:**
- Move: `web-report/*` → `da-report/web/frontend/`
- Move: `scripts/web_report_builder.py` → `da-report/web/uploader/web_report_builder.py`
- Create: `da-report/web/SKILL.md`

- [ ] **Step 1: 创建目标目录并迁移前端文件**

```bash
cd c:/Users/Administrator/.agents/skills/powerbi-analysis
mkdir -p da-report/web/frontend da-report/web/uploader

# 迁移前端（保留 node_modules 和 dist 不迁，重新安装）
cp web-report/.env.example da-report/web/frontend/
cp web-report/.gitignore da-report/web/frontend/
cp web-report/index.html da-report/web/frontend/
cp web-report/postcss.config.js da-report/web/frontend/
cp web-report/tailwind.config.js da-report/web/frontend/
cp web-report/vite.config.js da-report/web/frontend/
cp -r web-report/public da-report/web/frontend/
cp -r web-report/api da-report/web/frontend/
cp -r web-report/lib da-report/web/frontend/
cp -r web-report/src da-report/web/frontend/

# 迁移上传脚本
cp scripts/web_report_builder.py da-report/web/uploader/web_report_builder.py
```

- [ ] **Step 2: 创建 package.json 和 vercel.json**

web-report 目录中缺少这两个文件，需要重新创建。

`da-report/web/frontend/package.json`：

```json
{
  "name": "powerbi-web-report",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^7.0.0",
    "recharts": "^2.12.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.3",
    "vite": "^6.0.0"
  }
}
```

`da-report/web/frontend/vercel.json`：

```json
{
  "version": 2,
  "builds": [
    { "src": "api/index.ts", "use": "@vercel/node" },
    { "src": "package.json", "use": "@vercel/static-build", "config": { "distDir": "dist" } }
  ],
  "rewrites": [
    { "source": "/api/reports(.*)", "destination": "/api" },
    { "source": "/api/reports", "destination": "/api" },
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ]
}
```

- [ ] **Step 3: 安装前端依赖**

```bash
cd da-report/web/frontend && npm install
```

Expected: `node_modules/` 创建成功

- [ ] **Step 4: 写 SKILL.md**

```markdown
---
name: da-report-web
description: 生成 Web 分析报告并发布到 Vercel，返回可分享的公网 URL
---

# Web 报告生成

生成 Web 分析报告并上传到 Vercel，返回可分享的公网 URL。

## 触发条件

- 用户需要生成可分享的分析报告
- 用户使用 `/da-report-web` 命令
- 分析完成后需要可视化交付

## 报告 JSON 格式

```json
{
  "meta": {
    "title": "报告标题",
    "generated_at": "ISO 8601 时间戳",
    "model": "语义模型名称"
  },
  "summary": {
    "overall": "整体结论概述（2-3句）",
    "total_conclusions": 5,
    "high_importance_count": 2,
    "kpis": [
      {
        "label": "指标名称",
        "value": "核心数值",
        "trend": "up | down | neutral",
        "trend_value": "趋势说明"
      }
    ]
  },
  "conclusions": [
    {
      "id": 1,
      "title": "结论标题",
      "description": "详细描述",
      "data_support": "数据支撑",
      "importance": "high | medium | low",
      "chart_type": "bar | line | pie | scatter",
      "chart_data": {}
    }
  ]
}
```

### chart_data 格式

- **bar**: `{ "xKey": "name", "yKey": "value", "data": [{"name":"A","value":100}] }`
- **line**: `{ "x_labels": ["1月","2月"], "series": {"指标A":[100,200]} }`
- **pie**: `{ "labels": ["A","B"], "values": [60,40] }`
- **scatter**: `{ "x":[1,2], "y":[3,4], "x_title":"X", "y_title":"Y" }`

## 调用方式

```python
from da-report.web.uploader.web_report_builder import publish_report

url = publish_report(report_data, 'report-20260415-分析主题')
# 返回: https://project-6hzz6.vercel.app/report/report-20260415-分析主题
```

## 环境变量

- `VERCEL_REPORTS_URL` — Vercel 项目 URL
- `VERCEL_API_SECRET` — API 密钥

从 `.env` 文件自动加载。

## 输入

- 分析结论 JSON（含 meta + summary + conclusions）

## 输出

- 报告公网 URL（如 `https://project-6hzz6.vercel.app/report/report-xxx`）

## 依赖

- 无

## Vercel 部署

```bash
cd da-report/web/frontend && rm -rf dist && vercel deploy --prod --force
```

注意：必须先 `rm -rf dist` 清除构建缓存再部署。
```

Write this content to `da-report/web/SKILL.md`.

- [ ] **Step 5: Commit**

```bash
git add da-report/web/
git commit -m "feat: migrate web-report to da-report/web with new SKILL.md"
```

---

### Task 4: 迁移图表生成器到 da-report/image

**Files:**
- Move: `scripts/chart_generator.py` → `da-report/image/chart_generator.py`
- Create: `da-report/image/SKILL.md`

- [ ] **Step 1: 迁移文件**

```bash
cd c:/Users/Administrator/.agents/skills/powerbi-analysis
cp scripts/chart_generator.py da-report/image/chart_generator.py
```

- [ ] **Step 2: 写 SKILL.md**

```markdown
---
name: da-report-image
description: 生成本地图片报告，基于 matplotlib + seaborn 渲染商业级图表
---

# 图片报告生成

基于 matplotlib + seaborn 生成本地 PNG 图表文件。

## 触发条件

- 用户需要快速查看数据可视化（不需要分享）
- 用户使用 `/da-report-image` 命令
- 其他报告格式（PDF/PPT）需要本地图表素材

## 调用方式

```python
from da-report.image.chart_generator import generate_chart

filepath = generate_chart(data, chart_type, title)
# 返回: 绝对路径如 C:\...\output\20260410_121000_line_趋势分析.png
```

## 参数说明

- **data**: `List[Dict]` — 数据列表，结构因图表类型而异
- **chart_type**: `str` — 图表类型枚举
- **title**: `str` — 图表标题

### chart_type 可选值

| 类型 | 用途 | data 结构 |
|------|------|-----------|
| `bar` | 分类对比 | 第1 Key=分类维度，第2 Key=数值 |
| `line` | 时间趋势 | 第1 Key=时间维度，后续 Key=数值指标 |
| `donut` | 构成比例 | 第1 Key=分类，第2 Key=数值 |
| `combo` | 双指标对比 | 3 个 Key：维度+柱状值+折线值 |
| `scatter` | 相关性 | 2-3 个数值 Key，第3个为气泡大小 |
| `box` | 分布/异常值 | 第1 Key=分类，第2 Key=数值 |
| `heatmap` | 相关矩阵 | 多个数值列，自动计算相关系数 |

## 输入

- 分析结论 JSON（含 chart_type + chart_data）

## 输出

- 本地 PNG 文件路径

## 依赖

- Python 3.10+
- pandas, matplotlib, seaborn, numpy
```

Write this content to `da-report/image/SKILL.md`.

- [ ] **Step 3: Commit**

```bash
git add da-report/image/
git commit -m "feat: migrate chart generator to da-report/image with SKILL.md"
```

---

### Task 5: 写骨架 SKILL.md — da-corpus

**Files:**
- Create: `da-corpus/SKILL.md`
- Create: `da-corpus/templates/business-overview.md`
- Create: `da-corpus/templates/data-assets.md`
- Create: `da-corpus/feishu-client.mjs`（空骨架）

- [ ] **Step 1: 写 SKILL.md**

```markdown
---
name: da-corpus
description: 业务语料管理，从飞书获取业务背景、指标定义、维度说明、表结构等知识
---

# 业务语料管理

从飞书文档获取业务知识，供其他所有 skill 引用。

## 触发条件

- 用户使用 `/da-corpus` 命令
- 其他 skill 需要业务背景知识时自动引用

## 用途

1. **业务概述**：获取业务背景描述、经营分析思路
2. **数据资产管理**：指标定义、维度说明、表结构

## 核心流程

1. 根据业务名称或飞书文档 URL，调用飞书 API 获取文档内容
2. 解析文档为结构化业务知识
3. 返回给调用方使用

## 输入

- 业务名称（如"平台治理"、"超级VIP"）
- 或飞书文档 URL

## 输出

结构化业务知识：
- 指标清单（名称、定义、口径、计算公式）
- 维度清单（名称、层级、取值范围）
- 表关系（表名、字段、主外键）
- 业务背景文本

## 依赖

- 无

## 实现状态

骨架。飞书 API 客户端待实现。

### 语料模板

参考 `da-corpus/templates/` 下的模板文件：
- `business-overview.md` — 业务概述模板
- `data-assets.md` — 指标/维度/表管理模板
```

Write this content to `da-corpus/SKILL.md`.

- [ ] **Step 2: 写业务概述模板**

```markdown
# 业务概述：{业务名称}

## 业务背景

{业务的总体描述，包括业务模式、核心目标、关键成功因素}

## 经营分析思路

### 核心关注指标
- {指标1}：{为什么关注}
- {指标2}：{为什么关注}

### 常见分析场景
1. {场景1}：{描述}
2. {场景2}：{描述}

### 分析框架
- {常用的分析方法，如趋势分析、漏斗分析、归因分析等}
```

Write this content to `da-corpus/templates/business-overview.md`.

- [ ] **Step 3: 写数据资产模板**

```markdown
# 数据资产管理：{业务名称}

## 指标管理

### {指标名称}
- **定义**：{指标的业务含义}
- **口径**：{计算公式或取值规则}
- **数据来源**：{Power BI 语义模型 / SQL 表}
- **更新频率**：{日更/周更/月更}

---

## 维度管理

### {维度名称}
- **定义**：{维度的业务含义}
- **层级**：{如有层级，列出层级结构}
- **取值范围**：{常见取值或取值规则}

---

## 表管理

### {表名称}
- **用途**：{表的业务用途}
- **关键字段**：
  - {字段1}：{类型，说明}
  - {字段2}：{类型，说明}
- **关联关系**：{与其他表的关系}
```

Write this content to `da-corpus/templates/data-assets.md`.

- [ ] **Step 4: 创建飞书客户端骨架**

```javascript
// 飞书 API 客户端（骨架）
// 待实现：飞书文档读取、Wiki 空间浏览等功能

export class FeishuClient {
  constructor() {
    // TODO: 飞书应用凭证配置
  }

  async getDocument(docId) {
    throw new Error('feishu-client.mjs: 飞书 API 集成待实现');
  }

  async searchDocuments(query) {
    throw new Error('feishu-client.mjs: 飞书 API 集成待实现');
  }
}
```

Write this content to `da-corpus/feishu-client.mjs`.

- [ ] **Step 5: Commit**

```bash
git add da-corpus/
git commit -m "feat: add da-corpus skeleton with templates and feishu client stub"
```

---

### Task 6: 写骨架 SKILL.md — da-requirement

**Files:**
- Create: `da-requirement/SKILL.md`
- Create: `da-requirement/templates/requirement.md`

- [ ] **Step 1: 写 SKILL.md**

```markdown
---
name: da-requirement
description: 需求沟通，引导用户明确分析需求的场景、目的、指标口径、字段范围
---

# 需求沟通

引导用户将模糊的分析想法转化为标准需求文档，明确业务场景、分析目的、指标口径和字段范围。

## 触发条件

- 用户提出分析需求（如"帮我分析下复购率"、"看看这个月的投诉情况"）
- 用户使用 `/da-requirement` 命令

## 核心流程

1. 理解用户初始需求描述
2. 逐一确认以下要素（通过提问引导）：
   - 业务场景：这次分析的业务背景是什么？
   - 分析目的：是要发现问题、验证假设、还是定期监控？
   - 指标与口径：核心指标怎么定义？对比基准是什么？
   - 时间与范围：分析的时间段？业务线/区域等筛选条件？
   - 交付形式：Web 报告 / 本地图表 / 仅数据表格？
3. 确认每个字段/指标的数据来源（Power BI / SQL）
4. 产出标准需求文档

## 需求确认引导要点

针对互联网数据分析师常见场景：

- **趋势分析**：确认时间粒度（日/周/月）、对比基准（环比/同比）
- **对比分析**：确认对比维度（时间/人群/渠道）、统计显著性要求
- **归因分析**：确认拆解维度和层级
- **漏斗分析**：确认漏斗步骤定义和口径
- **实验分析**：确认实验组/对照组、核心指标、观察周期

## 输入

- 用户的自然语言描述

## 输出

标准需求文档（Markdown），包含：
- 业务场景
- 分析目的
- 指标清单（含口径定义）
- 字段清单（含数据来源标注：BI/SQL）
- 时间范围与筛选条件
- 期望交付形式

## 依赖

- da-corpus（获取业务知识辅助需求确认）

## 实现状态

骨架。需求模板已就绪。

### 需求模板

参考 `da-requirement/templates/requirement.md`。
```

Write this content to `da-requirement/SKILL.md`.

- [ ] **Step 2: 写需求文档模板**

```markdown
# 分析需求文档

## 基本信息

- **需求日期**：{YYYY-MM-DD}
- **需求方**：{提出需求的人或团队}
- **业务线**：{关联的业务线}

## 业务场景

{描述这次分析的业务背景，为什么要做这个分析}

## 分析目的

{明确分析要回答的问题，如：发现XX下降的原因、验证XX策略的效果}

## 指标与口径

| 指标名称 | 定义 | 计算口径 | 对比基准 |
|----------|------|----------|----------|
| {指标1} | {业务含义} | {计算公式} | {环比/同比/目标值} |
| {指标2} | {业务含义} | {计算公式} | {环比/同比/目标值} |

## 字段与数据来源

| 字段名称 | 说明 | 数据来源 | 来源表/模型 |
|----------|------|----------|-------------|
| {字段1} | {用途} | Power BI / SQL | {表名} |
| {字段2} | {用途} | Power BI / SQL | {表名} |

## 筛选条件

- **时间范围**：{起始日期} ~ {结束日期}
- **业务筛选**：{业务线/区域/渠道等}
- **其他条件**：{如排除异常数据等}

## 期望交付

- [ ] Web 报告（可分享链接）
- [ ] 本地图表（PNG）
- [ ] PDF 报告
- [ ] PPT 报告
- [ ] 仅数据表格
```

Write this content to `da-requirement/templates/requirement.md`.

- [ ] **Step 3: Commit**

```bash
git add da-requirement/
git commit -m "feat: add da-requirement skeleton with requirement template"
```

---

### Task 7: 写骨架 SKILL.md — da-data 板块级 + from-sql

**Files:**
- Create: `da-data/SKILL.md`
- Create: `da-data/from-sql/SKILL.md`

- [ ] **Step 1: 写板块级 SKILL.md**

```markdown
---
name: da-data
description: 数据获取板块，提供从不同数据源查询数据的能力
---

# 数据获取

本板块包含多个数据获取子 skill，根据数据源选择对应的子 skill。

## 子 skill 列表

| 子 skill | 触发词 | 数据源 | 状态 |
|----------|--------|--------|------|
| from-powerbi | `/da-powerbi` | Power BI 语义模型 | 已实现 |
| from-sql | `/da-sql` | SQL 数据库 | 骨架 |

## 选择依据

- 数据在 Power BI 语义模型中 → 使用 `/da-powerbi`
- 数据需要从数据库直接查询 → 使用 `/da-sql`
- 不确定数据来源 → 先引用 `da-corpus` 确认数据资产

## 统一输出格式

所有子 skill 输出统一的 JSON 数据集格式：

```json
{
  "columns": [{"Name": "列名", "Type": "类型"}],
  "rows": [["值1", "值2"], ["值1", "值2"]]
}
```
```

Write this content to `da-data/SKILL.md`.

- [ ] **Step 2: 写 from-sql SKILL.md**

```markdown
---
name: da-sql
description: SQL 数据查询，根据需求文档生成 SQL 并执行查询
---

# SQL 数据查询

根据需求文档中的字段清单，生成 SQL 语句并执行查询。

## 触发条件

- 用户需要从数据库查询数据（非 Power BI）
- 用户使用 `/da-sql` 命令
- 需求文档中标注字段来源为 SQL

## 核心流程

1. 读取需求文档中的字段清单
2. 引用 da-corpus 获取表结构和字段定义
3. 生成 SQL 查询语句
4. 执行查询并返回结果

## 输入

- 需求文档中的字段清单
- 目标数据库连接信息

## 输出

JSON 数据集，格式：`{ columns: [...], rows: [...] }`

## 依赖

- da-corpus（获取表结构、字段定义）

## 实现状态

骨架。SQL 生成和执行引擎待实现。
```

Write this content to `da-data/from-sql/SKILL.md`.

- [ ] **Step 3: Commit**

```bash
git add da-data/SKILL.md da-data/from-sql/SKILL.md
git commit -m "feat: add da-data board index and from-sql skeleton"
```

---

### Task 8: 写骨架 SKILL.md — da-analysis

**Files:**
- Create: `da-analysis/SKILL.md`
- Create: `da-analysis/frameworks/README.md`

- [ ] **Step 1: 写 SKILL.md**

```markdown
---
name: da-analysis
description: 分析框架，指导分析方向，产出洞察结论和可视化数据
---

# 分析框架

基于分析框架库指导分析方向，从数据集中发现洞察并产出结论。

## 触发条件

- 用户需要对数据进行分析
- 用户使用 `/da-analysis` 命令
- 数据获取完成后进入分析环节

## 核心流程

1. 确定分析类型（趋势/对比/归因/漏斗/实验等）
2. 从框架库中匹配对应的分析方法
3. 应用分析框架对数据集进行处理
4. 产出洞察结论和可视化数据

## 输入

- 数据集 JSON（格式：`{ columns: [], rows: [] }`）
- 分析目的（来自需求文档）

## 输出

分析结论，包含：
- 洞察描述（Markdown 文本）
- 可视化数据（chart_type + chart_data）
- 建议的行动项

### 可视化数据格式

与 da-report 的输入格式对齐：

```json
{
  "chart_type": "bar | line | pie | scatter",
  "chart_data": {}
}
```

## 依赖

- da-corpus（获取业务特定的分析经验和业务知识）

## 框架库

分析框架存放在 `da-analysis/frameworks/` 目录下。每个框架是一个 Markdown 文件，包含：
- 适用场景
- 分析步骤
- 常见陷阱
- 结论模板

当前为骨架，待填充框架内容。

## 实现状态

骨架。框架库待填充。
```

Write this content to `da-analysis/SKILL.md`.

- [ ] **Step 2: 写框架库说明**

```markdown
# 分析框架库

此目录存放分析框架文件。每个框架是一个 Markdown 文件，定义特定分析类型的方法论。

## 框架命名

`{分析类型}.md`，如 `trend-analysis.md`、`funnel-analysis.md`

## 框架文件结构

```markdown
# {框架名称}

## 适用场景
{描述什么情况下使用此框架}

## 分析步骤
1. {步骤1}
2. {步骤2}
...

## 常见陷阱
- {陷阱1}
- {陷阱2}

## 结论模板
{产出的标准格式}
```

## 待填充框架

- `trend-analysis.md` — 趋势分析
- `comparison-analysis.md` — 对比分析
- `attribution-analysis.md` — 归因分析
- `funnel-analysis.md` — 漏斗分析
- `retention-analysis.md` — 留存分析
- `experiment-analysis.md` — AB 实验分析
```

Write this content to `da-analysis/frameworks/README.md`.

- [ ] **Step 3: Commit**

```bash
git add da-analysis/
git commit -m "feat: add da-analysis skeleton with frameworks directory"
```

---

### Task 9: 写骨架 SKILL.md — da-report 板块级 + pdf/ppt

**Files:**
- Create: `da-report/SKILL.md`
- Create: `da-report/pdf/SKILL.md`
- Create: `da-report/ppt/SKILL.md`

- [ ] **Step 1: 写板块级 SKILL.md**

```markdown
---
name: da-report
description: 报告生成板块，支持 Web/PDF/PPT/图片多种报告格式
---

# 报告生成

本板块包含多种报告生成子 skill，根据交付需求选择对应格式。

## 子 skill 列表

| 子 skill | 触发词 | 输出 | 状态 |
|----------|--------|------|------|
| web | `/da-report-web` | 公网 URL | 已实现 |
| pdf | `/da-report-pdf` | 本地 PDF 文件 | 骨架 |
| ppt | `/da-report-ppt` | 本地 PPT 文件 | 骨架 |
| image | `/da-report-image` | 本地 PNG 文件 | 已实现 |

## 选择依据

- 需要在线分享 → `/da-report-web`
- 需要正式文档 → `/da-report-pdf`
- 需要演示汇报 → `/da-report-ppt`
- 快速查看图表 → `/da-report-image`

## 统一输入格式

所有子 skill 接受相同的分析结论 JSON：

```json
{
  "meta": { "title": "", "generated_at": "", "model": "" },
  "summary": { "overall": "", "kpis": [] },
  "conclusions": [
    { "title": "", "description": "", "chart_type": "", "chart_data": {} }
  ]
}
```
```

Write this content to `da-report/SKILL.md`.

- [ ] **Step 2: 写 PDF SKILL.md**

```markdown
---
name: da-report-pdf
description: 生成本地 PDF 分析报告文件
---

# PDF 报告生成

将分析结论生成为本地 PDF 文件。

## 触发条件

- 用户需要正式的 PDF 格式报告
- 用户使用 `/da-report-pdf` 命令

## 输入

分析结论 JSON（含 meta + summary + conclusions）

## 输出

本地 PDF 文件路径

## 依赖

- 无

## 实现状态

骨架。
```

Write this content to `da-report/pdf/SKILL.md`.

- [ ] **Step 3: 写 PPT SKILL.md**

```markdown
---
name: da-report-ppt
description: 生成本地 PPT 分析报告文件
---

# PPT 报告生成

将分析结论生成本地 PPT 文件。

## 触发条件

- 用户需要用于演示汇报的 PPT 格式报告
- 用户使用 `/da-report-ppt` 命令

## 输入

分析结论 JSON（含 meta + summary + conclusions）

## 输出

本地 PPT 文件路径

## 依赖

- 无

## 实现状态

骨架。
```

Write this content to `da-report/ppt/SKILL.md`.

- [ ] **Step 4: Commit**

```bash
git add da-report/SKILL.md da-report/pdf/SKILL.md da-report/ppt/SKILL.md
git commit -m "feat: add da-report board index, pdf and ppt skeletons"
```

---

### Task 10: 更新 CLAUDE.md 为框架级全局上下文

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 重写 CLAUDE.md**

将 `CLAUDE.md` 从单一 skill 说明更新为框架级全局上下文。保留关键技术信息（Azure AD、Vercel 部署），更新项目结构为新的多 skill 布局。

```markdown
# 数据分析 Skill 框架

综合数据分析能力，包含五个板块：语料、需求、数据获取、分析、报告。

## 架构

```
da-corpus/              板块 0：业务语料（飞书文档）
da-requirement/         板块 1：需求沟通
da-data/                板块 2：数据获取
  from-powerbi/           Power BI（已实现）
  from-sql/               SQL 查询（骨架）
da-analysis/            板块 3：分析框架
da-report/              板块 4：报告生成
  web/                    Web 报告（已实现）
  pdf/                    PDF 报告（骨架）
  ppt/                    PPT 报告（骨架）
  image/                  图片报告（已实现）
```

## 数据流

板块 0（语料）← 所有板块可引用
板块 1（需求）→ 板块 2（数据）→ 板块 3（分析）→ 板块 4（报告）

## Azure AD 配置

- 应用：`client_id: d44d3dbe-2b19-4ed0-ad47-ccd50627e9a5`
- 租户：`7d20639b-c6a8-4cdc-9cfe-6ea75b3af0c9`
- Client secret 已生成并验证可用
- 需要 Application 类型权限 + Admin Consent

## Vercel 部署

- 项目：`powerbi-analysis`，域名：`project-6hzz6.vercel.app`
- Blob Store：Public 访问模式
- 重新部署：`cd da-report/web/frontend && rm -rf dist && vercel deploy --prod --force`
- 必须先 `rm -rf dist` 清除构建缓存

## 前端技术栈

React 18 + Vite 6 + Tailwind CSS 3 + Recharts 2 + React Router 7

字体：Source Sans 3（正文/UI）、Cormorant Garamond（标题/数字）、IBM Plex Mono（标签/代码）

全局背景色 `--bg-primary: #faf7f2`，Warm Parchment 主题

## 关键注意事项

- **Vercel 构建缓存**：修改前端代码后必须 `rm -rf dist` 再部署
- **API 路由**：`da-report/web/frontend/api/index.ts` 单文件，通过 URL 解析分发
- **DAX 编写**：必须通过 `GetSemanticModelSchema` 确认字段名，参考 `da-data/from-powerbi/references/`
- **@vercel/blob**：`put()` 必须指定 `access: 'public'`，读取用 `head()` + `fetch(url)`

## 旧代码保留

以下旧代码保留在原位置，待确认新框架稳定后清理：
- `node_version/` — Node.js 旧位置（已迁移到 `da-data/from-powerbi/`）
- `scripts/` — Python 脚本旧位置（已迁移到 `da-report/`）
- `web-report/` — 前端旧位置（已迁移到 `da-report/web/frontend/`）
- `references/` — DAX 文档旧位置（已迁移到 `da-data/from-powerbi/references/`）
- `SKILL.md`（根目录）— 原 Python 版 skill 定义
```

Write this content to `CLAUDE.md`.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to framework-level context"
```

---

### Task 11: 验证完整性并清理

**Files:**
- Verify: 所有新目录和文件存在
- Verify: 迁移后的 CLI 可正常加载

- [ ] **Step 1: 验证目录结构**

```bash
cd c:/Users/Administrator/.agents/skills/powerbi-analysis
find da-corpus da-requirement da-data da-analysis da-report -type f | sort
```

Expected output:
```
da-analysis/SKILL.md
da-analysis/frameworks/README.md
da-corpus/SKILL.md
da-corpus/feishu-client.mjs
da-corpus/templates/business-overview.md
da-corpus/templates/data-assets.md
da-data/SKILL.md
da-data/from-powerbi/.gitignore
da-data/from-powerbi/package.json
da-data/from-powerbi/powerbi-client.mjs
da-data/from-powerbi/semantic-model-ids.json
da-data/from-powerbi/SKILL.md
da-data/from-powerbi/references/dax-aggregation.md
da-data/from-powerbi/references/dax-datetime.md
da-data/from-powerbi/references/dax-filter.md
da-data/from-powerbi/references/dax-logic.md
da-data/from-powerbi/references/dax-table.md
da-data/from-powerbi/references/dax-text.md
da-data/from-sql/SKILL.md
da-report/SKILL.md
da-report/image/SKILL.md
da-report/image/chart_generator.py
da-report/pdf/SKILL.md
da-report/ppt/SKILL.md
da-report/web/SKILL.md
da-report/web/frontend/...（多个前端文件）
da-report/web/uploader/web_report_builder.py
da-requirement/SKILL.md
da-requirement/templates/requirement.md
```

- [ ] **Step 2: 验证 PowerBI CLI 可用**

```bash
cd c:/Users/Administrator/.agents/skills/powerbi-analysis
node da-data/from-powerbi/powerbi-client.mjs 2>&1 || true
```

Expected: 输出用法说明或"未知命令"提示（说明 CLI 加载正常，不需要 Azure 凭证即可看到帮助）

- [ ] **Step 3: 验证所有 SKILL.md 存在且格式正确**

```bash
cd c:/Users/Administrator/.agents/skills/powerbi-analysis
for f in $(find da-corpus da-requirement da-data da-analysis da-report -name 'SKILL.md'); do
  echo "=== $f ==="
  head -3 "$f"
  echo ""
done
```

Expected: 每个 SKILL.md 都有 frontmatter（`---` 开头）和 `name:` 字段

- [ ] **Step 4: Commit 验证结果**

无需额外 commit，此步骤仅验证。
