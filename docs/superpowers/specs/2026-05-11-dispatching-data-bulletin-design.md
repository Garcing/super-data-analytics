# 数据播报 Skill 设计

## 概述

创建独立的 `dispatching-data-bulletin` skill，负责数据播报的全生命周期管理：新建模板、管理模板（列表/编辑/删除）、执行播报。执行时根据模板中标注的数据源类型，动态调用 `fetching-data-via-powerbi` 或 `fetching-data-via-sql` 获取数据，最终输出适配企业微信的 Markdown 文本。

## 目录结构

```
dispatching-data-bulletin/
├── SKILL.md                    # Skill 定义（意图识别 + 三条工作流）
└── references/                 # 播报模板存放处
    └── 平台治理经营健康数据播报.md  # 现有案例（添加 frontmatter）
```

模板以 `.md` 文件存放在 `references/` 下，文件名即播报名称。

## 模板规范

模板采用 frontmatter + 自由 Markdown 的混合格式。

### Frontmatter 字段

```yaml
---
name: 平台治理经营健康数据播报
data_source:
  type: powerbi          # powerbi | sql
  target: 平台治理经营看板  # 语义模型名 或 SQL 表名
time_granularity: weekly  # daily | weekly | monthly | quarterly
output_format: wecom-markdown
created: 2026-05-08
---
```

| 字段 | 说明 |
|---|---|
| `name` | 播报名称，用于意图匹配和列表展示 |
| `data_source.type` | 数据源类型，决定执行时调用哪个 fetching skill |
| `data_source.target` | 具体目标：PowerBI 语义模型名（对应 `semantic-model-ids.json`）或 SQL 表名 |
| `time_granularity` | 默认时间粒度，执行时用户可覆盖 |
| `output_format` | 输出格式，当前仅 `wecom-markdown` |
| `created` | 创建日期 |

### 正文结构

Frontmatter 之后的正文保持自由 Markdown，包含：
- 指标定义（维度 + 指标 + 计算方式）
- 健康阈值和风险判断规则
- 输出模板（表格结构、趋势标注方式）
- 重要限制和注意事项

## 意图识别

SKILL.md 中用决策树描述意图识别规则：

| 用户信号 | 判定意图 |
|---|---|
| "新建播报"、"创建播报"、"做一个XX播报模板" | 新建 |
| "列表"、"有哪些播报"、"管理播报"、"编辑XX播报"、"删除XX播报" | 管理 |
| 提到具体播报主题 + 没说"新建/编辑/删除"，如"播报平台治理"、"出经营周报" | 执行 |

当用户提到一个不存在的播报主题并期望执行时，引导用户先创建模板。

## 三条工作流

### 1. 新建模板

1. 收集信息：播报名称、数据源类型（powerbi/sql）、目标（语义模型名/表名）、时间粒度、指标和维度、健康阈值、输出格式偏好
2. 如果用户有参考文档或样本数据，据此填充指标定义
3. 生成带 frontmatter 的 `.md` 文件保存到 `references/`
4. 向用户展示生成的模板，确认或修改

### 2. 管理模板

- **列表**：遍历 `references/` 下的 `.md` 文件，解析 frontmatter，展示名称 + 数据源 + 时间粒度
- **编辑**：读取模板 → 用户说明修改内容 → 更新文件
- **删除**：确认后删除对应 `.md` 文件

### 3. 执行播报

1. 匹配模板：按名称或主题关键词在 `references/` 中查找
2. 解析 frontmatter：确定数据源类型和目标
3. 确认时间范围：用户指定或默认基于 `time_granularity`
4. 调用对应的 fetching skill 获取数据：
   - `data_source.type == powerbi` → 调用 `fetching-data-via-powerbi`
   - `data_source.type == sql` → 调用 `fetching-data-via-sql`
5. 读取模板中的输出格式部分，用查询结果填充
6. 计算衍生指标（周环比、趋势箭头、健康阈值判断）
7. 输出企业微信 Markdown 文本

## 关键约束

- 所有数据必须通过对应的 fetching skill 从真实数据源获取，严禁捏造数据
- 如果某个指标无数据，标注"暂无数据"
- 模板文件名不能包含特殊字符，建议使用中文或英文描述性名称
- 时间范围由用户在执行时指定，模板只提供默认粒度参考

## 清理工作

删除 `fetching-data-via-powerbi/SKILL.md` 中的"数据播报"小节（约第 99-116 行），该功能已迁移到本独立 skill。
