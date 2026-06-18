# Dispatching Data Briefs — Feishu Storage Upgrade Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `dispatching-data-briefs` to store templates in a Feishu folder instead of local files, via a Node.js CLI tool.

**Architecture:** Single `feishu-briefs.js` CLI tool (ESM, `.js` extension via `type: module`) wraps Feishu OpenAPI for CRUD. SKILL.md updated to call this CLI instead of reading local files.

**Tech Stack:** Node.js 18+ (native fetch), ESM, no extra dependencies.

---

## File Structure

```
dispatching-data-briefs/
├── SKILL.md                      # [MODIFY] Update to use CLI tool
├── feishu-briefs.js              # [CREATE] CLI tool
├── package.json                  # [CREATE] ESM config
├── .env                          # [CREATE] Feishu credentials
└── references/                   # [KEEP] Local copies for migration reference
    ├── 平台治理经营健康数据播报.md
    └── 质检数据播报.md
```

---

### Task 1: Project setup + CLI skeleton + auth + HTTP helpers

**Files:**
- Create: `dispatching-data-briefs/package.json`
- Create: `dispatching-data-briefs/.env`
- Create: `dispatching-data-briefs/feishu-briefs.js`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "feishu-briefs",
  "private": true,
  "type": "module"
}
```

- [ ] **Step 2: Create .env**

```
FEISHU_APP_ID=cli_a61c7f2cca7e900d
FEISHU_APP_SECRET=PwXcbOHIwdbcUO24JgBhocDRaINYYvhK
FEISHU_FOLDER_TOKEN=XvG6feei4lr5XFdaGzEcsxGrnkg
FEISHU_DELETE_PASSWORD=
```

- [ ] **Step 3: Create feishu-briefs.js with skeleton, .env loading, auth, and HTTP helpers**

```javascript
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// 从脚本所在目录向上查找 .env 文件并加载
const __dirname = dirname(fileURLToPath(import.meta.url));
for (let dir = __dirname; dir !== dirname(dir); dir = dirname(dir)) {
  try {
    const envPath = join(dir, '.env');
    const content = readFileSync(envPath, 'utf-8');
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eq = trimmed.indexOf('=');
      if (eq === -1) continue;
      const key = trimmed.slice(0, eq).trim();
      const val = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '');
      if (!process.env[key]) process.env[key] = val;
    }
    break;
  } catch {}
}

const FEISHU_BASE = 'https://open.feishu.cn/open-apis';

// --- Auth ---

async function getTenantToken() {
  const appId = process.env.FEISHU_APP_ID;
  const appSecret = process.env.FEISHU_APP_SECRET;
  if (!appId || !appSecret) {
    throw new Error('缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET 环境变量');
  }
  const resp = await fetch(`${FEISHU_BASE}/auth/v3/tenant_access_token/internal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ app_id: appId, app_secret: appSecret }),
  });
  const data = await resp.json();
  if (data.code !== 0) {
    throw new Error(`获取 token 失败: ${data.code} ${data.msg}`);
  }
  return data.tenant_access_token;
}

// --- HTTP helpers ---

function checkResponse(data) {
  if (data.code !== 0) {
    throw new Error(`飞书 API 错误: ${data.code} ${data.msg}`);
  }
  return data.data;
}

async function feishuGet(token, path) {
  const resp = await fetch(`${FEISHU_BASE}${path}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  return checkResponse(await resp.json());
}

async function feishuPost(token, path, body) {
  const resp = await fetch(`${FEISHU_BASE}${path}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json; charset=utf-8',
    },
    body: JSON.stringify(body),
  });
  return checkResponse(await resp.json());
}

async function feishuPatch(token, path, body) {
  const resp = await fetch(`${FEISHU_BASE}${path}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json; charset=utf-8',
    },
    body: JSON.stringify(body),
  });
  return checkResponse(await resp.json());
}

async function feishuDelete(token, path) {
  const resp = await fetch(`${FEISHU_BASE}${path}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` },
  });
  return checkResponse(await resp.json());
}

// --- CLI entry point ---

const [,, command, ...cliArgs] = process.argv;

if (!command) {
  console.error('用法: node feishu-briefs.js <命令> [参数]');
  console.error('');
  console.error('命令:');
  console.error('  list                              列出飞书文件夹中的播报模板');
  console.error('  read <doc_id>                     读取播报模板内容');
  console.error('  create --title "XX" --file <path>  创建播报模板');
  console.error('  update <doc_id> --file <path>      更新播报模板');
  console.error('  delete <doc_id> --password <pwd>   删除播报模板');
  process.exit(1);
}

