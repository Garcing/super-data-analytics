const fs = require('fs');
const data = JSON.parse(fs.readFileSync('cache/result-20260620-220000-pilates.json', 'utf-8'));

function parseDict(str) {
  if (!str) return {};
  const result = {};
  const start = str.indexOf('{'), end = str.lastIndexOf('}');
  if (start === -1 || end === -1) return {};
  const inner = str.substring(start + 1, end);
  const entries = [];
  let depth = 0, current = '';
  for (const ch of inner) {
    if (ch === '{') depth++;
    if (ch === '}') depth--;
    if (ch === ',' && depth === 0) { entries.push(current.trim()); current = ''; }
    else { current += ch; }
  }
  if (current.trim()) entries.push(current.trim());
  for (const entry of entries) {
    const ci = entry.lastIndexOf(':');
    if (ci === -1) continue;
    const key = entry.substring(0, ci).trim().replace(/^"/, '').replace(/"$/, '');
    const val = parseFloat(entry.substring(ci + 1).trim());
    result[key] = isNaN(val) ? 0 : val;
  }
  return result;
}

function fuzzyMatch(dict, pattern) {
  if (!pattern) return '-';
  if (dict[pattern] !== undefined) return (dict[pattern] * 100).toFixed(1) + '%';
  for (const k of Object.keys(dict)) {
    if (k.includes(pattern) || pattern.includes(k)) return (dict[k] * 100).toFixed(1) + '%';
  }
  return '-';
}

function fmtRate(v) { return v > 0 ? (v * 100).toFixed(2) + '%' : '-'; }
function fmtEff(v) { return v > 0 ? v.toString() : '-'; }
function fmtComp(e, c) {
  const d = e - c;
  if (Math.abs(d) < 0.0001) return '';
  return d > 0 ? ` 🟢+${(d*100).toFixed(2)}pp` : ` 🔴${(d*100).toFixed(2)}pp`;
}
function fmtCompN(e, c) {
  if (c === 0 || e === c) return '';
  return e > c ? ` 🟢+${e-c}` : ` 🔴${e-c}`;
}

// Table to text formatter for wecom
function tableToText(headers, rows) {
  // Calculate column widths
  const widths = headers.map((h, i) => {
    const maxRow = Math.max(...rows.map(r => String(r[i] || '-').length));
    return Math.max(h.length, maxRow);
  });
  let lines = [];
  // Header
  lines.push(headers.map((h, i) => h.padEnd(widths[i])).join(' | '));
  lines.push(widths.map(w => '-'.repeat(w)).join('-+-'));
  // Rows
  for (const row of rows) {
    lines.push(row.map((c, i) => String(c || '-').padEnd(widths[i])).join(' | '));
  }
  return lines.join('\n');
}

const allDetail = data.rows.filter(r => r['数据分组'] === '期数-明细');
const historicalAll = data.rows.filter(r => r['数据分组'] === '往期大盘-汇总');

const progressGroups = {};
allDetail.forEach(r => {
  const p = r['实际期数进度'];
  if (!progressGroups[p]) progressGroups[p] = [];
  progressGroups[p].push(r);
});

const broadcastExps = allDetail.filter(r => r['是否播报期数'] === '是' && r['期数分组'] === '实验期数');
const progressValues = [...new Set(broadcastExps.map(r => r['实际期数进度']))].sort();

const outputs = [];

