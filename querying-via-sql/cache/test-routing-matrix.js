// querying-via-sql 路由测试（--query 精简版）
// 三种写法：--query "<SQL>" / --query @<文件> / 管道 stdin
// 外加参数校验、落盘格式、护栏。
// 全程固定在临时 work-dir 下执行，不污染技能源码树。
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { writeFileSync, existsSync, readFileSync, rmSync, mkdtempSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const SKILL_DIR = process.cwd();
const SCRIPT = join(SKILL_DIR, 'scripts', 'sql-query.js');
const WORK = mkdtempSync(join(tmpdir(), 'sda-test-'));

const results = [];
function record(name, expect, pass, detail = '') {
  results.push({ name, expect, pass, detail });
}

function run(args, opts = {}) {
  return spawnSync('node', [SCRIPT, ...args], { cwd: WORK, encoding: 'utf8', ...opts });
}

// ---------- A. --query @文件 ----------
{
  const sqlPath = join(WORK, 'query-a.sql');
  writeFileSync(sqlPath, 'SELECT 1 AS one;', 'utf8');
  const r = run(['query', '--query', `@${sqlPath}`]);
  let ok = false;
  try { ok = r.status === 0 && JSON.parse(r.stdout).source === 'file' && JSON.parse(r.stdout).row_count === 1; } catch {}
  record('A1 --query @文件', 'exit0 + source=file + 1 行', ok, `exit=${r.status}`);
}
{
  const r = run(['query', '--query', '@']);
  record('A2 --query @ 空路径拒绝', 'exit≠0 + 提示需提供路径',
    r.status !== 0 && /路径/.test(r.stderr), `exit=${r.status}`);
}

// ---------- B. --query 直接 SQL（inline 护栏）----------
{
  const r = run(['query', '--query', 'SELECT 7 AS seven']);
  let ok = false;
  try { ok = r.status === 0 && JSON.parse(r.stdout).row_count === 1; } catch {}
  record('B1 --query 短 SQL', 'exit0 + 1 行', ok, `exit=${r.status}`);
}
{
  const longSql = 'SELECT ' + 'a'.repeat(500) + ';';
  const r = run(['query', '--query', longSql]);
  record('B2 --query >500 字符拒绝', 'exit≠0 + 提示超长',
    r.status !== 0 && /500/.test(r.stderr), `exit=${r.status}`);
}
{
  const r = run(['query', '--query', 'SELECT 1\n;']);
  record('B3 --query 多行拒绝', 'exit≠0 + 提示单行',
    r.status !== 0 && /单行/.test(r.stderr), `exit=${r.status}`);
}
{
  const r = run(['query', '--query', `SELECT '中文' AS c`]);
  record('B4 --query 含中文被拒', 'exit≠0 + 提示禁止',
    r.status !== 0 && /禁止/.test(r.stderr), `exit=${r.status} :: ${r.stderr.trim().slice(0,60)}`);
}
{
  const r = run(['query', '--query', `SELECT '$x' AS c`]);
  record('B5 --query 含 $/引号被拒', 'exit≠0 + 提示禁止',
    r.status !== 0 && /禁止/.test(r.stderr), `exit=${r.status} :: ${r.stderr.trim().slice(0,60)}`);
}

// ---------- C. 管道 stdin ----------
{
  const r = spawnSync('bash', ['-c',
    `node "${SCRIPT}" query <<'EOF'
SELECT 'a$b\`c 中文' AS s, 100 AS n;
EOF`], { cwd: WORK, encoding: 'utf8' });
  let ok = false;
  try { ok = r.status === 0 && JSON.parse(r.stdout).source === 'stdin' && JSON.parse(r.stdout).row_count === 1; } catch {}
  record('C1 管道 heredoc 特殊字符', 'exit0 + source=stdin + 1 行，shell 未展开',
    ok, `exit=${r.status}`);
}
{
  // 管道空输入 → 报 SQL 为空
  const r = run(['query'], { input: '' });
  record('C2 管道空输入拒绝', 'exit≠0 + 提示 SQL 为空',
    r.status !== 0 && /为空/.test(r.stderr), `exit=${r.status}`);
}
{
  // --query - 显式 stdin，从管道读
  const r = run(['query', '--query', '-'], { input: 'SELECT 9 AS nine;' });
  let ok = false;
  try { ok = r.status === 0 && JSON.parse(r.stdout).source === 'stdin' && JSON.parse(r.stdout).row_count === 1; } catch {}
  record('C3 --query - 显式 stdin', 'exit0 + source=stdin + 1 行', ok, `exit=${r.status}`);
}

// ---------- D. 参数校验 ----------
{
  const cases = [
    ['D1 --source 已删',   ['query','--source','stdin'],                    /未知 query 参数/],
    ['D2 --sql 已删',      ['query','--sql','SELECT 1'],                    /未知 query 参数/],
    ['D3 --sql-path 已删', ['query','--sql-path','x'],                      /未知 query 参数/],
    ['D4 未知 flag',       ['query','--query','SELECT 1','--foo'],          /未知 query 参数/],
    ['D5 重复 --query',    ['query','--query','SELECT 1','--query','x'],    /重复参数/],
    ['D6 --save 缺值',     ['query','--query','SELECT 1','--save'],         /需要指定值/],
    ['D7 --query 缺值',    ['query','--query'],                             /需要指定值/],
    ['D8 --trace-id 已删', ['query','--query','SELECT 1','--trace-id','x'], /未知 query 参数/],
    ['D9 --query 空串',    ['query','--query',''],                          /不能为空/],
  ];
  for (const [name, args, re] of cases) {
    const r = run(args);
    const pass = r.status !== 0 && re.test(r.stderr);
    record(name, `exit≠0 + stderr 匹配 ${re}`, pass, `exit=${r.status} :: ${r.stderr.trim().slice(0,70)}`);
  }
}

// ---------- E. --save 落盘格式 ----------
{
  const save = join(WORK, 'test-save.csv');
  const r = run(['query','--query',`SELECT 1 AS n, 2 AS m`, '--save', save]);
  let ok = false;
  if (r.status === 0 && existsSync(save)) {
    const txt = readFileSync(save, 'utf8');
    ok = /n,m/.test(txt) && txt.includes('1,2');
  }
  record('E1 --save .csv', '写出含表头与数据', ok, `exit=${r.status} exists=${existsSync(save)}`);
}
{
  const save = join(WORK, 'test-save.txt');
  const r = run(['query','--query','SELECT 1','--save', save]);
  record('E2 --save .txt 拒绝', 'exit≠0 + 提示不支持格式',
    r.status !== 0 && /不支持.*格式|\.json.*\.csv.*\.xlsx/.test(r.stderr), `exit=${r.status}`);
}

// ---------- F. 落盘位置 ----------
{
  const before = readdirSync(WORK).filter(f => /^result-.*\.json$/.test(f)).length;
  const r = run(['query','--query','SELECT 42 AS n']);
  const after = readdirSync(WORK).filter(f => /^result-.*\.json$/.test(f)).length;
  let ok = false; let where = '';
  try { const env = JSON.parse(r.stdout); where = env.result_path || ''; ok = existsSync(where); } catch {}
  record('F1 不传 --save 默认落 cwd', 'cwd 下新增 result-*.json + 文件存在',
    r.status === 0 && after === before + 1 && ok, `exit=${r.status} where=${where}`);
}
{
  const save = join(WORK, 'nested', 'dir', 'out.json');
  const r = run(['query','--query','SELECT 99 AS n','--save', save]);
  record('F2 --save 深层路径自动建目录', 'exit0 + 文件存在',
    r.status === 0 && existsSync(save), `exit=${r.status} exists=${existsSync(save)}`);
}
{
  const sqlBefore = readdirSync(WORK).filter(f => f.endsWith('.sql')).length;
  run(['query'], { input: 'SELECT 5 AS n;' });
  const sqlAfter = readdirSync(WORK).filter(f => f.endsWith('.sql')).length;
  record('F3 stdin 不产生 SQL 文件', '工作区 .sql 数量不变',
    sqlAfter === sqlBefore, `sqlBefore=${sqlBefore} sqlAfter=${sqlAfter}`);
}

// ---------- 汇总 ----------
console.log('\n================ --query 路由测试汇总 ================');
console.log(`临时 work-dir: ${WORK}\n`);
let npass = 0;
for (const r of results) {
  const tag = r.pass === null ? '🔎' : (r.pass ? '✅' : '❌');
  if (r.pass) npass++;
  console.log(`${tag} ${r.name.padEnd(34)} | 期望: ${r.expect}`);
  if (r.detail) console.log(`     └─ ${r.detail}`);
}
const decided = results.filter(r => r.pass !== null);
console.log(`\n通过 ${npass}/${decided.length}`);

try { rmSync(WORK, { recursive: true, force: true }); } catch {}