(async () => {
  try {
    const token = await getTenantToken();

    switch (command) {
      case 'list':
        console.log('TODO: list');
        break;
      case 'read':
        console.log('TODO: read');
        break;
      case 'create':
        console.log('TODO: create');
        break;
      case 'update':
        console.log('TODO: update');
        break;
      case 'delete':
        console.log('TODO: delete');
        break;
      default:
        console.error(`未知命令: ${command}`);
        process.exit(1);
    }
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }
})();
```

- [ ] **Step 4: Verify auth works**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-briefs"
node feishu-briefs.js list
```

Expected: prints `TODO: list` (auth succeeded without error). If auth fails, check `.env` credentials.

---

### Task 2: List command

**Files:**
- Modify: `dispatching-data-briefs/feishu-briefs.js`

- [ ] **Step 1: Add listFiles function and wire up the list command**

Replace the `list` case in the switch block with:

```javascript
      case 'list': {
        const folderToken = process.env.FEISHU_FOLDER_TOKEN;
        const data = await feishuGet(token, `/drive/v1/files?folder_token=${folderToken}&page_size=200`);
        const files = data.files || [];
        const result = files
          .filter(f => f.type === 'docx' || f.type === 'doc')
          .map(f => ({
            id: f.token,
            name: f.name,
            type: f.type,
            url: f.url,
            modified_time: f.modified_time,
          }));
        console.log(JSON.stringify(result, null, 2));
        break;
      }
```

- [ ] **Step 2: Verify list command**

```bash
node feishu-briefs.js list
```

Expected: JSON array of documents in the Feishu folder (may be empty if no docs yet).

---

### Task 3: Read command

**Files:**
- Modify: `dispatching-data-briefs/feishu-briefs.js`

- [ ] **Step 1: Add read command**

Replace the `read` case in the switch block with:

```javascript
      case 'read': {
        const docId = cliArgs[0];
        if (!docId) {
          console.error('用法: node feishu-briefs.js read <doc_id>');
          process.exit(1);
        }
        const data = await feishuGet(token, `/docx/v1/documents/${docId}/raw_content`);
        console.log(data.content || '');
        break;
      }
```

- [ ] **Step 2: Verify read command**

First use `list` to get a doc_id, then:

```bash
node feishu-briefs.js read <doc_id>
```

Expected: plain text content of the document. If folder is empty, skip this verification and test after migration.

---

### Task 4: Markdown-to-blocks converter + Create command

**Files:**
- Modify: `dispatching-data-briefs/feishu-briefs.js`

- [ ] **Step 1: Add the markdown-to-blocks converter**

Insert this function before the CLI entry point section (before `const [,, command, ...cliArgs]`):

