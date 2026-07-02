import { readFileSync, writeFileSync, existsSync, unlinkSync, mkdirSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { execFileSync, execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// ---------------------------------------------------------------------------
// .env 加载 — 仅查找当前目录（scripts/）和上一级目录（skill 根目录）
// ---------------------------------------------------------------------------
const __dirname = dirname(fileURLToPath(import.meta.url));
const parentDir = dirname(__dirname);

function loadEnv(dir) {
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
  } catch {}
}

loadEnv(__dirname);   // scripts/.env
loadEnv(parentDir);   // using-templates/.env

const CACHE_DIR = join(__dirname, 'cache');

// ---------------------------------------------------------------------------
// lark-cli 封装（优先以 user 身份调用，失败后回退到 bot）
// lark-cli 的 @文件路径相对于 CWD，所以始终先切换工作目录
// ---------------------------------------------------------------------------

/** 缓存已确认可用的身份，避免每次都重试 */
let resolvedIdentity = null;

function larkExec(args) {
  const opts = { encoding: 'utf-8', cwd: __dirname };
  if (process.platform === 'win32') opts.shell = true;

  // 如果已有缓存的可用身份，直接用
  if (resolvedIdentity) {
    return execFileSync('lark-cli', [...args, '--as', resolvedIdentity], opts);
  }

  // 先试 user，失败再试 bot
  try {
    const result = execFileSync('lark-cli', [...args, '--as', 'user'], opts);
    resolvedIdentity = 'user';
    return result;
  } catch {
    const result = execFileSync('lark-cli', [...args, '--as', 'bot'], opts);
    resolvedIdentity = 'bot';
    return result;
  }
}

/** 异步版本 — 支持并行调用多个子进程 */
function larkExecAsync(args) {
  const opts = { encoding: 'utf-8', cwd: __dirname };
  if (process.platform === 'win32') opts.shell = true;

  const tryWith = (identity) => new Promise((resolve, reject) => {
    execFile('lark-cli', [...args, '--as', identity], opts, (err, stdout, stderr) => {
      if (err) reject(err);
      else resolve(stdout);
    });
  });

  // 已缓存则直接用
  if (resolvedIdentity) return tryWith(resolvedIdentity);

  // 先试 user，失败再试 bot
  return tryWith('user')
    .then(stdout => { resolvedIdentity = 'user'; return stdout; })
    .catch(() => tryWith('bot').then(stdout => { resolvedIdentity = 'bot'; return stdout; }));
}

// ---------------------------------------------------------------------------
// 缓存文件辅助函数
// ---------------------------------------------------------------------------
function ensureCacheDir() {
  if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
}

function maybeDropFile(filePath, drop) {
  if (drop && filePath && existsSync(filePath)) {
    unlinkSync(filePath);
    console.error(`已删除临时文件: ${filePath}`);
  }
}

/** 将源文件复制到 cache/ 目录并加上时间戳命名，返回相对路径 */
function stageInCache(srcPath) {
  ensureCacheDir();
  const rel = join('cache', `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`);
  writeFileSync(join(__dirname, rel), readFileSync(resolve(srcPath), 'utf-8'));
  return rel;
}

// ---------------------------------------------------------------------------
// CLI 命令
// ---------------------------------------------------------------------------

/**
 * 列出单个文件夹下的文件（同步）。
 * 返回解析后的文件数组（可能包含子文件夹和文档）。
 */
function listFolderFiles(folderToken) {
  ensureCacheDir();
  const paramsFile = join('cache', `params-list-${Date.now()}.json`);
  writeFileSync(join(__dirname, paramsFile), JSON.stringify({ folder_token: folderToken, page_size: '200' }));

  try {
    const output = larkExec([
      'drive', 'files', 'list',
      '--params', `@${paramsFile}`,
      '--format', 'json',
      '--page-all',
    ]);
    const data = JSON.parse(output);
    return data.data?.files || data.files || [];
  } finally {
    if (existsSync(join(__dirname, paramsFile))) unlinkSync(join(__dirname, paramsFile));
  }
}

/** 异步版本 — 用于并行查询子文件夹 */
async function listFolderFilesAsync(folderToken) {
  ensureCacheDir();
  const paramsFile = join('cache', `params-list-${Date.now()}.json`);
  writeFileSync(join(__dirname, paramsFile), JSON.stringify({ folder_token: folderToken, page_size: '200' }));

  try {
    const output = await larkExecAsync([
      'drive', 'files', 'list',
      '--params', `@${paramsFile}`,
      '--format', 'json',
      '--page-all',
    ]);
    const data = JSON.parse(output);
    return data.data?.files || data.files || [];
  } finally {
    if (existsSync(join(__dirname, paramsFile))) unlinkSync(join(__dirname, paramsFile));
  }
}

async function cmdList() {
  const folderToken = process.env.FEISHU_FOLDER_TOKEN;
  if (!folderToken) throw new Error('.env 中未设置 FEISHU_FOLDER_TOKEN');

  // 第一步：列出根目录文件 — 收集 docx 文档 + 识别子文件夹
  const rootFiles = listFolderFiles(folderToken);

  const results = [];

  // 根目录下的文档 → category 为空
  for (const f of rootFiles) {
    if (f.type === 'docx' || f.type === 'doc') {
      results.push({
        id: f.token || f.id,
        name: f.name,
        category: '',
        type: f.type,
        url: f.url,
        modified_time: f.modified_time,
      });
    }
  }

  // 第二步：并行查询每个子文件夹（仅深入一层，忽略更深层级）
  const subFolders = rootFiles.filter(f => f.type === 'folder');

  const subResults = await Promise.all(
    subFolders.map(async (folder) => {
      const files = await listFolderFilesAsync(folder.token);
      return files
        .filter(f => f.type === 'docx' || f.type === 'doc')
        .map(f => ({
          id: f.token || f.id,
          name: f.name,
          category: folder.name,
          type: f.type,
          url: f.url,
          modified_time: f.modified_time,
        }));
    }),
  );

  results.push(...subResults.flat());
  console.log(JSON.stringify(results, null, 2));
}

async function cmdRead(docId) {
  if (!docId) throw new Error('用法: node templates.js read <doc_id>');

  const output = larkExec([
    'docs', '+fetch',
    '--api-version', 'v2',
    '--doc', docId,
    '--doc-format', 'markdown',
    '--format', 'json',
  ]);

  try {
    const data = JSON.parse(output);
    const markdown = data.data?.document?.content || data.data?.markdown || data.markdown || '';
    console.log(markdown);
  } catch {
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

  if (!title) throw new Error('用法: node templates.js create --title "标题" [--file <路径>] [--drop]');

  const folderToken = process.env.FEISHU_FOLDER_TOKEN;
  if (!folderToken) throw new Error('.env 中未设置 FEISHU_FOLDER_TOKEN');

  const cliArgs = [
    'docs', '+create',
    '--api-version', 'v2',
    '--parent-token', folderToken,
  ];

  let stagedFile;
  if (filePath) {
    stagedFile = stageInCache(filePath);
    cliArgs.push('--content', `@${stagedFile}`, '--doc-format', 'markdown');
  } else {
    cliArgs.push('--content', `# ${title}`, '--doc-format', 'markdown');
  }

  try {
    const output = larkExec(cliArgs);
    const data = JSON.parse(output);
    const docId = data.data?.doc_id || data.data?.document?.document_id || data.data?.document_id || data.document_id;
    if (!docId) throw new Error(`创建文档失败: 未返回 document_id\n输出: ${output}`);
    console.error(`已创建文档: ${docId}`);
    console.log(JSON.stringify({ document_id: docId, title }, null, 2));
  } finally {
    if (stagedFile && existsSync(join(__dirname, stagedFile))) unlinkSync(join(__dirname, stagedFile));
    if (filePath) maybeDropFile(resolve(filePath), drop);
  }
}

async function cmdUpdate(args) {
  const docId = args[0];
  if (!docId) throw new Error('用法: node templates.js update <doc_id> --file <路径> [--drop]');

  let filePath;
  let drop = false;
  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--file') filePath = args[++i];
    else if (args[i] === '--drop') drop = true;
  }

  if (!filePath) throw new Error('用法: node templates.js update <doc_id> --file <路径> [--drop]');

  const stagedFile = stageInCache(filePath);

  try {
    larkExec([
      'docs', '+update',
      '--api-version', 'v2',
      '--doc', docId,
      '--command', 'overwrite',
      '--content', `@${stagedFile}`,
      '--doc-format', 'markdown',
    ]);

    console.error(`已更新文档: ${docId}`);
    console.log(JSON.stringify({ updated: true, document_id: docId }, null, 2));
  } finally {
    if (existsSync(join(__dirname, stagedFile))) unlinkSync(join(__dirname, stagedFile));
    maybeDropFile(resolve(filePath), drop);
  }
}

async function cmdDelete(args) {
  const docId = args[0];
  if (!docId) throw new Error('用法: node templates.js delete <doc_id> --password <密码>');

  let password;
  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--password') password = args[++i];
  }

  const envPassword = process.env.FEISHU_DELETE_PASSWORD;
  if (envPassword) {
    if (!password) throw new Error('需要密码（已设置 FEISHU_DELETE_PASSWORD）');
    if (password !== envPassword) throw new Error('密码错误');
  }

  larkExec([
    'drive', '+delete',
    '--file-token', docId,
    '--type', 'docx',
    '--yes',
  ]);

  console.log(JSON.stringify({ deleted: true, document_id: docId }, null, 2));
}

// ---------------------------------------------------------------------------
// 主入口
// ---------------------------------------------------------------------------
async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  if (!command) {
    console.error(
      '用法: node templates.js <命令> [参数]\n\n' +
      '命令:\n' +
      '  list                                         列出文件夹中的文档\n' +
      '  read <doc_id>                                读取文档内容\n' +
      '  create --title "标题" [--file 路径] [--drop]  创建文档\n' +
      '  update <doc_id> --file <路径> [--drop]       更新文档（覆盖）\n' +
      '  delete <doc_id> --password <密码>            删除文档',
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
        console.error(`未知命令: ${command}`);
        process.exit(1);
    }
  } catch (err) {
    console.error(`错误: ${err.message}`);
    process.exit(1);
  }
}

main();
