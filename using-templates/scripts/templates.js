import { readFileSync, writeFileSync, existsSync, unlinkSync, mkdirSync } from 'node:fs';
import { join, dirname, resolve, isAbsolute, basename } from 'node:path';
import { homedir, tmpdir } from 'node:os';
import { execFileSync, execFile } from 'node:child_process';

// ---------------------------------------------------------------------------
// 配置：~/.super-data-analytics/config.json 是唯一来源
// 与 querying-data 同一约定：脚本不读 .env、不依赖环境变量导出，
// config.json 的 env 块整体合并进 process.env。缺失时由 agent 引导补全后重试。
// ---------------------------------------------------------------------------
const CONFIG_PATH = join(homedir(), '.super-data-analytics', 'config.json');

const TEMPLATE_KEYS = [
  'FEISHU_TEMPLATE_FOLDER_TOKEN',
  'FEISHU_TEMPLATE_DELETE_PASSWORD',
];

function loadConfig() {
  let raw;
  try {
    raw = readFileSync(CONFIG_PATH, 'utf-8');
  } catch (err) {
    if (err.code === 'ENOENT') {
      throw new Error(
        `配置文件不存在: ${CONFIG_PATH}\n` +
        `请把模板所需配置（${TEMPLATE_KEYS.join(' / ')}）告诉我，我会帮你写入 config.json 的 env 块后重试。`
      );
    }
    throw new Error(`读取配置失败 ${CONFIG_PATH}: ${err.message}`);
  }

  let cfg;
  try {
    cfg = JSON.parse(raw);
  } catch (err) {
    throw new Error(`解析配置失败 ${CONFIG_PATH}: ${err.message}`);
  }

  // config.json 的 env 块整体合并进 process.env（已有值不覆盖）
  const env = cfg.env || {};
  for (const key of Object.keys(env)) {
    if (process.env[key] === undefined) process.env[key] = String(env[key]);
  }
}

// ---------------------------------------------------------------------------
// lark-cli 封装（优先以 user 身份调用，失败后回退到 bot）
// lark-cli 的 @文件引用必须是「当前目录内的相对路径」，拒绝绝对路径和 CWD 外的路径。
// 因此每次调用按 @引用文件所在目录设置 cwd，并传相对 basename。
// ---------------------------------------------------------------------------

/** 缓存已确认可用的身份，避免每次都重试 */
let resolvedIdentity = null;

