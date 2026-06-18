// Parse and generate broadcast for WeChat (plain text, no markdown tables)
const core = JSON.parse(require('fs').readFileSync('C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\cache\\result-core-20260614.json', 'utf8'));
const rows = core.rows;

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
  if (!agentPeriods[r.agent_period]) {
    agentPeriods[r.agent_period] = { desc: r.agent_desc, target_recep: r.agent_target_recep, periods: [] };
  }
  agentPeriods[r.agent_period].periods.push(r);
}

const byProgress = {};
for (const r of rows) {
  const pp = r.period_progress;
  if (!byProgress[pp]) byProgress[pp] = [];
  byProgress[pp].push(r);
}

const broadcastProgresses = [...new Set(broadcastRows.map(r => r.period_progress))];

let o = '';
o += '🤖 后端普拉提Agent效果验证播报\n\n';

o += '【本期能力】\n';
for (const [key, val] of Object.entries(agentPeriods)) {
  o += `▸ ${key}\n  ${val.desc}\n  目标人服比：${val.target_recep}\n`;
}
o += '\n';

o += `【播报时间】2026-06-14\n\n`;

o += '【实际期数进度】\n';
for (const [key, val] of Object.entries(agentPeriods)) {
  o += `${key}：\n`;
  for (const p of val.periods) {
    o += `  • ${p.period_name}（${p.period_group}）→ ${p.cur_period_progress}，销转日 ${p.sales_conversion_date}\n`;
  }
}
o += '\n';

for (const progress of broadcastProgresses) {
  const { agent2, agent1, history } = (() => {
    const data = byProgress[progress] || [];
    return {
      agent2: data.filter(r => r.agent_period === 'Agent第二期'),
      agent1: data.filter(r => r.agent_period === 'Agent第一期'),
      history: data.filter(r => r.period_group === '往期大盘')
    };
  })();

  o += '━━━━━━━━━━━━━━━━\n';
  o += `📌 对比节点：${progress}\n\n`;

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
    const status = target ? (ratio <= target ? '✅达标' : '⚠️超标') : '';
    o += `  ${r.period_name}（${r.period_group}）接待${fmt(r.accept_count)}人 / 人服${fmt(r.sale_after_count)}人 / 比值${ratio.toFixed(1)}${target ? ' / 目标' + r.agent_target_recep : ''} ${status}\n`;
  }
  o += '\n';

  const hasSales = agent2.some(r => r.period_progress_sale_section !== '非销转状态');
  if (hasSales) {
    o += '💡【本日销转】\n';
    for (const r of agent2) {
      o += `  ${r.period_name}（${r.period_group}）本日复购${fmt(r.repurchase_count)}人 / 金额${fmt(r.repurchase_revenue)}元\n`;
    }
    o += '\n⭐【累计销转】\n';
    for (const r of agent2) {
      o += `  ${r.period_name}（${r.period_group}）累计复购${fmt(r.cum_repurchase_count)}人（${pct(r.cum_repurchase_rate)}）/ 金额${fmt(r.cum_repurchase_revenue)}元\n`;
      o += `    正价${fmt(r.cum_main_rep_count)}人（${pct(r.cum_main_rep_rate)}）/ 回流${fmt(r.cum_back_rep_count)}人（${pct(r.cum_back_rep_rate)}）\n`;
    }
    o += '\n';
  } else {
    o += '💡【本日销转】各期数均未进入销转阶段，暂无数据\n';
    o += '⭐【累计销转】各期数均未进入销转阶段，暂无数据\n\n';
  }
}

// Agent第一期回顾
o += '━━━━━━━━━━━━━━━━\n';
o += '📈【过往实验期数 - Agent第一期】\n\n';
const a1Progress = broadcastProgresses[0];
const a1Data = (byProgress[a1Progress] || []).filter(r => r.agent_period === 'Agent第一期');
if (a1Data.length > 0) {
  for (const r of a1Data) {
    o += `  ${r.period_name}（${r.period_group}）接待${fmt(r.accept_count)}人 / 人服${fmt(r.sale_after_count)}人 / 累计复购${fmt(r.cum_repurchase_count)}人（${pct(r.cum_repurchase_rate)}）\n`;
  }
  o += '\n  ⚠️ Agent第一期已结营，数据仅供历史参考\n';
}

console.log(o);
