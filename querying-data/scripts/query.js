import { loadConfig, HologresClient, parseTextInputArgs, resolveQueryOptions, readTextSource, createResultEnvelope, saveResult } from './lib/sql.js';
import { PowerBIClient, parseDaxPayload, savePowerBiResult } from './lib/powerbi.js';

const SOURCES = new Set(['sql', 'powerbi']);

function parseArgv(argv) {
  const tokens = argv.slice(2);
  const [source, command, ...rest] = tokens;
  if (!source || !command) {
    throw new Error(
      '用法: node scripts/query.js <sql|powerbi> <命令> [参数]\n' +
      'SQL 命令: test-connection / schema / query\n' +
      'PowerBI 命令: list-tools / list-semantic-models / test-connection / schema / query'
    );
  }
  if (!SOURCES.has(source)) throw new Error(`不支持的数据源: ${source}（当前支持：${[...SOURCES].join(', ')}）`);
  return { source, command, rest };
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
        if (cliArgs.length === 0) throw new Error('用法: node scripts/query.js sql schema <schema.table> [schema.table ...]');
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
        const options = resolveQueryOptions(parseTextInputArgs(cliArgs, { inputFlag: '--sql', inputLabel: 'SQL' }));
        if (options.source === 'stdin' && process.stdin.isTTY) {
          throw new Error('未提供 --sql 且 stdin 是终端。请用 --sql "<SQL>"、--sql @<文件> 或管道传入');
        }
        const sql = await readTextSource(options, process.stdin, { label: 'SQL', inputFlag: '--sql' });
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

async function runPowerBi(command, cliArgs, config) {
  switch (command) {
    case 'list-semantic-models': {
      console.log(JSON.stringify({ 'powerbi-semantic-models': config['powerbi-semantic-models'] || [] }, null, 2));
      break;
    }
    case 'list-tools': {
      const client = new PowerBIClient();
      console.log(JSON.stringify(await client.listTools(), null, 2));
      break;
    }
    case 'test-connection': {
      const client = new PowerBIClient();
      const tools = await client.listTools();
      console.log(JSON.stringify({ ok: true, message: 'PowerBI MCP 连接成功', tool_count: tools.length }, null, 2));
      break;
    }
    case 'schema': {
      const client = new PowerBIClient();
      const [artifactId] = cliArgs;
      if (!artifactId) throw new Error('用法: node scripts/query.js powerbi schema <artifactId>');
      console.log(JSON.stringify(await client.getSchema(artifactId), null, 2));
      break;
    }
    case 'query': {
      const client = new PowerBIClient();
      const options = resolveQueryOptions(parseTextInputArgs(cliArgs, { inputFlag: '--payload', inputLabel: 'PowerBI payload' }));
      if (options.source === 'stdin' && process.stdin.isTTY) {
        throw new Error('未提供 --payload 且 stdin 是终端。请用 --payload <JSON>、--payload @<文件> 或管道传入');
      }
      const text = await readTextSource(options, process.stdin, { label: 'PowerBI payload', inputFlag: '--payload' });
      const payload = parseDaxPayload(text);
      const result = await client.query(payload.artifactId, payload.daxQueries, payload.maxRows);
      const output = JSON.stringify(result, null, 2);
      if (options.savePath) {
        await savePowerBiResult(result, options.savePath);
        console.error(`结果已保存到: ${options.savePath}`);
      }
      console.log(output);
      break;
    }
    default:
      throw new Error(`powerbi 未知命令: ${command}（支持：list-tools / list-semantic-models / test-connection / schema / query）`);
  }
}
(async () => {
  try {
    const { command, source, rest } = parseArgv(process.argv);
    // 凭证统一在 dispatcher 主入口加载，sql / powerbi 共用
    const config = loadConfig();
    if (source === 'sql') {
      await runSql(command, rest);
    } else if (source === 'powerbi') {
      await runPowerBi(command, rest, config);
    } else {
      throw new Error(`source "${source}" 尚未接入`);
    }
  } catch (err) {
    console.error(err.message);
    process.exitCode = 1;
  }
})();
