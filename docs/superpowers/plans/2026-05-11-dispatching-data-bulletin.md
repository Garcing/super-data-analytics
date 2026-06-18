# Dispatching Data Bulletin Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an independent `dispatching-data-bulletin` skill that manages the full lifecycle of data bulletin templates (create, list, edit, delete) and executes bulletins by calling `fetching-data-via-powerbi` or `fetching-data-via-sql`.

**Architecture:** Single SKILL.md defines intent detection rules and three workflows (create, manage, execute). Templates are Markdown files with YAML frontmatter stored in `references/`. Execution dynamically calls the appropriate fetching skill based on the template's `data_source.type`.

**Tech Stack:** Markdown SKILL.md, YAML frontmatter templates, references to `fetching-data-via-powerbi` and `fetching-data-via-sql` skills.

---

## File Structure

```
dispatching-data-bulletin/
├── SKILL.md                                    # [CREATE] Skill definition
└── references/                                 # [CREATE] Template directory
    └── 平台治理经营健康数据播报.md                  # [MOVE + MODIFY] Add frontmatter

fetching-data-via-powerbi/SKILL.md              # [MODIFY] Remove "数据播报" section (lines 99-116)
```

---

### Task 1: Set up directory structure and move template

**Files:**
- Create: `dispatching-data-bulletin/references/`
- Move: `dispatching-data-bulletin/平台治理经营健康数据播报.md` → `dispatching-data-bulletin/references/平台治理经营健康数据播报.md`

- [ ] **Step 1: Create references directory and move template file**

```bash
mkdir -p "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-bulletin/references"
mv "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-bulletin/平台治理经营健康数据播报.md" \
   "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-bulletin/references/平台治理经营健康数据播报.md"
```

- [ ] **Step 2: Verify directory structure**

```bash
ls -la "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-bulletin/references/"
```

Expected: directory contains `平台治理经营健康数据播报.md`

---

### Task 2: Add frontmatter to existing template

**Files:**
- Modify: `dispatching-data-bulletin/references/平台治理经营健康数据播报.md`

- [ ] **Step 1: Prepend YAML frontmatter to the template**

Add this frontmatter block before the existing `# 平台治理经营健康数据播报` line. The content after frontmatter stays unchanged.

```yaml
---
name: 平台治理经营健康数据播报
data_source:
  type: powerbi
  target: 平台治理经营看板
time_granularity: weekly
output_format: wecom-markdown
created: 2026-05-08
---

```

The full file should look like:

```
---
name: 平台治理经营健康数据播报
data_source:
  type: powerbi
  target: 平台治理经营看板
time_granularity: weekly
output_format: wecom-markdown
created: 2026-05-08
---

# 平台治理经营健康数据播报

## 语义模型
平台治理经营看板
...（rest of existing content unchanged）
```

---

### Task 3: Write SKILL.md

**Files:**
- Create: `dispatching-data-bulletin/SKILL.md`

- [ ] **Step 1: Create SKILL.md with complete skill definition**

```markdown
---
name: dispatching-data-bulletin
description: 数据播报全生命周期管理：新建播报模板、管理已有模板（列表/编辑/删除）、执行数据播报。执行时根据模板标注的数据源类型，调用 fetching-data-via-powerbi 或 fetching-data-via-sql 获取数据，输出适配企业微信的 Markdown 文本。当用户提到"数据播报"、"周报"、"数据日报"、"经营播报"、"出一份XX报告"、"播报XX数据"、"新建播报"、"管理播报"、"编辑播报"、"删除播报"、"有哪些播报"时使用此 skill。即使用户没有明确说"播报"，只要意图是周期性地获取业务指标并格式化展示，也应该触发。
---

# 数据播报

管理数据播报模板的全生命周期，并执行播报生成企业微信 Markdown 报告。

## 意图识别

收到用户请求后，按以下规则判断意图：

| 用户信号 | 意图 |
|---|---|
| "新建播报"、"创建播报"、"做一个XX播报模板"、"建一个播报" | **新建** |
| "列表"、"有哪些播报"、"管理播报"、"编辑XX播报"、"删除XX播报"、"修改播报" | **管理** |
| 提到具体播报主题且未说新建/编辑/删除，如"播报平台治理"、"出经营周报"、"这周的XX数据" | **执行** |

如果用户提到的播报主题在 `references/` 中找不到，引导用户先创建模板。

## 模板规范

播报模板存放在 `references/` 目录下，每个 `.md` 文件是一个播报模板。

文件名即播报名称。文件格式为 YAML frontmatter + 自由 Markdown 正文：

```yaml
---
name: 播报名称
data_source:
  type: powerbi          # powerbi | sql
  target: 目标名称        # 语义模型名 或 SQL 表名
