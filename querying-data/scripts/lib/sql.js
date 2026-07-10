import {
  mkdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import { homedir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import pg from 'pg';

// Monkey-patch pg-protocol BufferReader to handle null field names from Hologres
import pgProtocol from 'pg-protocol';
const OrigBufferReader = pgProtocol.BufferReader || Object.values(pgProtocol).find(v => v && v.prototype && typeof v.prototype.cstring === 'function');
if (OrigBufferReader && OrigBufferReader.prototype.cstring) {
  const origCstring = OrigBufferReader.prototype.cstring;
  OrigBufferReader.prototype.cstring = function() {
    const start = this.offset;
    let end = start;
    // If first byte is null (0), the field name is empty
    if (this.buffer[end] === 0) {
      this.offset = end + 1;
      return '';
    }
    while (this.buffer[end++] !== 0) {}
    this.offset = end;
    return this.buffer.toString(this.encoding, start, end - 1);
  };
}

// 凭证/配置：config.json 是唯一来源
// config.json 缺失或字段不全时抛出明确错误，由 agent 引导用户提供后写回 config.json，再重试
const __dirname = dirname(fileURLToPath(import.meta.url));
const CONFIG_PATH = join(homedir(), '.super-data-analytics', 'config.json');
const CREDENTIAL_KEYS = [
  'HOLOGRES_HOST', 'HOLOGRES_PORT', 'HOLOGRES_DATABASE', 'HOLOGRES_USER', 'HOLOGRES_PASSWORD',
  'POWERBI_CLIENT_ID', 'POWERBI_CLIENT_SECRET', 'POWERBI_TENANT_ID',
];

function loadConfig() {
  let raw;
  try {
    raw = readFileSync(CONFIG_PATH, 'utf-8');
  } catch (err) {
    if (err.code === 'ENOENT') {
      throw new Error(
        `配置文件不存在: ${CONFIG_PATH}\n` +
        `请提供 Hologres 凭证（${CREDENTIAL_KEYS.join(' / ')}），我会帮你写入 config.json 后重试。`
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

  // config.json 唯一来源：直接灌进 process.env 供 HologresClient 读取
  const env = cfg.env || {};
  for (const key of CREDENTIAL_KEYS) {
    if (env[key] !== undefined) process.env[key] = String(env[key]);
  }

  return cfg;
}

// scripts/lib/ → querying-data/（多了一层 lib，向上两级）
const SCHEMA_SQL_PATH = join(__dirname, 'get_table_schema.sql');

function parseTextInputArgs(args, { inputFlag = '--sql', inputLabel = '查询' } = {}) {
  let input = null;
  let savePath = null;
  const seen = new Set();
  const knownFlags = new Set([inputFlag, '--output']);

  const markSeen = (arg) => {
    if (seen.has(arg)) throw new Error(`重复参数: ${arg}`);
    seen.add(arg);
  };

  const readValue = (arg, index) => {
    const value = args[index + 1];
    if (value === undefined || knownFlags.has(value)) throw new Error(`${arg} 需要指定值`);
    return value;
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === inputFlag) {
      markSeen(arg);
      input = readValue(arg, i++);
    } else if (arg === '--output') {
      markSeen(arg);
      savePath = readValue(arg, i++);
    } else {
      throw new Error(`未知输入参数: ${arg}`);
    }
  }

  // 把正文输入 flag 解析成内部 source：
  //   不传 或 -    → stdin（从管道读；- 是 Unix 惯用的"显式 stdin"）
  //   @<path>      → file
  //   其他         → inline（直接内容）
  let source;
  let content = null;
  let inputPath = null;
  if (input === null || input === '-') {
    source = 'stdin';
  } else if (input.startsWith('@')) {
    source = 'file';
    inputPath = input.slice(1);
    if (!inputPath) throw new Error(`${inputFlag} @ 后需提供文件路径`);
  } else {
    source = 'inline';
    content = input;
    if (!content) throw new Error(`${inputFlag} 不能为空`);
  }

  return { source, content, inputPath, savePath };
}

function readTextFile(filePath, label = '查询') {
  let content;
  try {
    content = readFileSync(filePath, 'utf-8').trim();
  } catch (e) {
    throw new Error(`无法读取${label}文件 ${filePath}: ${e.message}`);
  }

  if (!content) {
    throw new Error(`${label}文件为空: ${filePath}`);
  }

  return content;
}

async function readTextFromStdin(stream = process.stdin, { label = 'SQL', inputFlag = '--sql' } = {}) {
  if (typeof stream.setEncoding === 'function') {
    stream.setEncoding('utf8');
  }

  // 非 TTY（脚本/管道/agent 子进程）里，若调用方忘了带正文 flag 且 stdin 没关闭，
  // for-await 会永久挂起。加一个首字节超时：到点没收完就主动报错退出，不再卡死。
  const timeoutMs = Number(process.env.SQL_QUERY_STDIN_TIMEOUT_MS) || 15_000;

  const readPromise = (async () => {
    let content = '';
    for await (const chunk of stream) {
      content += chunk;
    }
    return content.trim();
  })();

  let timer;
  const timeoutPromise = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('STDIN_READ_TIMEOUT')), timeoutMs);
  });

  let content;
  try {
    content = await Promise.race([readPromise, timeoutPromise]);
  } catch (err) {
    // 超时：销毁流以解除挂起的 for-await；其他读取异常原样抛出
    if (stream.destroy) stream.destroy();
    if (err && err.message === 'STDIN_READ_TIMEOUT') {
      throw new Error(
        `等待 stdin 超时（${timeoutMs / 1000}s 内未收到${label}）。\n` +
        `常见原因：在非交互环境（脚本/管道/agent）里既没传 ${inputFlag} "<内容>" / ${inputFlag} @<文件>，stdin 也没关闭。\n` +
        `解决：用 ${inputFlag} 显式传入，或确保管道写完后关闭 stdin。`
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!content) {
    throw new Error(`stdin 中的${label}为空`);
  }

  return content;
}

async function readTextSource(options, stream = process.stdin, opts = {}) {
  const label = opts.label || 'SQL';
  if (options.source === 'stdin') return readTextFromStdin(stream, opts);
  if (options.source === 'file') return readTextFile(options.inputPath, label);

  const content = options.content.trim();
  if (!content) throw new Error(`inline ${label} 为空`);
  return content;
}

function resolveQueryOptions(options, cwd = process.cwd()) {
  // JS 不决定产物去向：不传 --output 则不落盘（只输出到 stdout）；传 --output 才写到 agent 指定路径。
  // .super-data-analytics/{results,scratch} 的布局与命名约定见 SKILL.md，由 agent 构造路径。
  const savePath = options.savePath ? resolve(cwd, options.savePath) : null;
  const inputPath = options.inputPath ? resolve(cwd, options.inputPath) : null;
  return { ...options, savePath, inputPath };
}

function createResultEnvelope({ source, resultPath, result }) {
  const envelope = {
    source,
    row_count: result.rows.length,
    columns: result.columns,
    rows: result.rows,
  };
  if (resultPath) envelope.result_path = resultPath;
  return envelope;
}

class HologresClient {
  constructor() {
    const env = process.env;
    const host = env.HOLOGRES_HOST;
    const port = env.HOLOGRES_PORT;
    const database = env.HOLOGRES_DATABASE;
    const user = env.HOLOGRES_USER;
    const password = env.HOLOGRES_PASSWORD;

    const missing = [
      !host && 'HOLOGRES_HOST',
      !port && 'HOLOGRES_PORT',
      !database && 'HOLOGRES_DATABASE',
      !user && 'HOLOGRES_USER',
      !password && 'HOLOGRES_PASSWORD',
    ].filter(Boolean);

    if (missing.length > 0) {
      throw new Error(
        `配置缺少: ${missing.join(', ')}\n\n` +
        `请补全舰队共享配置 ${CONFIG_PATH} 的 env 块（缺这几项）:\n` +
        '  {\n' +
        '    "env": {\n' +
        '      "HOLOGRES_HOST": "xxx.hologres.aliyuncs.com",\n' +
        '      "HOLOGRES_PORT": "80",\n' +
        '      "HOLOGRES_DATABASE": "your_db",\n' +
        '      "HOLOGRES_USER": "access_id",\n' +
        '      "HOLOGRES_PASSWORD": "access_key"\n' +
        '    }\n' +
        '  }\n' +
        '把缺的几项告诉我，我帮你写入 config.json 后重试。'
      );
    }

    this.pool = new pg.Pool({
      host,
      port: Number(port),
      database,
      user,
      password,
      max: 5,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
    });
  }

  async testConnection() {
    const client = await this.pool.connect();
    try {
      await client.query('SELECT 1');
    } finally {
      client.release();
    }
    return { ok: true, message: '数据库连接成功' };
  }

  async getTableSchema(tableName, schema = 'public') {
    const templateSql = readFileSync(SCHEMA_SQL_PATH, 'utf-8');
    const sql = templateSql
      .replace(/'schema_name'/g, `'${schema}'`)
      .replace(/'table_name'/g, `'${tableName}'`);
    const result = await this.pool.query(sql);
    return result.rows;
  }

  async query(sql) {
    const result = await this.pool.query(sql);
    const columns = result.fields.map((f, i) => ({ name: f.name || `col_${i}`, dataTypeID: f.dataTypeID }));
    return { columns, rows: result.rows };
  }

  async close() {
    await this.pool.end();
  }
}

async function saveResult(envelope, savePath) {
  const ext = savePath.slice(savePath.lastIndexOf('.')).toLowerCase();
  if (!['.json', '.csv', '.xlsx'].includes(ext)) {
    throw new Error(`不支持的文件格式: ${ext}（支持 .json / .csv / .xlsx）`);
  }

  mkdirSync(dirname(savePath), { recursive: true });

  if (ext === '.json') {
    writeFileSync(savePath, JSON.stringify(envelope, null, 2), 'utf-8');
  } else if (ext === '.csv') {
    const { columns, rows } = envelope;
    const header = columns.map(c => c.name).join(',');
    const dataRows = rows.map(row => columns.map(c => {
      const val = row[c.name];
      const str = val === null || val === undefined ? '' : String(val);
      return str.includes(',') || str.includes('"') || str.includes('\n')
        ? `"${str.replace(/"/g, '""')}"`
        : str;
    }).join(','));
    writeFileSync(savePath, [header, ...dataRows].join('\n'), 'utf-8');
  } else if (ext === '.xlsx') {
    let raw;
    try {
      raw = await import('xlsx');
    } catch {
      throw new Error('xlsx 格式需要安装 xlsx 依赖: npm install xlsx');
    }
    // xlsx 0.18.5 的 ESM 顶层只有 read/write/writeFile/utils，readFile 等挂在 default 上；
    // 归一化成同一个对象，免得不同版本/导入方式踩 export 形态差异。
    const XLSX = raw.default || raw;
    const { columns, rows } = envelope;
    const header = columns.map(c => c.name);
    const dataRows = rows.map(row => columns.map(c => row[c.name]));
    const ws = XLSX.utils.aoa_to_sheet([header, ...dataRows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
    XLSX.writeFile(wb, savePath);
  }
}

export {
  loadConfig,
  HologresClient,
  parseTextInputArgs,
  resolveQueryOptions,
  readTextSource,
  createResultEnvelope,
  saveResult,
};
