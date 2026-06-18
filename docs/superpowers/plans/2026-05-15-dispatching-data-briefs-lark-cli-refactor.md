# Dispatching Data Briefs — lark-cli Refactor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor feishu-briefs.js to use lark-cli as backend, add DocxXML formatting via mdToXml converter.

**Architecture:** feishu-briefs.js becomes a thin wrapper calling lark-cli via `execFileSync`. Only domain logic remains: mdToXml conversion, cache file management, and password verification. All HTTP/auth/rate-limit complexity delegated to lark-cli.

**Tech Stack:** Node.js 18+ ESM, `child_process.execFileSync`, lark-cli, no extra npm dependencies.

---

## File Structure

```
dispatching-data-briefs/
├── feishu-briefs.js         # [REWRITE] lark-cli backend + mdToXml
├── package.json             # [KEEP] type: module
├── .env                     # [MODIFY] remove APP_ID/SECRET
├── SKILL.md                 # [MODIFY] add lark-cli setup reference
└── references/
    └── setup.md             # [CREATE] lark-cli installation guide
```

---

### Task 1: Rewrite feishu-briefs.js

**Files:**
- Rewrite: `dispatching-data-briefs/feishu-briefs.js`

- [ ] **Step 1: Write the complete new feishu-briefs.js**

Replace the entire file with:

```javascript
import { readFileSync, writeFileSync, existsSync, unlinkSync, mkdirSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// ---------------------------------------------------------------------------
// .env loading
// ---------------------------------------------------------------------------
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

const CACHE_DIR = join(__dirname, 'cache');

// ---------------------------------------------------------------------------
// lark-cli wrapper
// ---------------------------------------------------------------------------
function larkExec(args) {
  try {
    return execFileSync('lark-cli', args, { encoding: 'utf-8' });
  } catch (err) {
    const stderr = err.stderr || '';
    const msg = stderr.trim() || err.message;
    throw new Error(`lark-cli error: ${msg}`);
  }
}

// ---------------------------------------------------------------------------
// XML escape — only for text content, not tags
// ---------------------------------------------------------------------------
function xmlEscape(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ---------------------------------------------------------------------------
// Markdown → DocxXML converter
// ---------------------------------------------------------------------------
function mdToXml(markdown) {
  const lines = markdown.split('\n');
  const xmlParts = [];
  let inCode = false;
  let codeLines = [];
  let codeLang = '';
  let inFrontmatter = false;
  let frontmatterLines = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // --- Frontmatter detection ---
    if (i === 0 && line.trim() === '---') {
      inFrontmatter = true;
      continue;
    }
    if (inFrontmatter) {
      if (line.trim() === '---') {
        // End frontmatter → emit as yaml code block
        xmlParts.push(`<pre lang="yaml" caption="配置">${xmlEscape(frontmatterLines.join('\n'))}</pre>`);
        xmlParts.push('<hr/>');
        inFrontmatter = false;
        frontmatterLines = [];
      } else {
        frontmatterLines.push(line);
      }
      continue;
    }

    // --- Code block ---
    const codeMatch = line.match(/^```(\w*)/);
    if (codeMatch) {
      if (inCode) {
        xmlParts.push(`<pre lang="${codeLang || 'text'}"><code>${xmlEscape(codeLines.join('\n'))}</code></pre>`);
        codeLines = [];
        inCode = false;
        codeLang = '';
      } else {
        inCode = true;
        codeLang = codeMatch[1] || '';
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    // --- Skip empty lines ---
    if (line.trim() === '') continue;

    // --- Horizontal rule ---
    if (/^---+\s*$/.test(line.trim())) {
      xmlParts.push('<hr/>');
      continue;
    }

    // --- Table ---
    if (line.includes('|') && line.trim().startsWith('|')) {
      const tableLines = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i]);
        i++;
      }
      i--; // back up one since the for loop will increment
      xmlParts.push(parseTable(tableLines));
      continue;
    }

    // --- Heading ---
    const headingMatch = line.match(/^(#{1,9})\s+(.*)/);
    if (headingMatch) {
      const level = Math.min(headingMatch[1].length, 9);
      xmlParts.push(`<h${level}>${xmlEscape(headingMatch[2].trim())}</h${level}>`);
      continue;
    }

    // --- Bullet list (collect consecutive items) ---
    if (/^[-*]\s+/.test(line.trim())) {
      const items = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ''));
        i++;
      }
      i--;
      const liTags = items.map(item => `<li>${xmlEscape(item)}</li>`).join('');
      xmlParts.push(`<ul>${liTags}</ul>`);
      continue;
    }

    // --- Plain text paragraph ---
    xmlParts.push(`<p>${xmlEscape(line)}</p>`);
  }

  // Unclosed code block
  if (inCode && codeLines.length > 0) {
    xmlParts.push(`<pre lang="${codeLang || 'text'}"><code>${xmlEscape(codeLines.join('\n'))}</code></pre>`);
  }

  return xmlParts.join('\n');
}