time_granularity: weekly  # daily | weekly | monthly | quarterly
output_format: wecom-markdown
created: 创建日期
---
```

frontmatter 之后的正文包含：
- 指标定义（维度 + 指标 + 计算方式）
- 健康阈值和风险判断规则
- 输出模板（表格结构、趋势标注方式）
- 重要限制

## 工作流：新建模板

1. 收集信息：播报名称、数据源类型（powerbi/sql）、目标（语义模型名/表名）、时间粒度、要播报的指标和维度、健康阈值、输出格式偏好
2. 如果用户有参考文档或样本数据，据此填充指标定义
3. 生成带 frontmatter 的 `.md` 文件保存到 `references/`，文件名用播报名称
4. 向用户展示生成的模板，确认或修改

## 工作流：管理模板

**列表**：遍历 `references/` 下的 `.md` 文件，解析 frontmatter，展示：
- 名称（`name` 字段或文件名）
- 数据源类型和目标
- 时间粒度
- 创建日期

**编辑**：读取模板 → 用户说明修改内容 → 更新文件。可以修改指标定义、健康阈值、输出模板、数据源配置等。

**删除**：确认后删除对应 `.md` 文件。

## 工作流：执行播报

1. **匹配模板**：按名称或主题关键词在 `references/` 中查找匹配的 `.md` 文件
2. **解析 frontmatter**：读取 `data_source.type` 和 `data_source.target`
3. **确认时间范围**：用户指定，或基于 `time_granularity` 推断（如 weekly → 本周/上周）
4. **调用数据获取 skill**：
   - `data_source.type == powerbi` → 使用 `fetching-data-via-powerbi` skill 的流程：读取语义模型 ID → 获取 Schema → 编写 DAX → 执行查询
   - `data_source.type == sql` → 使用 `fetching-data-via-sql` skill 的流程：获取表结构 → 编写 SQL → 执行查询
5. **填充输出模板**：用查询结果填充模板中定义的表格，计算衍生指标（周环比、趋势箭头 ↑↓→、健康阈值判断）
6. **生成报告**：按模板中的输出格式生成企业微信 Markdown 文本

### 周环比计算

```
周环比 = (本周值 - 上周值) / 上周值 * 100%
趋势：上升 → ↑，下降 → ↓，持平 → →
```

### 健康阈值判断

根据模板中定义的阈值规则判断，标注 ✅正常 或 ⚠需关注。

## 关键限制

- 所有数据必须通过对应的 fetching skill 从真实数据源获取，严禁捏造数据
- 如果某个指标无数据，标注"暂无数据"并注明原因
- 核心指标解读必须基于真实查询数据得出
- 时间范围由用户在执行时指定，模板只提供默认粒度参考
```

---

### Task 4: Clean up fetching-data-via-powerbi

**Files:**
- Modify: `fetching-data-via-powerbi/SKILL.md` (remove lines 99-116, the "数据播报" section)

- [ ] **Step 1: Remove the "数据播报" section**

Delete lines 99-116 from `fetching-data-via-powerbi/SKILL.md`. The section starts with `## 数据播报` and ends with the line `**关键限制：** 所有数据必须通过 DAX 查询从 Power BI 获取，严禁捏造数据。如果某个指标无数据，标注"暂无数据"。`

After removal, line 98 (`--keep-request` code block ending) should be followed directly by line 118 (`## 输入`).

- [ ] **Step 2: Verify the file is well-formed**

Read the modified file around the deletion point to confirm the transition from Phase 4's code block directly to `## 输入` is clean, with exactly one blank line between them.

---

### Task 5: Final verification

- [ ] **Step 1: Verify complete directory structure**

```bash
find "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-bulletin" -type f
```

Expected:
```
dispatching-data-bulletin/SKILL.md
dispatching-data-bulletin/references/平台治理经营健康数据播报.md
```

- [ ] **Step 2: Verify SKILL.md has valid frontmatter**

Check that `dispatching-data-bulletin/SKILL.md` starts with `---`, contains `name:` and `description:` fields, and closes with `---`.

- [ ] **Step 3: Verify template has frontmatter**

Check that `references/平台治理经营健康数据播报.md` starts with `---`, contains the `data_source` block, and closes with `---`.

- [ ] **Step 4: Verify fetching-data-via-powerbi no longer contains "数据播报" section**

```bash
grep -n "数据播报" "c:/Users/Administrator/.agents/skills/super-data-analyst/fetching-data-via-powerbi/SKILL.md"
```

Expected: no output (the section has been removed)
