# 数据分析 Skill 框架

综合数据分析能力，包含五个板块：语料、需求、数据获取、分析、报告。

## 架构

```
retrieving-context/              检索业务知识图谱（指标定义、数据资产、业务上下文）
orchestrating-analytics/         编排数据分析（入口路由、实体消歧、SQL Spec、流程验收）
querying-data/                   统一数据查询（SQL 默认；Power BI 显式兼容）
diagnosing-anomalies/            指标异动归因方法论
predicting-trends/               业务趋势预测和目标制定方法论（name: predicting_trends）
evaluating-impact/               效果评估与实验检验方法论
visualizing-data/                生成确定性单图图表（Seaborn/Matplotlib，PNG/SVG）
using-templates/                 报告模板生命周期管理（飞书个人文件夹，CLI）
building-reports/                生成报告（按格式 html / image / streamlit / lark 路由）
  scripts/html/                   HTML 报告（已实现，前端 + Blob + 发布）
  scripts/image/                  图片报告（apimart gpt-image-2，CLI + 编程式）
  scripts/streamlit/              Streamlit 报告（本地预览 + Community Cloud 部署）
validating-analyses/             分析成品质检（横向）：交付前独立审查分析是否准确、有据、可分享
```

## 运行环境与依赖

- Node.js `>=20.0.0`；有 lock 的目录统一用 `npm ci`：`querying-data/scripts/`、`retrieving-context/scripts/`、`building-reports/scripts/`、`building-reports/scripts/html/`。
- Python `>=3.10`；依赖文件分别位于 `retrieving-context/scripts/pipeline/requirements.txt`、`visualizing-data/requirements.txt`、`building-reports/scripts/streamlit/requirements.txt`。归因/预测/效果评估为标准库实现，各自保留注释型空 `requirements.txt`。
- `using-templates/scripts/package.json` 只声明 ESM/Node 版本，无第三方包和 lock；`building-reports/scripts/image/` 复用父级依赖，不单独维护 package/lock。
- 业务凭证统一来自 `~/.super-data-analytics/config.json`；详细安装矩阵与全部配置项见 `DEPENDENCIES.MD`。

## 数据流

板块 0（语料）← 所有板块可引用
板块 1（编排）→ 板块 2（数据）→ 板块 3（分析）→ 板块 4（报告）

## 触发路由

收到数据分析请求时，根据意图明确程度选择路径。LLM 本身就是路由器——读下面的规则，自己判断走哪条路。

### 直连路径（跳过 orchestration）

满足**任意一条**即可直连具体 skill，不需要先走 orchestrating-analytics：

- 用户给了明确的 SQL / DAX 语句
- 用户说"跑一下"/"查一下"/"拉一下" + 具体指标名
- 请求只涉及单一数据源、单一指标、明确的时间范围
- 用户明确说"不需要对齐需求"或"直接查"

跳过编排不等于跳过语义层：具体业务指标仍先用 `retrieving-context` 解析受治理口径，再默认用 `querying-data sql` 执行。只有用户明确提供 DAX、要求 Power BI 或指定 Power BI 模型时才走 `powerbi`。

### 编排路径（先走 orchestration）

满足**任意一条**则先走 orchestrating-analytics 编排：

- 请求包含"分析"、"为什么"、"看看情况"、"帮忙看看"等模糊词
- 涉及多个指标、实体、维度、关系或数据源，需要拆解归因
- 用户的意图需要多轮提问才能明确

### 完整路径（全流程）

满足**任意一条**则走 orchestrate → query → analyze → report → dispatch：

- 用户说"帮我出一份 XX 报告"/"做一次 XX 分析"
- 明确涉及 从分析到交付 的完整链路

### 横向服务（随时可引用）

以下 skill 不属于上述路径，但任何 skill 在执行中都可以随时调用：

- `retrieving-context`：需要知道指标定义、表名、业务层级时
- `orchestrating-analytics`：执行中发现实体、口径或流程不明确时，可以中途补走编排
- `diagnosing-anomalies`：业务指标上涨、下跌、异常波动或告警后，需要严谨归因方法论时使用
- `predicting_trends`：业务预测、趋势外推、目标制定、目标达成判断、资源预算预估等需要未来预测结果时使用
- `evaluating-impact`：产品上线、运营活动、Push、发券、投放、A/B 实验、DID 试点等需要判断“动作是否有效、ROI 是否为正、是否可以全量/加码/停止”时使用。
- `visualizing-data`：需要把结构化数据生成确定性单图 PNG/SVG 时使用；适合报告插图、文档图表、PPT/PDF 图表素材，尤其是数值必须准确时。
- `validating-analyses`：分析或报告交付给决策方之前，需要独立复核其是否准确、有据、可分享（复算关键数字、查分析陷阱、图表诚实性、置信度评级）时使用。

