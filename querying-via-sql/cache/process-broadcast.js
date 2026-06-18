const fs = require('fs');
const data = JSON.parse(fs.readFileSync('C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\cache\\result-core.json', 'utf-8'));
const rows = data.rows;

// Get unique periods with agent_group
const periods = {};
for (const r of rows) {
  const key = r.period_display_name;
  if (!periods[key]) {
    periods[key] = {
      agent_group: r.agent_group,
      agent_desc: r.agent_desc,
      agent_target_recep: r.agent_target_recep,
      period_group_type: r.period_group_type,
      display_name: r.period_display_name,
      days: []
    };
  }
  periods[key].days.push({
    day_num: parseInt(r.day_num),
    progress: r.period_progress,
    sale_section: r.period_progress_sale_section,
    cur_progress: r.cur_period_progress,
    user_count: parseInt(r.user_count),
    recep_count: parseInt(r.recep_count),
    day_repurchase: parseInt(r.day_repurchase),
    day_revenue: parseFloat(r.day_revenue),
    cum_repurchase: parseInt(r.cum_repurchase),
    cum_revenue: parseFloat(r.cum_revenue),
    cum_live: parseInt(r.cum_live_repurchase),
    cum_group: parseInt(r.cum_group_repurchase),
  });
}

// Sort days
for (const p of Object.values(periods)) {
  p.days.sort((a, b) => a.day_num - b.day_num);
  p.latest = p.days[p.days.length - 1];
}

// Filter to agent periods only
const agentPeriods = Object.values(periods).filter(p => p.agent_group);
const historicalPeriods = Object.values(periods).filter(p => !p.agent_group);

console.log('=== AGENT PERIODS ===');
for (const p of agentPeriods) {
  console.log(`${p.display_name} (${p.period_group_type}) - ${p.latest.cur_progress}`);
  console.log(`  Days: ${p.days.length}, Users: ${p.latest.user_count}, Recep: ${p.latest.recep_count}`);
  console.log(`  Today: +${p.latest.day_repurchase} rep / ¥${p.latest.day_revenue}`);
  console.log(`  Cum: ${p.latest.cum_repurchase} rep / ¥${Math.round(p.latest.cum_revenue)}`);
  console.log(`  Live: ${p.latest.cum_live}, Group: ${p.latest.cum_group}`);
  console.log(`  Target ratio: ${p.agent_target_recep}`);
}

console.log('\n=== HISTORICAL PERIODS (same progress) ===');
// For each agent period, find historical periods at same progress
for (const ap of agentPeriods) {
  const targetProgress = ap.latest.progress;
  console.log(`\n--- ${ap.display_name} at ${targetProgress} ---`);
  const matches = historicalPeriods.filter(hp => {
    const day = hp.days.find(d => d.progress === targetProgress);
    return day;
  });
  for (const hp of matches) {
    const day = hp.days.find(d => d.progress === targetProgress);
    console.log(`  ${hp.display_name}: cum=${day.cum_repurchase} rep / ¥${Math.round(day.cum_revenue)}`);
  }
}

// Get user:recep ratio
console.log('\n=== EFFICIENCY METRICS ===');
for (const ap of agentPeriods) {
  const ratio = ap.latest.recep_count > 0 ? (ap.latest.user_count / ap.latest.recep_count).toFixed(1) : 'N/A';
  console.log(`${ap.display_name}: ${ap.latest.user_count}:${ap.latest.recep_count} = 1:${ratio} (target: ${ap.agent_target_recep})`);
}
