// Final broadcast generator with process metrics
const core = JSON.parse(require('fs').readFileSync('C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\cache\\result-core-20260614.json', 'utf8'));
const procRaw = require('child_process').execSync(
  'node "C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\scripts\\sql-query.js" query --file "C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\cache\\sql-query-proc4.sql"',
  { encoding: 'utf8', timeout: 60000 }
);
const proc = JSON.parse(procRaw);

const rows = core.rows;
const procRows = proc.rows;

function fmt(n) {
  if (n === null || n === undefined || n === '') return '-';
  const num = typeof n === 'string' ? parseFloat(n) : n;
  if (isNaN(num)) return '-';
  return Math.round(num).toLocaleString();
}
function pct(n) {
  if (n === null || n === undefined || n === '' || n === '0.0000' || n === 0) return '0%';
  const num = typeof n === 'string' ? parseFloat(n) : n;
  if (isNaN(num)) return '-';
  return (num * 100).toFixed(1) + '%';
}

const broadcastRows = rows.filter(r => r.is_broadcast === '是');
const agentPeriods = {};
for (const r of broadcastRows) {
  if (!agentPeriods[r.agent_period]) agentPeriods[r.agent_period] = { desc: r.agent_desc, target_recep: r.agent_target_recep, periods: [] };
  agentPeriods[r.agent_period].periods.push(r);
}

const byProgress = {};
for (const r of rows) {
  if (!byProgress[r.period_progress]) byProgress[r.period_progress] = [];
  byProgress[r.period_progress].push(r);
}

// Process data indexed by (period_name, metric)
const procIdx = {};
for (const r of procRows) {
  const key = `${r.period_name}|${r.metric}`;
  procIdx[key] = r;
}

const broadcastProgresses = [...new Set(broadcastRows.map(r => r.period_progress))];
let o = '';

o += '🤖 后端普拉提Agent效果验证播报\n\n';

o += '【本期能力】\n';
for (const [key, val] of Object.entries(agentPeriods)) {
  o += `▸ ${key}\n  ${val.desc}\n  目标人服比：${val.target_recep}\n`;
}
o += '\n';

o += '【播报时间】2026-06-14\n\n';

o += '【实际期数进度】\n';
for (const [key, val] of Object.entries(agentPeriods)) {
  o += `${key}：\n`;
  for (const p of val.periods) {
    o += `  • ${p.period_name}（${p.period_group}）→ ${p.cur_period_progress}，销转日 ${p.sales_conversion_date}\n`;
  }
}
o += '\n';

for (const progress of broadcastProgresses) {
  const data = byProgress[progress] || [];
  const agent2 = data.filter(r => r.agent_period === 'Agent第二期');
  const agent1 = data.filter(r => r.agent_period === 'Agent第一期');
  const history = data.filter(r => r.period_group === '往期大盘');

  o += '━━━━━━━━━━━━━━━━\n';
  o += `📌 对比节点：${progress}\n\n`;

  // 人服比
  o += '【人服比】\n';
  const all = [
    ...agent2.filter(r => r.period_group === '实验期数'),
    ...agent2.filter(r => r.period_group === '对照期数'),
    ...agent1.filter(r => r.period_group === '实验期数'),
    ...agent1.filter(r => r.period_group === '对照期数'),
    ...history
  ];
  for (const r of all) {
    const ratio = parseFloat(r.ratio_rs);
    const target = r.agent_target_recep ? parseInt(r.agent_target_recep.split(':')[1]) : null;
    const status = target ? (ratio <= target ? '✅' : '⚠️') : '';
    o += `  ${r.period_name}（${r.period_group}）接待${fmt(r.accept_count)} / 人服${fmt(r.sale_after_count)} / 比${ratio.toFixed(1)}${target ? '（目标' + r.agent_target_recep + '）' : ''} ${status}\n`;
  }
  o += '\n';

  // 销转
  const hasSales = agent2.some(r => r.period_progress_sale_section !== '非销转状态');
  if (hasSales) {
    o += '💡【本日销转】\n';
    for (const r of agent2) {
      o += `  ${r.period_name}（${r.period_group}）本日复购${fmt(r.repurchase_count)}人 / ¥${fmt(r.repurchase_revenue)}\n`;
    }
    o += '\n⭐【累计销转】\n';
    for (const r of agent2) {
      o += `  ${r.period_name}（${r.period_group}）累计${fmt(r.cum_repurchase_count)}人（${pct(r.cum_repurchase_rate)}）¥${fmt(r.cum_repurchase_revenue)}\n`;
      o += `    正价${fmt(r.cum_main_rep_count)}（${pct(r.cum_main_rep_rate)}）回流${fmt(r.cum_back_rep_count)}（${pct(r.cum_back_rep_rate)}）直播${fmt(r.cum_live_repurchase_count)}社群${fmt(r.cum_group_repurchase_count)}\n`;
    }
    o += '\n';
  } else {
    o += '💡【本日销转】各期数均未进入销转阶段，暂无数据\n';
    o += '⭐【累计销转】各期数均未进入销转阶段，暂无数据\n\n';
  }

  // 过程指标
  o += '📊【过程指标】\n';
  // Get the Agent第二期 period names for this progress
  const agent2Periods = agent2.map(r => r.period_name);
  const learnedPeriods = [];
  for (const pn of agent2Periods) {
    if (procIdx[`${pn}|learn`]) learnedPeriods.push(pn);
    if (procIdx[`${pn}|question`]) learnedPeriods.push(pn);
    if (procIdx[`${pn}|clock`]) learnedPeriods.push(pn);
  }
  const uniquePeriods = [...new Set(learnedPeriods)];

  for (const pn of uniquePeriods) {
    o += `  ▸ ${pn}\n`;

    const lr = procIdx[`${pn}|learn`];
    if (lr && lr.detail) {
      const entries = Object.entries(lr.detail);
      const avgRate = entries.reduce((s, e) => s + e[1], 0) / entries.length;
      // Show latest topic rates
      const latest3 = entries.slice(-3);
      o += `    完课率：均${(avgRate * 100).toFixed(1)}%（共${entries.length}课）\n`;
      for (const [name, rate] of latest3) {
        o += `      ${name.split('】').pop()} ${(rate * 100).toFixed(1)}%\n`;
      }
    }

    const qr = procIdx[`${pn}|question`];
    if (qr && qr.detail) {
      for (const [name, rate] of Object.entries(qr.detail)) {
        const shortName = name.replace('25天普拉提瘦身蜕变营-', '');
        o += `    问卷「${shortName}」提交率 ${(rate * 100).toFixed(1)}%\n`;
      }
    }

    const cr = procIdx[`${pn}|clock`];
    if (cr && cr.detail) {
      for (const [name, rate] of Object.entries(cr.detail)) {
        o += `    打卡「${name}」率 ${(rate * 100).toFixed(1)}%\n`;
      }
    }
    o += '\n';
  }
}

// Agent第一期回顾
o += '━━━━━━━━━━━━━━━━\n';
o += '📈【过往实验期数 - Agent第一期】\n\n';
const a1Progress = broadcastProgresses[0];
const a1Data = (byProgress[a1Progress] || []).filter(r => r.agent_period === 'Agent第一期');
for (const r of a1Data) {
  o += `  ${r.period_name}（${r.period_group}）接待${fmt(r.accept_count)} / 人服${fmt(r.sale_after_count)} / 累计复购${fmt(r.cum_repurchase_count)}人（${pct(r.cum_repurchase_rate)}）\n`;
}
o += '\n  ⚠️ Agent第一期已结营，数据仅供参考\n';

console.log(o);