function parseTable(lines) {
  // Filter out separator lines (|---|---|)
  const dataLines = lines.filter(l => !/^\|[\s\-:|]+\|?$/.test(l.trim()));
  if (dataLines.length === 0) return '';

  const rows = dataLines.map(l =>
    l.split('|').map(c => c.trim()).filter(c => c !== '')
  );

  if (rows.length === 0) return '';

  const colCount = rows[0].length;
  let xml = '<table>';
  xml += `<colgroup><col span="${colCount}" width="120"/></colgroup>`;

  // First row as header
  const headerCells = rows[0].map(cell =>
    `<th background-color="light-gray">${xmlEscape(cell)}</th>`
  ).join('');
  xml += `<thead><tr>${headerCells}</tr></thead>`;

  // Remaining rows as body
  if (rows.length > 1) {
    const bodyRows = rows.slice(1).map(row => {
      const cells = row.map(cell => `<td>${xmlEscape(cell)}</td>`).join('');
      return `<tr>${cells}</tr>`;
    }).join('');
    xml += `<tbody>${bodyRows}</tbody>`;
  }

  xml += '</table>';
  return xml;
}

// ---------------------------------------------------------------------------
// Cache file helpers
// ---------------------------------------------------------------------------
function ensureCacheDir() {
  if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
}

function maybeDropFile(filePath, drop) {
  if (drop && filePath && existsSync(filePath)) {
    unlinkSync(filePath);
    console.error(`Dropped temp file: ${filePath}`);
  }
}

// ---------------------------------------------------------------------------
// CLI commands
// ---------------------------------------------------------------------------
async function cmdList() {
  const folderToken = process.env.FEISHU_FOLDER_TOKEN;
  if (!folderToken) throw new Error('FEISHU_FOLDER_TOKEN not set in .env');

  const output = larkExec([
    'drive', '+search',
    '--query', '',
    '--folder-tokens', folderToken,
    '--doc-types', 'docx',
    '--format', 'json',
  ]);

  // lark-cli returns JSON with results array
  const data = JSON.parse(output);
  const results = (data.results || []).map(r => ({
    id: r.token || r.id,
    name: r.title || r.name,
    type: r.doc_type || r.type || 'docx',
    url: r.url,
    modified_time: r.edit_time || r.modified_time,
  }));

  console.log(JSON.stringify(results, null, 2));
}

async function cmdRead(docId) {
  if (!docId) throw new Error('Usage: node feishu-briefs.js read <doc_id>');

  const output = larkExec([
    'docs', '+fetch',
    '--api-version', 'v2',
    '--doc', docId,
    '--doc-format', 'markdown',
  ]);

  // lark-cli returns the document content
  // Try to extract markdown content from JSON response
  try {
    const data = JSON.parse(output);
    console.log(data.data?.content || data.content || output);
  } catch {
    // If not JSON, output is the raw content
    console.log(output);
  }
}

