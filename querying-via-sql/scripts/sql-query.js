import {
  mkdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import { randomUUID } from 'node:crypto';
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

// 凭证/配置：config.json 是唯一来源（舰队共享一份），不再做环境变量优先回退。
// config.json 缺失或字段不全时抛出明确错误，由 agent 引导用户提供后写回 config.json，再重试。
const __dirname = dirname(fileURLToPath(import.meta.url));
const CONFIG_PATH = join(homedir(), '.super-data-analytics', 'config.json');
const CREDENTIAL_KEYS = ['HOLOGRES_HOST', 'HOLOGRES_PORT', 'HOLOGRES_DATABASE', 'HOLOGRES_USER', 'HOLOGRES_PASSWORD'];

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

  // config.json 唯一来源：直接灌进 process.env 供 HologresClient 读取（不再保留环境变量覆盖语义）。
  const env = cfg.env || {};
  for (const key of CREDENTIAL_KEYS) {
    if (env[key] !== undefined) process.env[key] = String(env[key]);
  }
  return cfg;
}

const ROOT_DIR = dirname(__dirname);
const SCHEMA_SQL_PATH = join(ROOT_DIR, 'references', 'get_table_schema.sql');

export function parseQueryArgs(args) {
  let query = null;
  let savePath = null;
  const seen = new Set();
  const knownFlags = new Set(['--query', '--save']);

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
    if (arg === '--query') {
      markSeen(arg);
      query = readValue(arg, i++);
    } else if (arg === '--save') {
      markSeen(arg);
      savePath = readValue(arg, i++);
    } else {
      throw new Error(`未知 query 参数: ${arg}`);
    }
  }

  // 把 --query 解析成内部 source（对外只剩一个 --query）：
  //   不传 或 -    → stdin（从管道读；- 是 Unix 惯用的"显式 stdin"）
  //   @<path>      → file
  //   其他         → inline（短纯 ASCII 单行 SQL，shell 会解析所以做护栏）
  let source;
  let sql = null;
  let sqlPath = null;
  if (query === null || query === '-') {
    source = 'stdin';
  } else if (query.startsWith('@')) {
    source = 'file';
    sqlPath = query.slice(1);
    if (!sqlPath) throw new Error('--query @ 后需提供文件路径');
  } else {
    source = 'inline';
    sql = query;
    if (!sql) throw new Error('--query 不能为空');
    if (/[\r\n]/.test(sql)) throw new Error('inline SQL 必须是单行');
    if (sql.length > 500) throw new Error('inline SQL 不能超过 500 个字符');
    if (/[^\x00-\x7F]|['"`$\\]/.test(sql)) {
      throw new Error('inline SQL 禁止包含非 ASCII 字符（如中文）或 Shell 特殊字符（单/双引号、$、反引号、反斜杠），请改用 --query @<文件> 或管道 stdin');
    }
  }

  return { source, sql, sqlPath, savePath };
}

export function readSqlFile(filePath) {
  let content;
  try {
    content = readFileSync(filePath, 'utf-8').trim();
  } catch (e) {
    throw new Error(`无法读取 SQL 文件 ${filePath}: ${e.message}`);
  }

  if (!content) {
    throw new Error(`SQL 文件为空: ${filePath}`);
  }

  return content;
}

export async function readSqlFromStdin(stream = process.stdin) {
  if (typeof stream.setEncoding === 'function') {
    stream.setEncoding('utf8');
  }

  let content = '';
  for await (const chunk of stream) {
    content += chunk;
  }

  content = content.trim();
  if (!content) {
    throw new Error('stdin 中的 SQL 为空');
  }

  return content;
}

export async function readSqlSource(options, stream = process.stdin) {
  if (options.source === 'stdin') return readSqlFromStdin(stream);
  if (options.source === 'file') return readSqlFile(options.sqlPath);

  const sql = options.sql.trim();
  if (!sql) throw new Error('inline SQL 为空');
  return sql;
}

