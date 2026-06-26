import { loadConfig, HologresClient, parseQueryArgs, resolveQueryOptions, readSqlSource, createResultEnvelope, saveResult } from './lib/sql.js';
import { PowerBIClient, parseDaxPayload, savePowerBiResult } from './lib/powerbi.js';

const SOURCES = new Set(['sql', 'powerbi']);

function parseGlobalArgs(args) {
  // 解析 --source，返回 { source, rest }
  let source = null;
  const rest = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--source') {
      source = args[++i];
      if (!source) throw new Error('--source 需要指定值：sql | powerbi');
    } else {
      rest.push(args[i]);
    }
  }
  if (!source) throw new Error('缺少 --source（sql | powerbi）');
  if (!SOURCES.has(source)) throw new Error(`不支持的 --source: ${source}（当前支持：${[...SOURCES].join(', ')}）`);
  return { source, rest };
}

async function runSql(command, cliArgs) {
  let client;
  try {
    switch (command) {
      case 'test-connection': {
        client = new HologresClient();
        console.log(JSON.stringify(await client.testConnection(), null, 2));
        break;
      }
      case 'schema': {
        if (cliArgs.length === 0) throw new Error('用法: query.js schema --source sql <schema.table> [schema.table ...]');
        client = new HologresClient();
        const allRows = [];
        for (const arg of cliArgs) {
          const dotIndex = arg.indexOf('.');
          if (dotIndex === -1) throw new Error(`参数格式错误: "${arg}"，应为 schema.table`);
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
          throw new Error('未提供 --query 且 stdin 是终端。请用 --query "<SQL>"、--query @<文件> 或管道传入');
        }
        const sql = await readSqlSource(options);
        client = new HologresClient();
        const result = await client.query(sql);
        const envelope = createResultEnvelope({ source: 'sql', resultPath: options.savePath, result });
        if (options.savePath) {
          await saveResult(envelope, options.savePath);
          console.error(`结果已保存到: ${options.savePath}`);
        }
        console.log(JSON.stringify(envelope, null, 2));
        break;
      }
      default:
        throw new Error(`sql 未知命令: ${command}（支持：test-connection / schema / query）`);
    }
  } finally {
    if (client) await client.close();
  }
}

async function runPowerBi(command, cliArgs) {
  const client = new PowerBIClient();
  switch (command) {
    case 'list-tools': {
      console.log(JSON.stringify(await client.listTools(), null, 2));
      break;
    }
    case 'test-connection': {
      const tools = await client.listTools();
      console.log(JSON.stringify({ ok: true, message: 'PowerBI MCP 连接成功', tool_count: tools.length }, null, 2));
      break;
    }
    case 'schema': {
      const [artifactId] = cliArgs;
      if (!artifactId) throw new Error('用法: query.js schema --source powerbi <artifactId>');
      console.log(JSON.stringify(await client.getSchema(artifactId), null, 2));
      break;
    }
    case 'query': {
      const options = resolveQueryOptions(parseQueryArgs(cliArgs));
      if (options.source === 'stdin' && process.stdin.isTTY) {
        throw new Error('未提供 --query 且 stdin 是终端。请用 --query <JSON>、--query @<文件> 或管道传入');
      }
      const text = await readSqlSource(options);
      const { artifactId, maxRows, daxQueries } = parseDaxPayload(text);
      const result = await client.query(artifactId, daxQueries, maxRows);
      const output = JSON.stringify(result, null, 2);
      if (options.savePath) {
        await savePowerBiResult(result, options.savePath);
        console.error(`结果已保存到: ${options.savePath}`);
      }
      console.log(output);
      break;
    }
    default:
      throw new Error(`powerbi 未知命令: ${command}（支持：list-tools / test-connection / schema / query）`);
  }
}

const [,, command, ...afterCommand] = process.argv;
if (!command) {
  console.error('用法: node query.js <命令> --source <sql|powerbi> [参数]');
  console.error('命令: test-connection / schema / query [/ powerbi 专属 list-tools]');
  process.exit(1);
}

(async () => {
  try {
    // 凭证统一在 dispatcher 主入口加载，sql / powerbi 共用
    loadConfig();
    const { source, rest } = parseGlobalArgs(afterCommand);
    if (source === 'sql') {
      await runSql(command, rest);
    } else if (source === 'powerbi') {
      await runPowerBi(command, rest);
    } else {
      throw new Error(`source "${source}" 尚未接入`);
    }
  } catch (err) {
    console.error(err.message);
    process.exitCode = 1;
  }
})();
