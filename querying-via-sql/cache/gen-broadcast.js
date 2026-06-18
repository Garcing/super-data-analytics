// Parse core result and generate broadcast
const core = JSON.parse(require('fs').readFileSync('C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\cache\\result-core-20260614.json', 'utf8'));
const rows = core.rows;

// Group by period_progress
const byProgress = {};
for (const r of rows) {
  const pp = r.period_progress;
  if (!byProgress[pp]) byProgress[pp] = [];
  byProgress[pp].push(r);
}

// Broadcast periods (is_broadcast=是)
const broadcastRows = rows.filter(r => r.is_broadcast === '是');

// Agent periods info
const agentPeriods = {};
for (const r of broadcastRows) {
  if (!agentPeriods[r.agent_period]) {
    agentPeriods[r.agent_period] = {
      desc: r.agent_desc,
      target_recep: r.agent_target_recep,
      periods: []
    };
  }
  agentPeriods[r.agent_period].periods.push(r);
}

// Format number
function fmt(n, decimals = 0) {
  if (n === null || n === undefined || n === '') return '-';
  const num = typeof n === 'string' ? parseFloat(n) : n;
  if (isNaN(num)) return '-';
  if (decimals > 0) return num.toFixed(decimals);
  return Math.round(num).toLocaleString();
}

function pct(n) {
  if (n === null || n === undefined || n === '' || n === '0.0000' || n === '0') return '0%';
  const num = typeof n === 'string' ? parseFloat(n) : n;
  if (isNaN(num)) return '-';
  return (num * 100).toFixed(1) + '%';
}

// Get comparison data for each period_progress
function getComparisonData(progress) {
  const data = byProgress[progress] || [];
  const agent2 = data.filter(r => r.agent_period === 'Agent第二期');
  const agent1 = data.filter(r => r.agent_period === 'Agent第一期');
  const history = data.filter(r => r.period_group === '往期大盘');
  return { agent2, agent1, history };
}

// Build broadcast
const today = '2026-06-14';
let output = '';

output += '🤖 后端普拉提Agent效果验证播报\n\n';

// 本期能力
output += '【本期能力】\n';
for (const [key, val] of Object.entries(agentPeriods)) {
  output += `• ${key}：${val.desc}\n`;
  output += `  目标人服比：${val.target_recep}\n`;
}
output += '\n';

// 播报时间
output += `【播报时间】${today}\n\n`;

// 实际期数进度
output += '【实际期数进度】\n';
for (const [key, val] of Object.entries(agentPeriods)) {
  output += `${key}：\n`;
  for (const p of val.periods) {
    output += `  ${p.period_name}（${p.period_group}）当前进度：${p.cur_period_progress}，销转日：${p.sales_conversion_date}\n`;
  }
}
output += '\n';

// For each period_progress that has broadcast rows
const broadcastProgresses = [...new Set(broadcastRows.map(r => r.period_progress))];

for (const progress of broadcastProgresses) {
  const { agent2, agent1, history } = getComparisonData(progress);

  output += `━━━━━━━━━━━━━━━━\n`;
  output += `📌 对比节点：${progress}\n\n`;

  // 人服比
  output += '【人服比】\n';
  let table = '| 期数 | 期数分组 | 接待人数 | 人服数 | 实际人服比 | 目标人服比 | 状态 |\n';
  table += '| --- | --- | --- | --- | --- | --- | --- |\n';

  // Sort: Agent2实验 first, then Agent2对照, then Agent1实验, Agent1对照, then history
  const allRows = [
    ...agent2.filter(r => r.period_group === '实验期数'),
    ...agent2.filter(r => r.period_group === '对照期数'),
    ...agent1.filter(r => r.period_group === '实验期数'),
    ...agent1.filter(r => r.period_group === '对照期数'),
    ...history
  ];

  for (const r of allRows) {
    const ratio = parseFloat(r.ratio_rs);
    const target = r.agent_target_recep ? parseInt(r.agent_target_recep.split(':')[1]) : 120;
    const status = ratio <= target ? '✅达标' : '⚠️超标';
    table += `| ${r.period_name} | ${r.period_group} | ${fmt(r.accept_count)} | ${fmt(r.sale_after_count)} | ${ratio.toFixed(1)} | ${r.agent_target_recep || '-'} | ${status} |\n`;
  }
  output += table + '\n';

  // 销转 sections - only show if in sales phase
  const hasSalesPhase = agent2.some(r => r.period_progress_sale_section !== '非销转状态');
  if (hasSalesPhase) {
    // 本日销转
    output += '💡【本日销转】\n';
    let sTable = '| 期数 | 期数分组 | 本日复购人数 | 本日复购金额 | 累计复购人数 | 累计复购率 | 累计复购金额 |\n';
    sTable += '| --- | --- | --- | --- | --- | --- | --- |\n';
    for (const r of agent2) {
      sTable += `| ${r.period_name} | ${r.period_group} | ${fmt(r.repurchase_count)} | ${fmt(r.repurchase_revenue)} | ${fmt(r.cum_repurchase_count)} | ${pct(r.cum_repurchase_rate)} | ${fmt(r.cum_repurchase_revenue)} |\n`;
    }
    output += sTable + '\n';

    // 累计销转明细
    output += '⭐【累计销转明细】\n';
    let cTable = '| 期数 | 期数分组 | 累计正价 | 累计正价率 | 累计回流 | 累计回流率 | 直播间 | 社群 |\n';
    cTable += '| --- | --- | --- | --- | --- | --- | --- | --- |\n';
    for (const r of agent2) {
      cTable += `| ${r.period_name} | ${r.period_group} | ${fmt(r.cum_main_rep_count)} | ${pct(r.cum_main_rep_rate)} | ${fmt(r.cum_back_rep_count)} | ${pct(r.cum_back_rep_rate)} | ${fmt(r.cum_live_repurchase_count)} | ${fmt(r.cum_group_repurchase_count)} |\n`;
    }
    output += cTable + '\n';
  } else {
    output += '💡【本日销转】当前各期数均未进入销转阶段，暂无销转数据。\n\n';
    output += '⭐【累计销转】当前各期数均未进入销转阶段，暂无累计销转数据。\n\n';
  }
}

// 📈 过往实验期数
output += '━━━━━━━━━━━━━━━━\n';
output += '📈【过往实验期数 - Agent第一期 最终结果】\n\n';
const agent1All = rows.filter(r => r.agent_period === 'Agent第一期' && r.period_progress === '开营第09天');
output += 'Agent第一期（蜕变第十一期 vs 蜕变第11A期）当前对比：\n';
let hTable = '| 期数 | 期数分组 | 接待人数 | 累计复购人数 | 累计复购率 | 累计复购金额 | 实际人服比 |\n';
hTable += '| --- | --- | --- | --- | --- | --- | --- |\n';
for (const r of agent1All) {
  hTable += `| ${r.period_name} | ${r.period_group} | ${fmt(r.accept_count)} | ${fmt(r.cum_repurchase_count)} | ${pct(r.cum_repurchase_rate)} | ${fmt(r.cum_repurchase_revenue)} | ${parseFloat(r.ratio_rs).toFixed(1)} |\n`;
}
output += hTable + '\n';

output += '⚠️ 备注：Agent第一期各期数已结营，当前均为0复购（已超出结算范围），仅供历史参考。\n';

console.log(output);
