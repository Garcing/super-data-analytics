const fs = require('fs');
const data = JSON.parse(fs.readFileSync('cache/result-20260620-220000-pilates.json', 'utf-8'));

// Helper: parse dict string
function parseDict(str) {
  if (!str) return {};
  const result = {};
  const start = str.indexOf('{');
  const end = str.lastIndexOf('}');
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
    const colonIdx = entry.lastIndexOf(':');
    if (colonIdx === -1) continue;
    const key = entry.substring(0, colonIdx).trim().replace(/^"/, '').replace(/"$/, '');
    const val = parseFloat(entry.substring(colonIdx + 1).trim());
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

function formatCompare(expVal, ctrlVal) {
  const diff = expVal - ctrlVal;
  if (Math.abs(diff) < 0.0001) return '-';
  return (diff > 0 ? '🟢+' : '🔴') + (diff * 100).toFixed(2) + 'pp';
}

function formatCompareNum(expVal, ctrlVal) {
  if (ctrlVal === 0) return '-';
  const diff = expVal - ctrlVal;
  if (diff === 0) return '-';
  return (diff > 0 ? '🟢+' : '🔴') + diff;
}

function fmtRate(v) { return v > 0 ? (v * 100).toFixed(2) + '%' : '-'; }
function fmtEff(v) { return v > 0 ? v.toString() : '-'; }

// === Main ===
const allDetail = data.rows.filter(r => r['数据分组'] === '期数-明细');
const historicalAll = data.rows.filter(r => r['数据分组'] === '往期大盘-汇总');

// Group by 实际期数进度
const progressGroups = {};
allDetail.forEach(r => {
  const p = r['实际期数进度'];
  if (!progressGroups[p]) progressGroups[p] = [];
  progressGroups[p].push(r);
});

// Get unique progress values from broadcast periods, sorted
const broadcastExps = allDetail.filter(r => r['是否播报期数'] === '是' && r['期数分组'] === '实验期数');
const progressValues = [...new Set(broadcastExps.map(r => r['实际期数进度']))].sort();

const outputs = [];

for (const progress of progressValues) {
  const group = progressGroups[progress];
  const historical = historicalAll.find(h => h['实际期数进度'] === progress);
  
  // Find ALL experiment periods in this progress group that need broadcasting
  const exps = broadcastExps.filter(e => e['实际期数进度'] === progress);
  
  // Group experiments by Agent期数
  const agentGroups = {};
  exps.forEach(e => {
    const a = e['Agent期数'];
    if (!agentGroups[a]) agentGroups[a] = [];
    agentGroups[a].push(e);
  });
  
  for (const [agentPeriod, agentExps] of Object.entries(agentGroups)) {
    for (const exp of agentExps) {
      // Find matching control (same agent period, 对照期数, same progress)
      const ctrl = group.find(r => r['期数分组'] === '对照期数' && r['Agent期数'] === agentPeriod);
      
      // Find past experiment: 实验期数 with 是否播报期数=否, same agent period, same progress
      const pastExp = allDetail.find(r => 
        r['期数分组'] === '实验期数' && r['Agent期数'] === agentPeriod && 
        r['是否播报期数'] === '否' && r['实际期数进度'] === progress &&
        r['期数名称'] !== exp['期数名称']
      );
      
      const hist = historical;
      const saleSection = exp['期数销转区间'];
      const isSaleActive = saleSection !== '非销转状态';
      
      // Parse dicts
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
      
      // Latest 3 courses
      const expCourseKeys = Object.keys(expCourseDict);
      const latestCourses = expCourseKeys.slice(-3);
      
      const expSurveyKeys = Object.keys(expSurveyDict);
      const latestSurvey = expSurveyKeys[expSurveyKeys.length - 1] || null;
      
      const expClockKeys = Object.keys(expClockDict);
      const latestClock = expClockKeys[expClockKeys.length - 1] || null;
      
      let o = '';
      o += `🤖普拉提${agentPeriod}数据播报\n\n`;
      o += `【本期能力】${exp['Agent描述']}\n\n`;
      o += `【播报时间】2026-06-21 10:00:00\n\n`;
      o += `【实际期数进度】${progress}\n\n`;
      
      const targetRatio = exp['Agent目标人服比'] || '-';
      const actualRatio = parseInt(exp['人服比']) || 0;
      const targetNum = parseInt(targetRatio.toString().replace('1:', '')) || 0;
      const diff = actualRatio - targetNum;
      o += `【人服比】目标${targetRatio}，实际${actualRatio}，差距${diff >= 0 ? '+' : ''}${diff}\n\n`;
      o += `【往期大盘期数】${hist ? hist['期数名称'] : '-'}\n`;
      
      // 💡本日销转 - only when sale is active
      if (isSaleActive) {
        const expDailyRate = parseInt(exp['承接人数']) > 0 ? parseInt(exp['复购人数']) / parseInt(exp['承接人数']) : 0;
        const ctrlDailyRate = ctrl && parseInt(ctrl['承接人数']) > 0 ? parseInt(ctrl['复购人数']) / parseInt(ctrl['承接人数']) : 0;
        
        o += `\n💡本日销转\n\n`;
        o += `| 期数分组 | 期数名称 | 本日复购人数 | 本日复购流水 | 本日复购率 |\n`;
        o += `|-|-|-|-|-|\n`;
        const expComp = formatCompare(expDailyRate, ctrlDailyRate);
        o += `| 实验期数 | ${exp['期数名称']} | ${exp['复购人数']} | ${exp['复购流水']} | ${(expDailyRate * 100).toFixed(2)}%${expComp !== '-' ? ' (' + expComp + ')' : ''} |\n`;
        if (ctrl) {
          o += `| 对照期数 | ${ctrl['期数名称']} | ${ctrl['复购人数']} | ${ctrl['复购流水']} | ${(ctrlDailyRate * 100).toFixed(2)}% |\n`;
        }
      }
      
      // ⭐累计销转
      o += `\n⭐累计销转\n\n`;
      
      let cumHeader = '| 期数分组 | 期数名称 | 累计复购率 | 累计直播间复购率 | 累计社群复购率';
      let cumSep = '|-|-|-|-|-';
      
      const showPreSale = ['前置期', '结营日', 'T+10'].includes(saleSection);
      const showEndDay = ['结营日', 'T+10'].includes(saleSection);
      const showT10 = saleSection === 'T+10';
      
      if (showPreSale) { cumHeader += ' | 累计前置期复购率'; cumSep += '|-'; }
      if (showEndDay) { cumHeader += ' | 累计结营日复购率'; cumSep += '|-'; }
      if (showT10) { cumHeader += ' | 累计T+10复购率'; cumSep += '|-'; }
      
      cumHeader += ' | 人效';
      cumSep += '|-';
      
      o += cumHeader + '\n' + cumSep + '\n';
      
      const expCumRate = parseFloat(exp['累计复购率']) || 0;
      const ctrlCumRate = ctrl ? parseFloat(ctrl['累计复购率']) || 0 : 0;
      const expEff = parseInt(exp['人效']) || 0;
      const ctrlEff = ctrl ? parseInt(ctrl['人效']) || 0 : 0;
      
      // Exp row
      let expLine = `| 实验期数 | ${exp['期数名称']} | ${fmtRate(expCumRate)}`;
      const cumComp = ctrl ? formatCompare(expCumRate, ctrlCumRate) : '-';
      if (cumComp !== '-') expLine += ` (${cumComp})`;
      expLine += ` | ${fmtRate(parseFloat(exp['累计直播间复购率']) || 0)} | ${fmtRate(parseFloat(exp['累计社群复购率']) || 0)}`;
      if (showPreSale) expLine += ` | ${fmtRate(parseFloat(exp['累计前置期复购率']) || 0)}`;
      if (showEndDay) expLine += ` | ${fmtRate(parseFloat(exp['累计结营日复购率']) || 0)}`;
      if (showT10) expLine += ` | ${fmtRate(parseFloat(exp['累计T+10复购率']) || 0)}`;
      expLine += ` | ${fmtEff(expEff)}`;
      const effComp = ctrl ? formatCompareNum(expEff, ctrlEff) : '-';
      if (effComp !== '-') expLine += ` (${effComp})`;
      expLine += ' |';
      o += expLine + '\n';
      
      // Control row
      if (ctrl) {
        let ctrlLine = `| 对照期数 | ${ctrl['期数名称']} | ${fmtRate(ctrlCumRate)} | ${fmtRate(parseFloat(ctrl['累计直播间复购率']) || 0)} | ${fmtRate(parseFloat(ctrl['累计社群复购率']) || 0)}`;
        if (showPreSale) ctrlLine += ` | ${fmtRate(parseFloat(ctrl['累计前置期复购率']) || 0)}`;
        if (showEndDay) ctrlLine += ` | ${fmtRate(parseFloat(ctrl['累计结营日复购率']) || 0)}`;
        if (showT10) ctrlLine += ` | ${fmtRate(parseFloat(ctrl['累计T+10复购率']) || 0)}`;
        ctrlLine += ` | ${fmtEff(ctrlEff)} |`;
        o += ctrlLine + '\n';
      }
      
      // Past experiment row
      if (pastExp) {
        let pastLine = `| 过往实验期数 | ${pastExp['期数名称']} | ${fmtRate(parseFloat(pastExp['累计复购率']) || 0)} | ${fmtRate(parseFloat(pastExp['累计直播间复购率']) || 0)} | ${fmtRate(parseFloat(pastExp['累计社群复购率']) || 0)}`;
        if (showPreSale) pastLine += ` | ${fmtRate(parseFloat(pastExp['累计前置期复购率']) || 0)}`;
        if (showEndDay) pastLine += ` | ${fmtRate(parseFloat(pastExp['累计结营日复购率']) || 0)}`;
        if (showT10) pastLine += ` | ${fmtRate(parseFloat(pastExp['累计T+10复购率']) || 0)}`;
        pastLine += ` | ${fmtEff(parseInt(pastExp['人效']) || 0)} |`;
        o += pastLine + '\n';
      }
      
      // Historical row
      if (hist) {
        let histLine = `| 往期大盘 | ${hist['期数名称']} | ${fmtRate(parseFloat(hist['累计复购率']) || 0)} | ${fmtRate(parseFloat(hist['累计直播间复购率']) || 0)} | ${fmtRate(parseFloat(hist['累计社群复购率']) || 0)}`;
        if (showPreSale) histLine += ` | ${fmtRate(parseFloat(hist['累计前置期复购率']) || 0)}`;
        if (showEndDay) histLine += ` | ${fmtRate(parseFloat(hist['累计结营日复购率']) || 0)}`;
        if (showT10) histLine += ` | ${fmtRate(parseFloat(hist['累计T+10复购率']) || 0)}`;
        histLine += ` | ${fmtEff(parseInt(hist['人效']) || 0)} |`;
        o += histLine + '\n';
      }
      
      // 🔎过程指标
      o += `\n🔎过程指标\n\n`;
      let procHeader = '| 期数分组 | 期数名称';
      let procSep = '|-|-';
      const courseShortNames = latestCourses.map(c => {
        const m = c.match(/【[^】]+】(.+)/);
        return m ? m[1] : c;
      });
      for (const c of courseShortNames) { procHeader += ` | ${c}`; procSep += '|-'; }
      if (latestSurvey) {
        const s = latestSurvey.replace(/25天普拉提瘦身蜕变营-/, '');
        procHeader += ` | ${s}`; procSep += '|-';
      }
      if (latestClock) {
        const c = latestClock.replace(/第\d+[AB]?期-/, '');
        procHeader += ` | ${c}`; procSep += '|-';
      }
      o += procHeader + '\n' + procSep + '\n';
      
      // Exp
      let pExp = `| 实验期数 | ${exp['期数名称']}`;
      for (const c of latestCourses) pExp += ` | ${(expCourseDict[c] * 100).toFixed(1)}%`;
      if (latestSurvey) pExp += ` | ${(expSurveyDict[latestSurvey] * 100).toFixed(1)}%`;
      if (latestClock) pExp += ` | ${(expClockDict[latestClock] * 100).toFixed(1)}%`;
      o += pExp + '\n';
      
      // Control
      if (ctrl) {
        let pCtrl = `| 对照期数 | ${ctrl['期数名称']}`;
        for (const c of latestCourses) pCtrl += ` | ${fuzzyMatch(ctrlCourseDict, c)}`;
        if (latestSurvey) pCtrl += ` | ${fuzzyMatch(ctrlSurveyDict, latestSurvey)}`;
        if (latestClock) pCtrl += ` | ${fuzzyMatch(ctrlClockDict, latestClock)}`;
        o += pCtrl + '\n';
      }
      
      // Past exp
      if (pastExp) {
        let pPast = `| 过往实验期数 | ${pastExp['期数名称']}`;
        for (const c of latestCourses) pPast += ` | ${fuzzyMatch(pastCourseDict, c)}`;
        if (latestSurvey) pPast += ` | ${fuzzyMatch(pastSurveyDict, latestSurvey)}`;
        if (latestClock) pPast += ` | ${fuzzyMatch(pastClockDict, latestClock)}`;
        o += pPast + '\n';
      }
      
      // Historical
      if (hist) {
        let pHist = `| 往期大盘 | ${hist['期数名称']}`;
        for (const c of latestCourses) pHist += ` | ${fuzzyMatch(histCourseDict, c)}`;
        if (latestSurvey) pHist += ` | ${fuzzyMatch(histSurveyDict, latestSurvey)}`;
        if (latestClock) pHist += ` | ${fuzzyMatch(histClockDict, latestClock)}`;
        o += pHist + '\n';
      }
      
      // 核心结论
      o += `\n【核心结论】\n\n`;
      const conclusions = [];
      
      if (targetNum > 0) {
        if (actualRatio >= targetNum) conclusions.push(`人服比${actualRatio}已达到目标${targetRatio}，达成预期。`);
        else conclusions.push(`人服比${actualRatio}，距离目标${targetRatio}还差${targetNum - actualRatio}。`);
      }
      
      if (ctrl) {
        if (expCumRate > ctrlCumRate) {
          conclusions.push(`实验期数累计复购率${(expCumRate*100).toFixed(2)}%，高于对照期数${(ctrlCumRate*100).toFixed(2)}%。`);
        } else if (expCumRate === ctrlCumRate && expCumRate === 0) {
          conclusions.push(`实验期数和对照期数累计复购率均为0，当前尚在服务期，暂未进入销转。`);
        } else if (expCumRate < ctrlCumRate && ctrlCumRate > 0) {
          conclusions.push(`实验期数累计复购率${(expCumRate*100).toFixed(2)}%，低于对照期数${(ctrlCumRate*100).toFixed(2)}%。`);
        }
      }
      
      const expRepNum = parseInt(exp['累计复购人数']) || 0;
      const expRepFlow = parseInt(exp['累计复购流水']) || 0;
      if (expRepNum > 0) {
        const source = (parseFloat(exp['累计社群复购率']) || 0) > 0 ? '社群跟单' : 
                        (parseFloat(exp['累计直播间复购率']) || 0) > 0 ? '直播间成单' : '其他';
        conclusions.push(`实验期数已有${expRepNum}人复购（累计流水¥${expRepFlow}），复购来源为${source}。`);
      }
      
      if (latestCourses.length > 0) {
        const lastC = latestCourses[latestCourses.length - 1];
        conclusions.push(`最新单课「${lastC}」完课率${(expCourseDict[lastC] * 100).toFixed(1)}%。`);
      }
      
      if (conclusions.length === 0) conclusions.push('当前数据暂无显著差异，持续观察中。');
      o += conclusions.join('\n');
      
      outputs.push(o);
    }
  }
}

console.log(outputs.join('\n\n---\n\n'));