for (const progress of progressValues) {
  const group = progressGroups[progress];
  const historical = historicalAll.find(h => h['实际期数进度'] === progress);
  const exps = broadcastExps.filter(e => e['实际期数进度'] === progress);
  const agentGroups = {};
  exps.forEach(e => {
    const a = e['Agent期数'];
    if (!agentGroups[a]) agentGroups[a] = [];
    agentGroups[a].push(e);
  });

  for (const [agentPeriod, agentExps] of Object.entries(agentGroups)) {
    for (const exp of agentExps) {
      const ctrl = group.find(r => r['期数分组'] === '对照期数' && r['Agent期数'] === agentPeriod);
      const pastExp = allDetail.find(r =>
        r['期数分组'] === '实验期数' && r['Agent期数'] === agentPeriod &&
        r['是否播报期数'] === '否' && r['实际期数进度'] === progress &&
        r['期数名称'] !== exp['期数名称']
      );
      const hist = historical;
      const saleSection = exp['期数销转区间'];
      const isSaleActive = saleSection !== '非销转状态';

      const expCourseDict = parseDict(exp['完课率字典']);
      const ctrlCourseDict = ctrl ? parseDict(ctrl['完课率字典']) : {};
      const pastCourseDict = pastExp ? parseDict(pastExp['完课率字典']) : {};
      const histCourseDict = hist ? parseDict(hist['完课率字典']) : {};

      const expSurveyDict = parseDict(exp['问卷提交率字典']);
      const ctrlSurveyDict = ctrl ? parseDict(ctrl['问卷提交率字典']) : {};
      const pastSurveyDict = pastExp ? parseDict(pastExp['问卷提交率字典']) : {};
      const histSurveyDict = hist ? parseDict(hist['问卷提交率字典']) : {};

      const expClockDict = parseDict(exp['打卡率字典']);
      const ctrlClockDict = ctrl ? parseDict(ctrl['打卡率字典']) : {};
      const pastClockDict = pastExp ? parseDict(pastExp['打卡率字典']) : {};
      const histClockDict = hist ? parseDict(hist['打卡率字典']) : {};

      const latestCourses = Object.keys(expCourseDict).slice(-3);
      const expSurveyKeys = Object.keys(expSurveyDict);
      const latestSurvey = expSurveyKeys[expSurveyKeys.length - 1] || null;
      const expClockKeys = Object.keys(expClockDict);
      const latestClock = expClockKeys[expClockKeys.length - 1] || null;

      let o = '';
      o += `🤖普拉提${agentPeriod}数据播报\n\n`;
      o += `【本期能力】${exp['Agent描述']}\n`;
      o += `【播报时间】2026-06-21 10:00:00\n`;
      o += `【实际期数进度】${progress}\n`;
      
      const targetRatio = exp['Agent目标人服比'] || '-';
      const actualRatio = parseInt(exp['人服比']) || 0;
      const targetNum = parseInt(targetRatio.toString().replace('1:', '')) || 0;
      const diff = actualRatio - targetNum;
      o += `【人服比】目标${targetRatio}，实际${actualRatio}，差距${diff >= 0 ? '+' : ''}${diff}\n`;
      o += `【往期大盘期数】${hist ? hist['期数名称'] : '-'}\n`;

      // 💡本日销转
      if (isSaleActive) {
        const expDailyRate = parseInt(exp['承接人数']) > 0 ? parseInt(exp['复购人数']) / parseInt(exp['承接人数']) : 0;
        const ctrlDailyRate = ctrl && parseInt(ctrl['承接人数']) > 0 ? parseInt(ctrl['复购人数']) / parseInt(ctrl['承接人数']) : 0;
        o += `\n💡本日销转\n`;
        o += `┌──────────┬────────────────────┬────────┬────────┬────────┐\n`;
        o += `│ 期数分组 │ 期数名称            │ 复购人数│ 复购流水│ 复购率  │\n`;
        o += `├──────────┼────────────────────┼────────┼────────┼────────┤\n`;
        o += `│ 实验期数 │ ${exp['期数名称'].padEnd(18)}│ ${String(exp['复购人数']).padEnd(6)}│ ${String(exp['复购流水']).padEnd(6)}│ ${(expDailyRate*100).toFixed(2).padEnd(6)}%${fmtComp(expDailyRate, ctrlDailyRate).padEnd(2)} │\n`;
        if (ctrl) {
          o += `│ 对照期数 │ ${ctrl['期数名称'].padEnd(18)}│ ${String(ctrl['复购人数']).padEnd(6)}│ ${String(ctrl['复购流水']).padEnd(6)}│ ${(ctrlDailyRate*100).toFixed(2).padEnd(6)}%      │\n`;
        }
        o += `└──────────┴────────────────────┴────────┴────────┴────────┘\n`;
      }

      // ⭐累计销转
      o += `\n⭐累计销转\n`;
      const expCumRate = parseFloat(exp['累计复购率']) || 0;
      const ctrlCumRate = ctrl ? parseFloat(ctrl['累计复购率']) || 0 : 0;
      const expEff = parseInt(exp['人效']) || 0;
      const ctrlEff = ctrl ? parseInt(ctrl['人效']) || 0 : 0;
      
      const cumHeaders = ['期数分组', '期数名称', '累计复购率', '累计直播间', '累计社群', '人效'];
      const buildCumRow = (label, name, cumR, liveR, groupR, eff, compR, compN) => {
        const r = `${(cumR ? fmtRate(parseFloat(cumR)) : '-').padEnd(8)}`;
        const c = compR !== undefined ? fmtComp(parseFloat(cumR) || 0, parseFloat(compR) || 0) : '';
        const e = `${(eff ? fmtEff(eff) : '-').padEnd(6)}`;
        const cn = compN !== undefined ? fmtCompN(eff || 0, compN || 0) : '';
        return [label, name, r + c, fmtRate(parseFloat(liveR) || 0), fmtRate(parseFloat(groupR) || 0), e + cn];
      };
      
      const cumRows = [
        buildCumRow('实验期数', exp['期数名称'], expCumRate, exp['累计直播间复购率'], exp['累计社群复购率'], expEff, ctrl ? ctrlCumRate : undefined, ctrl ? ctrlEff : undefined),
      ];
      if (ctrl) cumRows.push(buildCumRow('对照期数', ctrl['期数名称'], ctrlCumRate, ctrl['累计直播间复购率'], ctrl['累计社群复购率'], ctrlEff));
      if (pastExp) cumRows.push(buildCumRow('过往实验', pastExp['期数名称'], pastExp['累计复购率'], pastExp['累计直播间复购率'], pastExp['累计社群复购率'], parseInt(pastExp['人效']) || 0));
      if (hist) cumRows.push(buildCumRow('往期大盘', hist['期数名称'] || '', hist['累计复购率'], hist['累计直播间复购率'], hist['累计社群复购率'], parseInt(hist['人效']) || 0));
      
      o += tableToText(cumHeaders, cumRows) + '\n';

      // 🔎过程指标
      o += `\n🔎过程指标\n`;
      const procHeaders = ['期数分组', '期数名称', ...latestCourses.map(c => { const m = c.match(/【[^】]+】(.+)/); return m ? m[1] : c; })];
      if (latestSurvey) procHeaders.push(latestSurvey.replace(/25天普拉提瘦身蜕变营-/, ''));
      if (latestClock) procHeaders.push(latestClock.replace(/第\d+[AB]?期-/, ''));
      
      const buildProcRow = (label, name, courseD, surveyD, clockD) => {
        const vals = latestCourses.map(c => {
          if (courseD[c] !== undefined) return (courseD[c]*100).toFixed(1) + '%';
          return fuzzyMatch(courseD, c);
        });
        if (latestSurvey) vals.push(surveyD ? fuzzyMatch(surveyD, latestSurvey) : '-');
        if (latestClock) vals.push(clockD ? fuzzyMatch(clockD, latestClock) : '-');
        return [label, name, ...vals];
      };
      
      const procRows = [
        buildProcRow('实验期数', exp['期数名称'], expCourseDict, expSurveyDict, expClockDict),
      ];
      if (ctrl) procRows.push(buildProcRow('对照期数', ctrl['期数名称'], ctrlCourseDict, ctrlSurveyDict, ctrlClockDict));
      if (pastExp) procRows.push(buildProcRow('过往实验', pastExp['期数名称'], pastCourseDict, pastSurveyDict, pastClockDict));
      if (hist) procRows.push(buildProcRow('往期大盘', hist['期数名称'] || '', histCourseDict, histSurveyDict, histClockDict));
      
      o += tableToText(procHeaders, procRows) + '\n';

      // 核心结论
      o += `\n【核心结论】\n`;
      const conclusions = [];
      if (targetNum > 0) {
        if (actualRatio >= targetNum) conclusions.push(`▸ 人服比${actualRatio}已达到目标${targetRatio}，达成预期`);
        else conclusions.push(`▸ 人服比${actualRatio}，距离目标${targetRatio}还差${targetNum - actualRatio}`);
      }
      if (ctrl) {
        if (expCumRate > ctrlCumRate) conclusions.push(`▸ 实验期数累计复购率${(expCumRate*100).toFixed(2)}%，高于对照期数${(ctrlCumRate*100).toFixed(2)}%`);
        else if (expCumRate === ctrlCumRate && expCumRate === 0) conclusions.push(`▸ 实验期数和对照期数累计复购率均为0，当前尚在服务期`);
        else if (expCumRate < ctrlCumRate && ctrlCumRate > 0) conclusions.push(`▸ 实验期数累计复购率${(expCumRate*100).toFixed(2)}%，低于对照期数${(ctrlCumRate*100).toFixed(2)}%`);
      }
      const expRepNum = parseInt(exp['累计复购人数']) || 0;
      const expRepFlow = parseInt(exp['累计复购流水']) || 0;
      if (expRepNum > 0) {
        const source = (parseFloat(exp['累计社群复购率']) || 0) > 0 ? '社群跟单' : (parseFloat(exp['累计直播间复购率']) || 0) > 0 ? '直播间成单' : '其他';
        conclusions.push(`▸ 已有${expRepNum}人复购（累计流水¥${expRepFlow}），复购来源为${source}`);
      }
      if (latestCourses.length > 0) {
        const lc = latestCourses[latestCourses.length - 1];
        conclusions.push(`▸ 最新单课「${lc}」完课率${(expCourseDict[lc] * 100).toFixed(1)}%`);
      }
      if (conclusions.length === 0) conclusions.push('▸ 当前数据暂无显著差异，持续观察中');
      o += conclusions.join('\n');

      outputs.push(o);
    }
  }
}

console.log(outputs.join('\n\n═══════════════════════════════════\n\n'));
