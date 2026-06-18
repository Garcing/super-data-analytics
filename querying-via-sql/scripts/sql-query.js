import {
  existsSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { join, dirname, isAbsolute, relative, resolve } from 'node:path';
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

const ROOT_DIR = dirname(__dirname);
const CACHE_DIR = join(ROOT_DIR, 'cache');
const SCHEMA_SQL_PATH = join(ROOT_DIR, 'references', 'get_table_schema.sql');

export function parseQueryArgs(args) {
  let filePath;
  let savePath = null;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--file') {
      filePath = args[++i];
      if (!filePath) {
        throw new Error('用法: node sql-query.js query --file <file_path> [--save <save_path>]');
      }
    } else if (arg === '--save') {
      savePath = args[++i];
      if (!savePath) {
        throw new Error('--save 需要指定保存路径');
      }
    } else {
      throw new Error(`未知 query 参数: ${arg}\n用法: node sql-query.js query --file <file_path> [--save <save_path>]`);
    }
  }

  if (!filePath) {
    throw new Error('用法: node sql-query.js query --file <file_path> [--save <save_path>]');
  }

  return { filePath, savePath };
}

function isTruthy(val) {
  if (!val) return false;
  return val.toLowerCase() !== 'false';
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
        `缺少环境变量: ${missing.join(', ')}\n\n` +
        '配置方法:\n' +
        '  在脚本同级目录（或上级目录）创建 .env 文件:\n' +
        '  HOLOGRES_HOST=xxx.hologres.aliyuncs.com\n' +
        '  HOLOGRES_PORT=80\n' +
        '  HOLOGRES_DATABASE=your_db\n' +
        '  HOLOGRES_USER=access_id\n' +
        '  HOLOGRES_PASSWORD=access_key'
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

export async function saveResult(result, savePath) {
  const ext = savePath.slice(savePath.lastIndexOf('.')).toLowerCase();

  if (ext === '.json') {
    writeFileSync(savePath, JSON.stringify(result, null, 2), 'utf-8');
  } else if (ext === '.csv') {
    const { columns, rows } = result;
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
    const { columns, rows } = result;
    const header = columns.map(c => c.name);
    const dataRows = rows.map(row => columns.map(c => row[c.name]));
    const ws = XLSX.utils.aoa_to_sheet([header, ...dataRows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
    XLSX.writeFile(wb, savePath);
  } else {
    throw new Error(`不支持的文件格式: ${ext}（支持 .json / .csv / .xlsx）`);
  }
}

// CLI 入口
const [,, command, ...cliArgs] = process.argv;

if (command) {
  (async () => {
    try {
      const client = new HologresClient();

      switch (command) {
        case 'test-connection': {
          const result = await client.testConnection();
          console.log(JSON.stringify(result, null, 2));
          await client.close();
          break;
        }
        case 'schema': {
          if (cliArgs.length === 0) {
            console.error('用法: node sql-query.js schema <schema.table> [schema.table ...]');
            process.exit(1);
          }
          const allRows = [];
          for (const arg of cliArgs) {
            const dotIndex = arg.indexOf('.');
            if (dotIndex === -1) {
              console.error(`参数格式错误: "${arg}"，应为 schema.table`);
              process.exit(1);
            }
            const schemaName = arg.slice(0, dotIndex);
            const tableName = arg.slice(dotIndex + 1);
            const rows = await client.getTableSchema(tableName, schemaName);
            allRows.push({ schema: schemaName, table: tableName, columns: rows });
          }
          console.log(JSON.stringify(allRows, null, 2));
          await client.close();
          break;
        }
        case 'query': {
          const { filePath, savePath } = parseQueryArgs(cliArgs);
          const sql = readSqlFile(filePath);
          const result = await client.query(sql);

          // KEEP_SQL_RESULT: 自动保存结果到 cache/（文件名 sql-query → result）
          if (isTruthy(process.env.KEEP_SQL_RESULT)) {
            const basename = filePath.replace(/\\/g, '/').split('/').pop();
            const resultName = basename.replace(/^sql-query-/, 'result-').replace(/\.sql$/, '.json');
            const resultPath = join(CACHE_DIR, resultName);
            writeFileSync(resultPath, JSON.stringify(result, null, 2), 'utf-8');
            console.error(`结果已缓存: ${resultPath}`);
          }

          if (savePath) {
            await saveResult(result, savePath);
            console.error(`结果已保存到: ${savePath}`);
          } else {
            console.log(JSON.stringify(result, null, 2));
          }

          // KEEP_SQL_FILE: 是否删除 SQL 缓存文件（默认 true = 保留）
          if (!isTruthy(process.env.KEEP_SQL_FILE) && existsSync(filePath)) {
            unlinkSync(filePath);
          }

          await client.close();
          break;
        }
        default:
          console.error(`未知命令: ${command}\n`);
          console.error('用法: node sql-query.js <命令> [参数]');
          console.error('');
          console.error('命令:');
          console.error('  test-connection              测试数据库连接');
          console.error('  schema <tableName>           获取表结构');
          console.error('  query --file <file_path>     从 SQL 文件读取并执行查询');
          process.exit(1);
      }
    } catch (err) {
      console.error(err.message);
      process.exit(1);
    }
  })();
}

export { CACHE_DIR, SCHEMA_SQL_PATH };