async function cmdCreate(args) {
  let title;
  let filePath;
  let drop = false;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--title') title = args[++i];
    else if (args[i] === '--file') filePath = args[++i];
    else if (args[i] === '--drop') drop = true;
  }

  if (!title) throw new Error('Usage: node feishu-briefs.js create --title "XX" [--file <path>] [--drop]');

  const folderToken = process.env.FEISHU_FOLDER_TOKEN;
  if (!folderToken) throw new Error('FEISHU_FOLDER_TOKEN not set in .env');

  // Convert markdown to XML
  let xmlContent = `<title>${xmlEscape(title)}</title>`;
  if (filePath) {
    const md = readFileSync(resolve(filePath), 'utf-8');
    xmlContent = `<title>${xmlEscape(title)}</title>\n${mdToXml(md)}`;
  }

  // Write XML to temp file for safe passing to lark-cli
  ensureCacheDir();
  const xmlTempPath = join(CACHE_DIR, `xml-create-${Date.now()}.xml`);
  writeFileSync(xmlTempPath, xmlContent, 'utf-8');

  try {
    const xmlStr = readFileSync(xmlTempPath, 'utf-8');
    const output = larkExec([
      'docs', '+create',
      '--api-version', 'v2',
      '--parent-token', folderToken,
      '--content', xmlStr,
    ]);

    const data = JSON.parse(output);
    const docId = data.data?.document?.document_id;
    if (!docId) throw new Error('Failed to create document: no document_id returned');

    console.error(`Created document: ${docId}`);
    console.log(JSON.stringify({ document_id: docId, title }, null, 2));
  } finally {
    // Always clean up XML temp file
    if (existsSync(xmlTempPath)) unlinkSync(xmlTempPath);
    // Maybe drop the markdown source file
    if (filePath) maybeDropFile(resolve(filePath), drop);
  }
}

async function cmdUpdate(args) {
  const docId = args[0];
  if (!docId) throw new Error('Usage: node feishu-briefs.js update <doc_id> --file <path> [--drop]');

  let filePath;
  let drop = false;
  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--file') filePath = args[++i];
    else if (args[i] === '--drop') drop = true;
  }

  if (!filePath) throw new Error('Usage: node feishu-briefs.js update <doc_id> --file <path> [--drop]');

  // Read file and convert to XML
  const md = readFileSync(resolve(filePath), 'utf-8');
  const xmlContent = mdToXml(md);

  // Write XML to temp file
  ensureCacheDir();
  const xmlTempPath = join(CACHE_DIR, `xml-update-${Date.now()}.xml`);
  writeFileSync(xmlTempPath, xmlContent, 'utf-8');

  try {
    const xmlStr = readFileSync(xmlTempPath, 'utf-8');
    const output = larkExec([
      'docs', '+update',
      '--api-version', 'v2',
      '--doc', docId,
      '--command', 'overwrite',
      '--content', xmlStr,
    ]);

    console.error(`Updated document: ${docId}`);
    console.log(JSON.stringify({ updated: true, document_id: docId }, null, 2));
  } finally {
    if (existsSync(xmlTempPath)) unlinkSync(xmlTempPath);
    maybeDropFile(resolve(filePath), drop);
  }
}

async function cmdDelete(args) {
  const docId = args[0];
  if (!docId) throw new Error('Usage: node feishu-briefs.js delete <doc_id> --password <pwd>');

  let password;
  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--password') password = args[++i];
  }

  const envPassword = process.env.FEISHU_DELETE_PASSWORD;
  if (envPassword) {
    if (!password) throw new Error('Password required (FEISHU_DELETE_PASSWORD is set)');
    if (password !== envPassword) throw new Error('Incorrect password');
  }

  const params = JSON.stringify({ token: docId, type: 'docx' });
  larkExec([
    'drive', 'files', 'delete',
    '--params', params,
  ]);

  console.log(JSON.stringify({ deleted: true, document_id: docId }, null, 2));
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  if (!command) {
    console.error(
      'Usage: node feishu-briefs.js <command> [args]\n\n' +
      'Commands:\n' +
      '  list                                         List documents in folder\n' +
      '  read <doc_id>                                Read document content\n' +
      '  create --title "X" [--file path] [--drop]    Create document\n' +
      '  update <doc_id> --file <path> [--drop]       Update document (overwrite)\n' +
      '  delete <doc_id> --password <pwd>             Delete document',
    );
    process.exit(1);
  }

  try {
    switch (command) {
      case 'list':
        await cmdList();
        break;
      case 'read':
        await cmdRead(args[1]);
        break;
      case 'create':
        await cmdCreate(args.slice(1));
        break;
      case 'update':
        await cmdUpdate(args.slice(1));
        break;
      case 'delete':
        await cmdDelete(args.slice(1));
        break;
      default:
        console.error(`Unknown command: ${command}`);
        process.exit(1);
    }
  } catch (err) {
    console.error(`Error: ${err.message}`);
    process.exit(1);
  }
}

main();
```

- [ ] **Step 2: Verify lark-cli is available**

```bash
lark-cli --version
```

Expected: version number. If not found, install lark-cli first.

- [ ] **Step 3: Smoke test — list command**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-briefs"
node feishu-briefs.js list
```

Expected: JSON array of documents currently in the Feishu folder.