export function resolveQueryOptions(options, cwd = process.cwd()) {
  const traceId = randomUUID();
  // JS 不再决定产物/scratch 去向：结果由 --save 指定（默认落 cwd/result-<trace>.json），
  // SQL 文件路径由 --sql-path 指定。.super-data-analytics/{results,scratch} 的布局约定见 SKILL.md，由 agent 构造路径。
  const savePath = options.savePath
    ? resolve(cwd, options.savePath)
    : join(cwd, `result-${traceId}.json`);
  const sqlPath = options.sqlPath ? resolve(cwd, options.sqlPath) : null;

  return { ...options, traceId, savePath, sqlPath };
}

export function createResultEnvelope({ traceId, source, resultPath, result }) {
  return {
    trace_id: traceId,
    source,
    result_path: resultPath,
    row_count: result.rows.length,
    columns: result.columns,
    rows: result.rows,
  };
}

export class HologresClient {
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

export async function saveResult(envelope, savePath) {
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
    let XLSX;
    try {
      XLSX = await import('xlsx');
    } catch {
      throw new Error('xlsx 格式需要安装 xlsx 依赖: npm install xlsx');
    }
    const { columns, rows } = envelope;
    const header = columns.map(c => c.name);
    const dataRows = rows.map(row => columns.map(c => row[c.name]));
    const ws = XLSX.utils.aoa_to_sheet([header, ...dataRows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
    XLSX.writeFile(wb, savePath);
  }
}

// CLI 入口
const [,, command, ...cliArgs] = process.argv;

if (command) {
  (async () => {
    let client;
    try {
      loadConfig();
      switch (command) {
        case 'test-connection': {
          client = new HologresClient();
          const result = await client.testConnection();
          console.log(JSON.stringify(result, null, 2));
          break;
        }
        case 'schema': {
          if (cliArgs.length === 0) {
            throw new Error('用法: node sql-query.js schema <schema.table> [schema.table ...]');
          }
          client = new HologresClient();
          const allRows = [];
          for (const arg of cliArgs) {
            const dotIndex = arg.indexOf('.');
            if (dotIndex === -1) {
              throw new Error(`参数格式错误: "${arg}"，应为 schema.table`);
            }
            const schemaName = arg.slice(0, dotIndex);
            const tableName = arg.slice(dotIndex + 1);
            const rows = await client.getTableSchema(tableName, schemaName);
            allRows.push({ schema: schemaName, table: tableName, columns: rows });
          }
          console.log(JSON.stringify(allRows, null, 2));
          break;
        }
        case 'query': {
          const options = resolveQueryOptions(parseQueryArgs(cliArgs));
          if (options.source === 'stdin' && process.stdin.isTTY) {
            throw new Error('未提供 --query 且 stdin 是终端（无管道输入）。请用 --query "<SQL>"、--query @<文件> 或通过管道传入 SQL');
          }
          const sql = await readSqlSource(options);
          client = new HologresClient();
          const result = await client.query(sql);
          const envelope = createResultEnvelope({
            traceId: options.traceId,
            source: options.source,
            resultPath: options.savePath,
            result,
          });

          await saveResult(envelope, options.savePath);
          console.error(`结果已保存到: ${options.savePath}`);
          console.log(JSON.stringify(envelope, null, 2));
          break;
        }
        default:
          throw new Error(
            `未知命令: ${command}\n\n` +
            '用法: node sql-query.js <命令> [参数]\n\n' +
            '命令:\n' +
            '  test-connection                              测试数据库连接\n' +
            '  schema <schema.table> [schema.table ...]     获取表结构\n' +
            '  query --query "<SQL>"                        直接执行短 SQL\n' +
            '  query --query @<文件>                         从文件读取 SQL\n' +
            '  query --query -                              从管道 stdin 读取 SQL（heredoc / 父进程 spawn 喂入）'
          );
      }
    } catch (err) {
      console.error(err.message);
      process.exitCode = 1;
    } finally {
      if (client) await client.close();
    }
  })();
}

export { SCHEMA_SQL_PATH, CONFIG_PATH };