function larkExec(args, cwd) {
  const opts = { encoding: 'utf-8' };
  if (cwd) opts.cwd = cwd;
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
function larkExecAsync(args, cwd) {
  const opts = { encoding: 'utf-8' };
  if (cwd) opts.cwd = cwd;
  if (process.platform === 'win32') opts.shell = true;

  const tryWith = (identity) => new Promise((resolveP, rejectP) => {
    execFile('lark-cli', [...args, '--as', identity], opts, (err, stdout) => {
      if (err) rejectP(err);
      else resolveP(stdout);
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
// 临时文件辅助函数（实现细节，落 OS tmpdir，不进工作区）
// ---------------------------------------------------------------------------

/** 在 tmpdir 下建一个本调用专属子目录，返回其路径（lark-cli 要求 @文件在其 CWD 内） */
function newTempDir(label) {
  const dir = join(tmpdir(), `templates-${process.pid}-${label}-${Date.now()}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

// ---------------------------------------------------------------------------
// CLI 命令
// ---------------------------------------------------------------------------

/** 列出单个文件夹下的文件，返回解析后的文件数组（含子文件夹和文档） */
async function listFolderFiles(folderToken) {
  const dir = newTempDir('list');
  const paramsName = 'params.json';
  writeFileSync(join(dir, paramsName), JSON.stringify({ folder_token: folderToken, page_size: '200' }));

  try {
    const output = await larkExecAsync([
      'drive', 'files', 'list',
      '--params', `@${paramsName}`,
      '--format', 'json',
      '--page-all',
    ], dir);
    const data = JSON.parse(output);
    return data.data?.files || data.files || [];
  } finally {
    if (existsSync(join(dir, paramsName))) unlinkSync(join(dir, paramsName));
  }
}

async function cmdList() {
  const folderToken = process.env.FEISHU_TEMPLATE_FOLDER_TOKEN;
  if (!folderToken) throw new Error('config.json env 中未设置 FEISHU_TEMPLATE_FOLDER_TOKEN');

  // 第一步：列出根目录文件 — 收集 docx 文档 + 识别子文件夹
  const rootFiles = await listFolderFiles(folderToken);

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
      const files = await listFolderFiles(folder.token);
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

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--title') title = args[++i];
    else if (args[i] === '--file') filePath = args[++i];
  }

  if (!title) throw new Error('用法: node templates.js create --title "标题" [--file <路径>]');

  const folderToken = process.env.FEISHU_TEMPLATE_FOLDER_TOKEN;
  if (!folderToken) throw new Error('config.json env 中未设置 FEISHU_TEMPLATE_FOLDER_TOKEN');

  const cliArgs = [
    'docs', '+create',
    '--api-version', 'v2',
    '--parent-token', folderToken,
  ];

  let absFilePath;
  if (filePath) {
    // 直接用 agent 提供的 scratch 文件：cwd 设到文件所在目录，@传相对 basename（lark-cli 要求 CWD 内相对路径）
    absFilePath = isAbsolute(filePath) ? filePath : resolve(process.cwd(), filePath);
    if (!existsSync(absFilePath)) throw new Error(`文件不存在: ${absFilePath}`);
    cliArgs.push('--content', `@${basename(absFilePath)}`, '--doc-format', 'markdown');
  } else {
    cliArgs.push('--content', `# ${title}`, '--doc-format', 'markdown');
  }

  const output = larkExec(cliArgs, absFilePath ? dirname(absFilePath) : undefined);
  const data = JSON.parse(output);
  const docId = data.data?.doc_id || data.data?.document?.document_id || data.data?.document_id || data.document_id;
  if (!docId) throw new Error(`创建文档失败: 未返回 document_id\n输出: ${output}`);
  console.error(`已创建文档: ${docId}`);
  console.log(JSON.stringify({ document_id: docId, title }, null, 2));
}

async function cmdUpdate(args) {
  const docId = args[0];
  if (!docId) throw new Error('用法: node templates.js update <doc_id> --file <路径>');

  let filePath;
  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--file') filePath = args[++i];
  }

  if (!filePath) throw new Error('用法: node templates.js update <doc_id> --file <路径>');

  // 直接用 agent 提供的 scratch 文件：cwd 设到文件所在目录，@传相对 basename（lark-cli 要求 CWD 内相对路径）
  const absFilePath = isAbsolute(filePath) ? filePath : resolve(process.cwd(), filePath);
  if (!existsSync(absFilePath)) throw new Error(`文件不存在: ${absFilePath}`);

  larkExec([
    'docs', '+update',
    '--api-version', 'v2',
    '--doc', docId,
    '--command', 'overwrite',
    '--content', `@${basename(absFilePath)}`,
    '--doc-format', 'markdown',
  ], dirname(absFilePath));

  console.error(`已更新文档: ${docId}`);
  console.log(JSON.stringify({ updated: true, document_id: docId }, null, 2));
}

async function cmdDelete(args) {
  const docId = args[0];
  if (!docId) throw new Error('用法: node templates.js delete <doc_id> --password <密码>');

  let password;
  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--password') password = args[++i];
  }

  const envPassword = process.env.FEISHU_TEMPLATE_DELETE_PASSWORD;
  if (envPassword) {
    if (!password) throw new Error('需要密码（已设置 FEISHU_TEMPLATE_DELETE_PASSWORD）');
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
      '  create --title "标题" [--file 路径]          创建文档\n' +
      '  update <doc_id> --file <路径>               更新文档（覆盖）\n' +
      '  delete <doc_id> --password <密码>            删除文档',
    );
    process.exit(1);
  }

  // 凭证/配置在主入口统一加载
  loadConfig();

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