---

### Task 2: Update .env

**Files:**
- Modify: `dispatching-data-briefs/.env`

- [ ] **Step 1: Remove app credentials from .env**

The new content (auth is handled by lark-cli, not our .env):

```
FEISHU_FOLDER_TOKEN=XvG6feei4lr5XFdaGzEcsxGrnkg
FEISHU_DELETE_PASSWORD=
```

Remove `FEISHU_APP_ID` and `FEISHU_APP_SECRET` lines.

---

### Task 3: Create lark-cli setup guide

**Files:**
- Create: `dispatching-data-briefs/references/setup.md`

- [ ] **Step 1: Write the setup guide**

```markdown
# lark-cli 安装与配置

feishu-briefs.js 依赖 lark-cli 来操作飞书文档。

## 安装

```bash
npm install -g @anthropic-ai/lark-cli
```

## 初始化

```bash
lark-cli config init
```

按提示输入飞书应用的 App ID 和 App Secret。

## 登录授权

```bash
lark-cli auth login
```

选择需要的权限 scope，至少包含：
- `docx:document` — 读写文档
- `drive:drive` — 管理云空间文件
- `search:docs:read` — 搜索文档

## 验证

```bash
lark-cli docs +fetch --api-version v2 --help
```

如果显示帮助信息，说明安装成功。

## 故障排除

- `lark-cli: command not found` — 确认 npm 全局安装目录在 PATH 中
- `Permission denied` — 在飞书开放平台检查应用权限和 Admin Consent
- `Auth failed` — 运行 `lark-cli auth login` 重新授权
```

---

### Task 4: Update SKILL.md

**Files:**
- Modify: `dispatching-data-briefs/SKILL.md`

- [ ] **Step 1: Add lark-cli prerequisite to SKILL.md**

In SKILL.md, add a new section right after the `# 数据播报` heading and before `## 意图识别`:

```markdown
## 前置条件

本 skill 依赖 lark-cli 操作飞书文档。如果 `node feishu-briefs.js list` 报错 "lark-cli error"，请按 [`references/setup.md`](references/setup.md) 安装和配置 lark-cli。
```

Also update the `create` and `update` command descriptions in the CLI section to mention `--drop`:

```bash
# 创建新模板（默认保留临时文件，加 --drop 执行后删除）
node feishu-briefs.js create --title "播报名称" --file <content_file> [--drop]

# 更新模板（覆盖同一文档，ID 不变，加 --drop 执行后删除）
node feishu-briefs.js update <doc_id> --file <content_file> [--drop]
```

---

### Task 5: End-to-end verification

- [ ] **Step 1: Test all CRUD commands**

```bash
cd "c:/Users/Administrator/.agents/skills/super-data-analyst/dispatching-data-briefs"

# List existing templates
node feishu-briefs.js list

# Read an existing template (use doc_id from list output)
node feishu-briefs.js read <existing_doc_id>

# Create a test document
mkdir -p cache
echo "# 测试播报

## 数据源
- 类型：powerbi
- 模型：测试看板

## 指标
| 指标 | 本周 | 上周 | 周环比 |
|---|---|---|---|
| 用户数 | 1000 | 800 | +25% |
| 退费率 | 1.5% | 2.0% | -25% |

---
结束" > cache/create-测试播报-20260515-120000.md

node feishu-briefs.js create --title "验证测试" --file cache/create-测试播报-20260515-120000.md

# Verify file is kept (default --keep)
ls cache/create-测试播报-20260515-120000.md

# Update the document (use doc_id from create output)
echo "# 测试播报 v2" > cache/update-测试播报-20260515-120001.md
node feishu-briefs.js update <doc_id> --file cache/update-测试播报-20260515-120001.md --drop

# Verify --drop removed the file
ls cache/update-测试播报-20260515-120001.md

# Delete the test document
node feishu-briefs.js delete <doc_id> --password ""

# Clean up
rm cache/create-测试播报-20260515-120000.md
```

Expected: all commands succeed. The created document should appear in Feishu with formatted headings, table, and horizontal rules.

- [ ] **Step 2: Verify migrated templates are still accessible**

```bash
node feishu-briefs.js list
```

Expected: the two migrated templates (平台治理经营健康数据播报, 质检数据播报) still appear.

```bash
node feishu-briefs.js read <平台治理_doc_id>
```

Expected: full text content of the template.