```javascript
// --- Markdown to Feishu blocks converter ---

function textElement(content) {
  return { text_run: { content } };
}

function textBlock(content) {
  return {
    block_type: 2,
    text: { elements: [textElement(content)], style: {} },
  };
}

function headingBlock(level, content) {
  const types = { 1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 8, 7: 9, 8: 10, 9: 11 };
  const names = { 1: 'heading1', 2: 'heading2', 3: 'heading3', 4: 'heading4', 5: 'heading5', 6: 'heading6', 7: 'heading7', 8: 'heading8', 9: 'heading9' };
  const blockType = types[level] || 3;
  const blockName = names[level] || 'heading1';
  return {
    block_type: blockType,
    [blockName]: { elements: [textElement(content)], style: {} },
  };
}

function bulletBlock(content) {
  return {
    block_type: 12,
    bullet: { elements: [textElement(content)], style: {} },
  };
}

function codeBlock(content) {
  return {
    block_type: 14,
    code: { elements: [textElement(content)], style: {} },
  };
}

function dividerBlock() {
  return { block_type: 22, divider: {} };
}

function mdToBlocks(markdown) {
  const lines = markdown.split('\n');
  const blocks = [];
  let inCode = false;
  let codeLines = [];

  for (const rawLine of lines) {
    const line = rawLine;

    // Code block boundaries
    if (line.trim().startsWith('```')) {
      if (inCode) {
        blocks.push(codeBlock(codeLines.join('\n')));
        codeLines = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    // Empty line → skip
    if (line.trim() === '') continue;

    // Horizontal rule
    if (/^---+\s*$/.test(line.trim())) {
      blocks.push(dividerBlock());
      continue;
    }

    // Headings
    const headingMatch = line.match(/^(#{1,9})\s+(.*)/);
    if (headingMatch) {
      blocks.push(headingBlock(headingMatch[1].length, headingMatch[2].trim()));
      continue;
    }

    // Bullet list
    if (/^[-*]\s+/.test(line.trim())) {
      blocks.push(bulletBlock(line.trim().replace(/^[-*]\s+/, '')));
      continue;
    }

    // Everything else → text block
    blocks.push(textBlock(line));
  }

  // Unclosed code block
  if (inCode && codeLines.length > 0) {
    blocks.push(codeBlock(codeLines.join('\n')));
  }

  return blocks;
}
```

- [ ] **Step 2: Add create command**

Replace the `create` case in the switch block with:

```javascript
      case 'create': {
        let title, filePath;
        for (let i = 0; i < cliArgs.length; i++) {
          if (cliArgs[i] === '--title') title = cliArgs[++i];
          else if (cliArgs[i] === '--file') filePath = cliArgs[++i];
        }
        if (!title) {
          console.error('用法: node feishu-briefs.js create --title "标题" --file <file_path>');
          process.exit(1);
        }

        // 1. Create empty document
        const folderToken = process.env.FEISHU_FOLDER_TOKEN;
        const docData = await feishuPost(token, '/docx/v1/documents', {
          title,
          folder_token: folderToken,
        });
        const docId = docData.document.document_id;
        console.error(`文档已创建: ${docId}`);

        // 2. If file provided, write content as blocks
        if (filePath) {
          const content = readFileSync(filePath, 'utf-8');
          const blocks = mdToBlocks(content);
          if (blocks.length > 0) {
            // Get root block (page block)
            const blocksData = await feishuGet(token, `/docx/v1/documents/${docId}/blocks?page_size=1`);
            const pageBlockId = docId; // root block id = document id

            // Batch create: max 50 blocks per request
            for (let i = 0; i < blocks.length; i += 50) {
              const batch = blocks.slice(i, i + 50);
              await feishuPost(
                token,
                `/docx/v1/documents/${docId}/blocks/${pageBlockId}/children`,
                { children: batch }
              );
            }
            console.error(`已写入 ${blocks.length} 个内容块`);
          }
        }

        // 3. Output result
        console.log(JSON.stringify({ document_id: docId, title }, null, 2));
        break;
      }
```

- [ ] **Step 3: Verify create command**

Create a small test file first:

```bash
echo "# 测试播报

## 数据源
- 类型：powerbi
- 模型：测试看板

## 指标
- 用户数
- 退费率

---
结束" > "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-briefs/test-template.md"
```

Then run:

```bash
node feishu-briefs.js create --title "测试播报模板" --file test-template.md
```

Expected: JSON output with `document_id`. Verify in Feishu that the document appears in the folder with formatted content.

Clean up test file:

```bash
rm test-template.md
```

---

### Task 5: Delete command

**Files:**
- Modify: `dispatching-data-briefs/feishu-briefs.js`

- [ ] **Step 1: Add delete command**

Replace the `delete` case in the switch block with:

```javascript
      case 'delete': {
        const docId = cliArgs[0];
        let password;
        for (let i = 0; i < cliArgs.length; i++) {
          if (cliArgs[i] === '--password') password = cliArgs[++i];
        }
        if (!docId) {
          console.error('用法: node feishu-briefs.js delete <doc_id> --password <密码>');
          process.exit(1);
        }

        const configPassword = process.env.FEISHU_DELETE_PASSWORD;
        if (configPassword && configPassword !== password) {
          console.error('密码错误，删除操作已取消');
          process.exit(1);
        }

        await feishuDelete(token, `/drive/v1/files/${docId}?type=docx`);
        console.log(JSON.stringify({ deleted: true, document_id: docId }));
        break;
      }
```

- [ ] **Step 2: Verify delete command**

Use the doc_id from Task 4's test:

```bash
node feishu-briefs.js delete <test_doc_id> --password ""
```

Expected: `{"deleted": true, "document_id": "..."}`. If `FEISHU_DELETE_PASSWORD` is empty in `.env`, any password is accepted (empty string matches empty config).

---

### Task 6: Update command

**Files:**
- Modify: `dispatching-data-briefs/feishu-briefs.js`

Update uses a delete-and-recreate strategy: read old title → delete old doc → create new doc with same title and new content. This avoids complex block-level manipulation.

- [ ] **Step 1: Add update command**

Replace the `update` case in the switch block with:

```javascript
      case 'update': {
        const docId = cliArgs[0];
        let filePath;
        for (let i = 0; i < cliArgs.length; i++) {
          if (cliArgs[i] === '--file') filePath = cliArgs[++i];
        }
        if (!docId || !filePath) {
          console.error('用法: node feishu-briefs.js update <doc_id> --file <file_path>');
          process.exit(1);
        }

        // Read old document title
        const docInfo = await feishuGet(token, `/docx/v1/documents/${docId}`);
        const oldTitle = docInfo.document?.title || '未命名';

        // Delete old document
        await feishuDelete(token, `/drive/v1/files/${docId}?type=docx`);

        // Create new document with same title
        const folderToken = process.env.FEISHU_FOLDER_TOKEN;
        const newDoc = await feishuPost(token, '/docx/v1/documents', {
          title: oldTitle,
          folder_token: folderToken,
        });
        const newDocId = newDoc.document.document_id;

        // Write new content
        const content = readFileSync(filePath, 'utf-8');
        const blocks = mdToBlocks(content);
        if (blocks.length > 0) {
          for (let i = 0; i < blocks.length; i += 50) {
            const batch = blocks.slice(i, i + 50);
            await feishuPost(
              token,
              `/docx/v1/documents/${newDocId}/blocks/${newDocId}/children`,
              { children: batch }
            );
          }
        }

        console.log(JSON.stringify({
          updated: true,
          old_document_id: docId,
          new_document_id: newDocId,
          title: oldTitle,
        }));
        break;
      }
```

- [ ] **Step 2: Verify update command**

Create a test document, then update it:

```bash
echo "# 测试播报 v2" > "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-briefs/test-v2.md"

# First create
node feishu-briefs.js create --title "测试更新" --file test-v2.md
# Note the document_id from output

# Then update
node feishu-briefs.js update <doc_id> --file test-v2.md
# Should output new_document_id

rm test-v2.md
```

Expected: `updated: true` with a new `document_id`.

---

### Task 7: SKILL.md update

**Files:**
- Modify: `dispatching-data-briefs/SKILL.md`

- [ ] **Step 1: Rewrite SKILL.md to use the CLI tool**

Replace the entire `SKILL.md` content with:

```markdown
---
name: dispatching-data-briefs
description: 数据播报全生命周期管理：新建播报模板、管理已有模板（列表/编辑/删除）、执行数据播报。模板存储在飞书个人文件夹中，通过 feishu-briefs.js CLI 工具进行增删改查。执行时根据模板标注的数据源类型，调用 querying-data-via-powerbi 或 querying-data-via-sql 获取数据，输出适配企业微信的 Markdown 文本。当用户提到"数据播报"、"周报"、"数据日报"、"经营播报"、"出一份XX报告"、"播报XX数据"、"新建播报"、"管理播报"、"编辑播报"、"删除播报"、"有哪些播报"时使用此 skill。
---

# 数据播报

管理数据播报模板的全生命周期，并执行播报生成企业微信 Markdown 报告。模板存储在飞书个人文件夹中。

## 意图识别

收到用户请求后，按以下规则判断意图：

| 用户信号 | 意图 |
|---|---|
| "新建播报"、"创建播报"、"做一个XX播报模板"、"建一个播报" | **新建** |
| "列表"、"有哪些播报"、"管理播报"、"编辑XX播报"、"删除XX播报"、"修改播报" | **管理** |
| 提到具体播报主题且未说新建/编辑/删除，如"播报平台治理"、"出经营周报"、"这周的XX数据" | **执行** |

如果用户提到的播报主题在飞书文件夹中找不到匹配的模板，引导用户先创建。

## CLI 工具

所有模板操作通过 `feishu-briefs.js`（位于本 skill 目录下）：

```bash
# 列出所有播报模板
node feishu-briefs.js list

# 读取模板内容（返回纯文本，包含 frontmatter）
node feishu-briefs.js read <doc_id>

# 创建新模板
node feishu-briefs.js create --title "播报名称" --file <content_file>

# 更新模板（覆盖重建）
node feishu-briefs.js update <doc_id> --file <content_file>

# 删除模板（需要密码）
node feishu-briefs.js delete <doc_id> --password <密码>
```

## 模板规范

模板存储为飞书文档，文档标题即播报名称。文档内容开头为 YAML frontmatter（纯文本形式），后续为模板正文：

```
---
name: 播报名称
data_source:
  type: powerbi          # powerbi | sql
  target: 目标名称        # 语义模型名 或 SQL 表名
time_granularity: weekly  # daily | weekly | monthly | quarterly
output_format: wecom-markdown
created: 创建日期
---

（指标定义、健康阈值、输出模板等正文内容）
```

frontmatter 字段说明：
- `data_source.type`：决定执行时调用哪个 fetching skill（powerbi → `querying-data-via-powerbi`，sql → `querying-data-via-sql`）
- `data_source.target`：PowerBI 语义模型名（对应 `semantic-model-ids.json`）或 SQL 表名
- `time_granularity`：默认时间粒度，执行时用户可以覆盖

## 工作流：新建模板

1. 收集信息：播报名称、数据源类型（powerbi/sql）、目标（语义模型名/表名）、时间粒度、要播报的指标和维度、健康阈值、输出格式偏好
2. 如果用户有参考文档或样本数据，据此填充指标定义
3. 生成模板内容（frontmatter + 正文），写入本地临时文件
4. 调用 `node feishu-briefs.js create --title "播报名称" --file <临时文件>` 创建飞书文档
5. 向用户展示创建结果（文档 ID 和飞书链接）
6. 清理临时文件

## 工作流：管理模板

**列表**：
```bash
node feishu-briefs.js list
```
返回 JSON 数组，每个元素包含 `id`、`name`、`type`、`url`、`modified_time`。向用户展示名称、数据源类型、最后修改时间。

**编辑**：
1. `node feishu-briefs.js read <doc_id>` 读取当前内容
2. 用户说明修改内容
3. 生成修改后的完整内容，写入临时文件
4. `node feishu-briefs.js update <doc_id> --file <临时文件>` 更新
5. 清理临时文件

**删除**：
1. 确认用户要删除的模板
2. 向用户索取删除密码
3. `node feishu-briefs.js delete <doc_id> --password <密码>`
4. 确认删除成功

## 工作流：执行播报

1. **匹配模板**：`node feishu-briefs.js list` 列出模板，按名称匹配用户提到的播报主题
2. **读取模板**：`node feishu-briefs.js read <doc_id>` 获取完整内容，解析 frontmatter
3. **确认时间范围**：用户指定，或基于 `time_granularity` 推断（如 weekly → 本周/上周）
4. **调用数据获取 skill**：
   - `data_source.type == powerbi` → 使用 `querying-data-via-powerbi` skill 的流程：读取语义模型 ID → 获取 Schema → 根据模板中的指标定义编写 DAX → 执行查询
   - `data_source.type == sql` → 使用 `querying-data-via-sql` skill 的流程：获取表结构 → 根据模板中的指标定义编写 SQL → 执行查询
5. **填充输出模板**：用查询结果填充模板中定义的表格，计算衍生指标（周环比、趋势箭头 ↑↓→、健康阈值判断）
6. **生成报告**：按模板中的输出格式生成企业微信 Markdown 文本

### 周环比计算

```
周环比 = (本周值 - 上周值) / 上周值 * 100%，保留2位小数
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

### Task 8: Migrate existing templates to Feishu

**Files:**
- No file changes — migration is a runtime operation

- [ ] **Step 1: Upload 平台治理经营健康数据播报**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-briefs"
node feishu-briefs.js create --title "平台治理经营健康数据播报" --file references/平台治理经营健康数据播报.md
```

Expected: JSON with `document_id`. Note the ID.

- [ ] **Step 2: Upload 质检数据播报**

```bash
node feishu-briefs.js create --title "质检数据播报" --file references/质检数据播报.md
```

Expected: JSON with `document_id`. Note the ID.

- [ ] **Step 3: Verify migration**

```bash
node feishu-briefs.js list
```

Expected: JSON array with 2 documents: "平台治理经营健康数据播报" and "质检数据播报".

```bash
node feishu-briefs.js read <doc_id_of_平台治理>
```

Expected: full text content including frontmatter and template body.

- [ ] **Step 4: Clean up test data (optional)**

If test documents from earlier tasks remain, delete them:

```bash
node feishu-briefs.js delete <test_doc_id> --password ""
```

---

### Task 9: Final verification

- [ ] **Step 1: Verify all commands work end-to-end**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-briefs"

# List
node feishu-briefs.js list

# Read (use a doc_id from list output)
node feishu-briefs.js read <doc_id>

# Create + Update + Delete cycle
echo "# Test" > /tmp/test-brief.md
node feishu-briefs.js create --title "验证测试" --file /tmp/test-brief.md
# Use returned doc_id for update and delete
node feishu-briefs.js update <doc_id> --file /tmp/test-brief.md
node feishu-briefs.js delete <doc_id> --password ""
rm /tmp/test-brief.md
```

All commands should succeed without errors.

- [ ] **Step 2: Verify SKILL.md references are correct**

Read `SKILL.md` and confirm all CLI commands match the actual `feishu-briefs.js` interface.