互联网数据分析三大能力：
- `diagnosing-anomalies`：异动归因，回答“为什么变了”。
- `predicting_trends`：趋势预测和目标制定，回答“未来会怎样 / 目标怎么定”。
- `evaluating-impact`：效果评估和实验检验，回答“做的事情有没有用 / 是否值得继续”。

## Azure AD 配置

- 应用：`client_id: d44d3dbe-2b19-4ed0-ad47-ccd50627e9a5`
- 租户：`7d20639b-c6a8-4cdc-9cfe-6ea75b3af0c9`
- 运行时从 `config.json` 的 `POWERBI_CLIENT_ID` / `POWERBI_CLIENT_SECRET` / `POWERBI_TENANT_ID` 读取，不在仓库保存 secret
- 需要 Application 类型权限 + Admin Consent

## Vercel 部署

- 项目：`super-data-analytics`，域名：`www.super-data-analytics.online`
- Blob Store：Public 访问模式
- 重新部署：`cd building-reports/scripts/html && rm -rf dist && vercel deploy --prod --force --token $VERCEL_TOKEN`（`VERCEL_TOKEN` 由调用者或 Vercel CLI 登录态提供；项目脚本不从 `config.json` 加载）
- 必须先 `rm -rf dist` 清除构建缓存

## 前端技术栈

React 18 + Vite 6 + Tailwind CSS 3 + Recharts 2 + React Router 7

字体：Source Sans 3（正文/UI）、Cormorant Garamond（标题/数字）、IBM Plex Mono（标签/代码）

全局背景色 `--bg-primary: #faf7f2`，Warm Parchment 主题

## CLI 三态输入约定

需要接收长文本、SQL/DAX、JSON、报告源码、提示词等正文输入的 CLI，应统一采用三态输入口径，减少 agent 使用歧义：

- inline：`--flag "<内容>"`，直接把参数值作为正文输入
- 文件：`--flag @<file>`，读取 UTF-8 文件内容，适合多行、含引号或特殊符号的输入
- stdin：`--flag -` 或不传该正文 flag 时从管道读取；若 stdin 是交互终端，应立即报错提示用户改用 inline / @文件 / 管道

实现细节需保持一致：文件、stdin、inline 都应 `trim()` 后判空；`@` 后缺路径、文件不存在、文件为空、stdin 为空、stdin 超时都要给出明确错误。非交互 stdin 读取需设置约 15s 超时，避免 agent 子进程忘记关闭 stdin 时永久挂起。

当前已按此口径实现/对齐的入口：

- `querying-data/scripts/query.js sql query --sql ...`
- `querying-data/scripts/query.js powerbi query --payload ...`
- `building-reports/scripts/report.js html publish --report ...`
- `building-reports/scripts/report.js streamlit publish --report ...`
- `building-reports/scripts/report.js image <generate|submit> --prompt ...`
- `visualizing-data/scripts/chart.py --data ...`
- `retrieving-context/scripts/retrieve.js search --question ...` 与 `retrieving-context/scripts/retrieve.js cypher --statement ...`：正文 flag 支持 inline / @文件 / `-` stdin；不传正文 flag 时走 stdin。

## 关键注意事项

- **Vercel 构建缓存**：修改前端代码后必须 `rm -rf dist` 再部署
- **DAX 编写**：没有 artifactId 时先跑 `node scripts/query.js powerbi list-semantic-models` 查看本地语义模型候选；写 DAX 前必须通过 `GetSemanticModelSchema` 确认字段名，参考 `querying-data/references/powerbi.md`
- **@vercel/blob**：`put()` 必须指定 `access: 'public'`，读取用 `head()` + `fetch(url)`
- **HTML 报告**：用 `scripts/report.js html` 发布/列出/读取/删除报告（`publishReport` / `listReports` / `getReport` / `deleteReport` + 子命令 CLI）；接口与输入格式见 `building-reports/references/report_to_html.md`
- **图片报告**：用 `scripts/report.js image generate` 生成图片（apimart gpt-image-2，异步提交→轮询→下载）；`node scripts/report.js image generate --prompt "<提示词>" --output <路径> [--model|--size|--quality ...]`，`--dry-run` 零成本自检；接口与用法见 `building-reports/references/report_to_image.md`
- **Streamlit 报告**：用 `scripts/streamlit/`（本地预览 `streamlit run scripts/streamlit/app.py`，在 `building-reports/` 下执行）；一份报告 = `scripts/streamlit/reports/*.py`，遵循 `references/report_to_streamlit.md`；线上 `https://super-data-analytics.streamlit.app/`，每份报告直达链接 = 线上地址/`<报告title>`；发布新报告 commit 后在 `building-reports/` 下跑 `bash scripts/streamlit/deploy.sh`（subtree push 到 `Garcing/streamlit-reports`，Cloud 自动重新部署）

## 旧代码保留

旧框架代码（`node_version/`、根 `scripts/`、`web-report/`、根 `references/`、根 `SKILL.md`）已在 1.0 重置时全部清理，当前目录树即最终结构。
