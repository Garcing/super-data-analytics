const fs = require('fs');
const data = JSON.parse(fs.readFileSync('C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\cache\\result-core.json', 'utf-8'));
const rows = data.rows;

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
for (const p of Object.values(periods)) {
  p.days.sort((a, b) => a.day_num - b.day_num);
  p.latest = p.days[p.days.length - 1];
}

const agentPeriods = Object.values(periods).filter(p => p.agent_group);
const historicalPeriods = Object.values(periods).filter(p => !p.agent_group);

function getHistoricalAvg(progress) {
  const matches = historicalPeriods.map(hp => {
    const day = hp.days.find(d => d.progress === progress);
    return day;
  }).filter(Boolean);
  if (matches.length === 0) return null;
  const avg = {
    count: matches.length,
    avg_rep: Math.round(matches.reduce((s, m) => s + m.cum_repurchase, 0) / matches.length),
    avg_rev: Math.round(matches.reduce((s, m) => s + m.cum_revenue, 0) / matches.length),
  };
  return avg;
}

function pct(current, baseline) {
  if (!baseline || baseline === 0) return current === 0 ? '-' : 'N/A';
  const diff = ((current - baseline) / baseline * 100).toFixed(1);
  const sign = diff >= 0 ? '+' : '';
  return `${sign}${diff}%`;
}

function formatRev(v) {
  if (v >= 10000) return `¥${(v / 10000).toFixed(1)}万`;
  return `¥${Math.round(v).toLocaleString()}`;
}

// Agent第二期 current periods (focus)
const phase2Periods = agentPeriods.filter(p => p.agent_group === 'Agent第二期');
const phase1Periods = agentPeriods.filter(p => p.agent_group === 'Agent第一期');

let md = `## 📊 后端普拉提 Agent效果验证播报\n`;
md += `> 数据截止：2026-06-14 | Agent第二期 · W2\n\n`;

// === Section 1: Agent第二期 进行中期数总览 ===
md += `### 一、Agent第二期 进行中期数总览\n\n`;

for (const ap of phase2Periods) {
  const ratio = ap.latest.recep_count > 0 ? (ap.latest.user_count / ap.latest.recep_count).toFixed(0) : '-';
  const target = ap.agent_target_recep ? ap.agent_target_recep.replace('1:', '') : '-';
  const ratioEmoji = ap.latest.recep_count > 0 && parseInt(target) > 0
    ? (parseInt(ratio) >= parseInt(target) ? '✅' : '⚠️')
    : '➖';
  
  md += `**${ap.display_name}** (${ap.period_group_type})\n`;
  md += `> 当前进度：${ap.latest.cur_progress} | 承接${ap.latest.user_count}人 | ${ap.latest.recep_count}位售后 | 人服比 1:${ratio} (目标1:${target}) ${ratioEmoji}\n\n`;
}

// === Section 2: 当日复购情况 ===
md += `### 二、当日复购情况\n\n`;
md += `| 期数 | 分组 | 进度 | 当日复购人数 | 当日流水 |\n`;
md += `|------|------|------|-------------|--------|\n`;

for (const ap of agentPeriods) {
  const shortName = ap.display_name.replace('蜕变', '').replace('26-', '');
  md += `| ${shortName} | ${ap.period_group_type} | ${ap.latest.cur_progress} | ${ap.latest.day_repurchase} | ${formatRev(ap.latest.day_revenue)} |\n`;
}

md += `\n`;

// === Section 3: 累计复购率对比 ===
md += `### 三、累计复购情况\n\n`;

for (const ap of agentPeriods) {
  const shortName = ap.display_name.replace('蜕变', '').replace('26-', '');
  const ratio = ap.latest.user_count > 0 ? (ap.latest.cum_repurchase / ap.latest.user_count * 100).toFixed(1) : '0.0';
  const baseline = getHistoricalAvg(ap.latest.progress);
  
  md += `**${shortName}** (${ap.period_group_type}) @ ${ap.latest.cur_progress}\n`;
  md += `- 累计复购：**${ap.latest.cum_repurchase}人** / ${formatRev(ap.latest.cum_revenue)} (复购率 ${ratio}%)\n`;
  if (baseline) {
    md += `- 同期大盘均值(${baseline.count}期)：${baseline.avg_rep}人 / ${formatRev(baseline.avg_rev)}`;
    if (baseline.avg_rep > 0) {
      const repDiff = ((ap.latest.cum_repurchase - baseline.avg_rep) / baseline.avg_rep * 100).toFixed(1);
      md += ` | 偏差 ${repDiff >= 0 ? '+' : ''}${repDiff}%`;
    }
    md += `\n`;
  }
  md += `\n`;
}

// === Section 4: Agent第一期 复盘 ===
md += `### 四、Agent第一期 复盘（已结营）\n\n`;
md += `| 期数 | 分组 | 结营状态 | 累计复购 | 累计流水 | 复购率 |\n`;
md += `|------|------|---------|---------|---------|--------|\n`;

for (const ap of phase1Periods) {
  const shortName = ap.display_name.replace('蜕变', '').replace('26-', '');
  const ratio = ap.latest.user_count > 0 ? (ap.latest.cum_repurchase / ap.latest.user_count * 100).toFixed(1) : '0.0';
  const baseline = getHistoricalAvg(ap.latest.progress);
  const baselineRep = baseline ? baseline.avg_rep : '-';
  md += `| ${shortName} | ${ap.period_group_type} | ${ap.latest.cur_progress} | ${ap.latest.cum_repurchase} | ${formatRev(ap.latest.cum_revenue)} | ${ratio}% |\n`;
}
md += `\n`;

// Agent 第一期 vs baseline
for (const ap of phase1Periods) {
  const baseline = getHistoricalAvg(ap.latest.progress);
  if (baseline) {
    const shortName = ap.display_name.replace('蜕变', '').replace('26-', '');
    const ratio = ap.latest.user_count > 0 ? (ap.latest.cum_repurchase / ap.latest.user_count * 100).toFixed(1) : '0.0';
    const blRatio = baseline.avg_rep > 0 ? (baseline.avg_rep / 379 * 100).toFixed(1) : '0.0'; // rough baseline rate
    md += `> **${shortName}**：vs同期大盘(${baseline.count}期均值${baseline.avg_rep}人) ${pct(ap.latest.cum_repurchase, baseline.avg_rep)}\n`;
  }
}

// === Section 5: 人效指标 ===
md += `\n### 五、人效指标\n\n`;
md += `| 期数 | 分组 | 人服比 | 目标人服比 | 状态 |\n`;
md += `|------|------|--------|-----------|------|\n`;

for (const ap of agentPeriods) {
  const shortName = ap.display_name.replace('蜕变', '').replace('26-', '');
  const ratio = ap.latest.recep_count > 0 ? (ap.latest.user_count / ap.latest.recep_count).toFixed(0) : '-';
  const target = ap.agent_target_recep ? ap.agent_target_recep.replace('1:', '') : '-';
  const status = ap.latest.recep_count > 0 && parseInt(target) > 0
    ? (parseInt(ratio) >= parseInt(target) ? '达标 ✅' : `偏离 ⚠️ (差${parseInt(target) - parseInt(ratio)}人/售后)`)
    : 'N/A';
  md += `| ${shortName} | ${ap.period_group_type} | 1:${ratio} | 1:${target} | ${status} |\n`;
}

console.log(md);
