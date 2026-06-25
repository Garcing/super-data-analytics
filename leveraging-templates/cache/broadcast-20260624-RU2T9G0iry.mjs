import fs from 'fs';

const data = JSON.parse(fs.readFileSync('cache/result-20260624-150500-pilates.json', 'utf-8'));

// Helper: parse dict string like '"期数名": { "a": 0.5, "b": 0.6 }'
function parseDict(dictStr) {
  if (!dictStr || dictStr === '-' || dictStr === 'null') return {};
  const obj = {};
  const match = dictStr.match(/\{(.+)\}/s);
  if (!match) return obj;
  const inner = match[1];
  const re = new RegExp('"([^"]+)"\\s*:\\s*([\\d.]+)\\s*', 'g');
  let m;
  while ((m = re.exec(inner)) !== null) {
    obj[m[1].trim()] = parseFloat(m[2]);
  }
  return obj;
}

// Get latest N keys from a dict
function latestKeys(dict, n) {
  return Object.keys(dict).slice(-n);
}

// Fuzzy match a key in another dict
function fuzzyMatch(key, dict) {
  if (!key) return null;
  // Try exact match first
  if (dict[key] !== undefined) return dict[key];
  // Fuzzy: try substring match
  for (const k of Object.keys(dict)) {
    if (k.includes(key) || key.includes(k)) return dict[k];
  }
  return null;
}

function fmt(v, def = '-') {
  if (v === null || v === undefined || v === '' || v === 'null') return def;
  const n = parseFloat(v);
  if (isNaN(n)) return def;
  return (n * 100).toFixed(2) + '%';
}

function fmtNum(v, def = '-') {
  if (v === null || v === undefined || v === '' || v === 'null') return def;
  return String(v);
}

function fmtMoney(v, def = '-') {
  if (v === null || v === undefined || v === '' || v === 'null') return def;
  const n = parseFloat(v);
  if (isNaN(n) || n === 0) return def;
  return n.toLocaleString();
}

// Group by 实际期数进度
const progressGroups = {};
for (const r of data.rows) {
  if (r['数据分组'] !== '期数-明细') continue;
  const p = r['实际期数进度'];
  if (!progressGroups[p]) progressGroups[p] = [];
  progressGroups[p].push(r);
}

const sortedProgresses = Object.keys(progressGroups).sort();

// Get往期大盘 rows grouped by 实际期数进度
const historicalByProgress = {};
for (const r of data.rows) {
  if (r['数据分组'] !== '往期大盘-汇总') continue;
  const p = r['实际期数进度'];
  historicalByProgress[p] = r;
}

const broadcastTime = '2026-06-24 15:00:00';
const messages = [];

for (const progress of sortedProgresses) {
  const rows = progressGroups[progress];
  const experimental = rows.filter(r => r['期数分组'] === '实验期数' && r['是否播报期数'] === '是');
  const control = rows.filter(r => r['期数分组'] === '对照期数' && r['是否播报期数'] === '是');
  const pastExperimental = rows.filter(r => r['期数分组'] === '实验期数' && r['是否播报期数'] === '否');

  if (experimental.length === 0 && control.length === 0) continue;

  // Take first experimental row for header info
  const expRow = experimental[0] || rows.find(r => r['期数分组'] === '实验期数') || rows[0];
  const agentGroup = expRow['Agent期数'] || '-';
  const agentDesc = expRow['Agent描述'] || '-';
  const agentTarget = expRow['Agent目标人服比'] || '-';
  const targetNum = parseInt(agentTarget.split(':')[1]) || 0;

  // Historical for this progress
  const hist = historicalByProgress[progress];

  let md = `🤖普拉提<${agentGroup}>数据播报\n\n`;
  md += `【本期能力】${agentDesc}\n\n`;
  md += `【播报时间】${broadcastTime}\n\n`;
  md += `【实际期数进度】${progress}\n\n`;

  // 人服比 - use the experimental broadcast row
  const expBroadcast = experimental[0];
  if (expBroadcast) {
    const actualRatio = parseInt(expBroadcast['人服比']) || 0;
    const diff = actualRatio - targetNum;
    md += `【人服比】目标${agentTarget}，实际${actualRatio}，差距${diff > 0 ? '+' : ''}${diff}\n\n`;
  }

  // 往期大盘期数
  if (hist) {
    md += `【往期大盘期数】${hist['期数名称']}\n\n`;
  }

  // 销转区间判断
  const saleSection = expRow['期数销转区间'];
  const isSalePhase = saleSection && saleSection !== '非销转状态';

  if (!isSalePhase) {
    md += `> 💡本日销转：当前尚未进入销转阶段，暂无数据\n\n`;
    md += `> ⭐累计销转：当前尚未进入销转阶段，暂无数据\n\n`;
  } else {
    // Build本日销转 table
    md += `💡本日销转\n\n`;
    md += `| 期数分组 | 期数名称 | 本日复购人数 | 本日复购流水 | 本日复购率 |\n`;
    md += `| - | - | - | - | - |\n`;
    for (const exp of experimental) {
      const dailyRate = exp['承接人数'] > 0 ? (parseFloat(exp['复购人数']) / parseFloat(exp['承接人数'])).toFixed(4) : '-';
      const controlMatch = control.find(c => c['实际期数进度'] === progress);
      md += `| 实验期数 | ${exp['期数名称']} | ${fmtNum(exp['复购人数'], '-')} | ${fmtMoney(exp['复购流水'], '-')} | ${dailyRate === '-' ? '-' : (parseFloat(dailyRate) * 100).toFixed(2) + '%'} |\n`;
    }
    for (const ctrl of control) {
      const dailyRate = ctrl['承接人数'] > 0 ? (parseFloat(ctrl['复购人数']) / parseFloat(ctrl['承接人数'])).toFixed(4) : '-';
      md += `| 对照期数 | ${ctrl['期数名称']} | ${fmtNum(ctrl['复购人数'], '-')} | ${fmtMoney(ctrl['复购流水'], '-')} | ${dailyRate === '-' ? '-' : (parseFloat(dailyRate) * 100).toFixed(2) + '%'} |\n`;
    }

    // Build累计销转 table
    md += `\n⭐累计销转\n\n`;
    // Determine columns based on phase
    const hasPre = saleSection === '前置期' || saleSection === '结营日' || saleSection === 'T+10';
    const hasCampEnd = saleSection === '结营日' || saleSection === 'T+10';
    const hasT10 = saleSection === 'T+10';

    let cumHeader = '| 期数分组 | 期数名称 | 累计复购率 | 累计直播间复购率 | 累计社群复购率';
    if (hasPre) cumHeader += ' | 累计前置期复购率';
    if (hasCampEnd) cumHeader += ' | 累计结营日复购率';
    if (hasT10) cumHeader += ' | 累计T+10复购率';
    cumHeader += ' | 人效 |\n';
    let cumSep = '| - | - | - | - | -';
    if (hasPre) cumSep += ' | -';
    if (hasCampEnd) cumSep += ' | -';
    if (hasT10) cumSep += ' | -';
    cumSep += ' | - |\n';

    md += cumHeader + cumSep;

    for (const exp of experimental) {
      let row = `| 实验期数 | ${exp['期数名称']} | ${fmt(exp['累计复购率'])} | ${fmt(exp['累计直播间复购率'])} | ${fmt(exp['累计社群复购率'])}`;
      if (hasPre) row += ` | ${fmt(exp['累计前置期复购率'])}`;
      if (hasCampEnd) row += ` | ${fmt(exp['累计结营日复购率'])}`;
      if (hasT10) row += ` | ${fmt(exp['累计T+10复购率'])}`;
      row += ` | ${fmtNum(exp['人效'], '-')} |\n`;
      md += row;
    }
    for (const ctrl of control) {
      let row = `| 对照期数 | ${ctrl['期数名称']} | ${fmt(ctrl['累计复购率'])} | ${fmt(ctrl['累计直播间复购率'])} | ${fmt(ctrl['累计社群复购率'])}`;
      if (hasPre) row += ` | ${fmt(ctrl['累计前置期复购率'])}`;
      if (hasCampEnd) row += ` | ${fmt(ctrl['累计结营日复购率'])}`;
      if (hasT10) row += ` | ${fmt(ctrl['累计T+10复购率'])}`;
      row += ` | ${fmtNum(ctrl['人效'], '-')} |\n`;
      md += row;
    }
    // Past experimental (latest one)
    if (pastExperimental.length > 0) {
      const pe = pastExperimental[pastExperimental.length - 1];
      let row = `| 过往实验期数 | ${pe['期数名称']} | ${fmt(pe['累计复购率'])} | ${fmt(pe['累计直播间复购率'])} | ${fmt(pe['累计社群复购率'])}`;
      if (hasPre) row += ` | ${fmt(pe['累计前置期复购率'])}`;
      if (hasCampEnd) row += ` | ${fmt(pe['累计结营日复购率'])}`;
      if (hasT10) row += ` | ${fmt(pe['累计T+10复购率'])}`;
      row += ` | ${fmtNum(pe['人效'], '-')} |\n`;
      md += row;
    }
    if (hist) {
      let row = `| 往期大盘 | ${hist['期数名称']} | ${fmt(hist['累计复购率'])} | ${fmt(hist['累计直播间复购率'])} | ${fmt(hist['累计社群复购率'])}`;
      if (hasPre) row += ` | ${fmt(hist['累计前置期复购率'])}`;
      if (hasCampEnd) row += ` | ${fmt(hist['累计结营日复购率'])}`;
      if (hasT10) row += ` | ${fmt(hist['累计T+10复购率'])}`;
      row += ` | ${fmtNum(hist['人效'], '-')} |\n`;
      md += row;
    }
    md += '\n';
  }

  // Process indicators table
  // Get experiment period's latest 3 courses, 1 questionnaire, 1 clock task
  const expLearnDict = parseDict(expRow['完课率字典']);
  const expQuestionDict = parseDict(expRow['问卷提交率字典']);
  const expClockDict = parseDict(expRow['打卡率字典']);

  const latest3Courses = latestKeys(expLearnDict, 3);
  const latest1Question = latestKeys(expQuestionDict, 1);
  const latest1Clock = latestKeys(expClockDict, 1);

  // Process control's dict for matching
  const controlRow = control[0];
  const ctrlLearnDict = controlRow ? parseDict(controlRow['完课率字典']) : {};
  const ctrlQuestionDict = controlRow ? parseDict(controlRow['问卷提交率字典']) : {};
  const ctrlClockDict = controlRow ? parseDict(controlRow['打卡率字典']) : {};

  // Past experimental dict
  const peRow = pastExperimental.length > 0 ? pastExperimental[pastExperimental.length - 1] : null;
  const peLearnDict = peRow ? parseDict(peRow['完课率字典']) : {};
  const peQuestionDict = peRow ? parseDict(peRow['问卷提交率字典']) : {};
  const peClockDict = peRow ? parseDict(peRow['打卡率字典']) : {};

  // Historical dict
  const histLearnDict = hist ? parseDict(hist['完课率字典']) : {};
  const histQuestionDict = hist ? parseDict(hist['问卷提交率字典']) : {};
  const histClockDict = hist ? parseDict(hist['打卡率字典']) : {};

  // Table header
  const procHeaders = [...latest3Courses.map(c => shortenName(c)), ...latest1Question.map(q => shortenName(q)), ...latest1Clock.map(c => shortenName(c))];
  if (procHeaders.length === 0) {
    md += `🔎过程指标：暂无数据\n\n`;
  } else {
    md += `🔎过程指标\n\n`;
    md += `| 期数分组 | 期数名称 | ${procHeaders.join(' | ')} |\n`;
    md += `| - | - | ${procHeaders.map(() => '-').join(' | ')} |\n`;

    // Experimental row
    let expProcRow = `| 实验期数 | ${expRow['期数名称']}`;
    for (const c of latest3Courses) {
      expProcRow += ` | ${fmt(expLearnDict[c])}`;
    }
    for (const q of latest1Question) {
      expProcRow += ` | ${fmt(expQuestionDict[q])}`;
    }
    for (const c of latest1Clock) {
      expProcRow += ` | ${fmt(expClockDict[c])}`;
    }
    expProcRow += ' |\n';
    md += expProcRow;

    // Control row - fuzzy match from experimental's keys
    if (controlRow) {
      let ctrlProcRow = `| 对照期数 | ${controlRow['期数名称']}`;
      for (const c of latest3Courses) {
        ctrlProcRow += ` | ${fmt(fuzzyMatch(c, ctrlLearnDict))}`;
      }
      for (const q of latest1Question) {
        ctrlProcRow += ` | ${fmt(fuzzyMatch(q, ctrlQuestionDict))}`;
      }
      for (const c of latest1Clock) {
        ctrlProcRow += ` | ${fmt(fuzzyMatch(c, ctrlClockDict))}`;
      }
      ctrlProcRow += ' |\n';
      md += ctrlProcRow;
    }

    // Past experimental row
    if (peRow) {
      let peProcRow = `| 过往实验期数 | ${peRow['期数名称']}`;
      for (const c of latest3Courses) {
        peProcRow += ` | ${fmt(fuzzyMatch(c, peLearnDict))}`;
      }
      for (const q of latest1Question) {
        peProcRow += ` | ${fmt(fuzzyMatch(q, peQuestionDict))}`;
      }
      for (const c of latest1Clock) {
        peProcRow += ` | ${fmt(fuzzyMatch(c, peClockDict))}`;
      }
      peProcRow += ' |\n';
      md += peProcRow;
    }

    // Historical row
    if (hist) {
      let histProcRow = `| 往期大盘 | ${hist['期数名称']}`;
      for (const c of latest3Courses) {
        histProcRow += ` | ${fmt(fuzzyMatch(c, histLearnDict))}`;
      }
      for (const q of latest1Question) {
        histProcRow += ` | ${fmt(fuzzyMatch(q, histQuestionDict))}`;
      }
      for (const c of latest1Clock) {
        histProcRow += ` | ${fmt(fuzzyMatch(c, histClockDict))}`;
      }
      histProcRow += ' |\n';
      md += histProcRow;
    }
    md += '\n';
  }

  // Core conclusions
  md += `【核心结论】\n`;
  md += generateConclusion(progress, experimental, control, pastExperimental, hist, isSalePhase);
  md += '\n';

  messages.push(md);
}

function shortenName(name) {
  if (!name) return '-';
  // Remove brackets prefix like 【精准训练】
  let s = name.replace(/^【[^】]+】\s*/, '');
  // Limit length
  if (s.length > 12) s = s.substring(0, 12);
  return s;
}

function generateConclusion(progress, experimental, control, pastExperimental, hist, isSalePhase) {
  const lines = [];
  const expRow = experimental[0];
  const ctrlRow = control[0];

  if (!isSalePhase) {
    lines.push(`${progress}尚未进入销转阶段。`);
  }

  if (expRow && ctrlRow) {
    const expRatio = parseInt(expRow['人服比']) || 0;
    const ctrlRatio = parseInt(ctrlRow['人服比']) || 0;
    const targetNum = parseInt(expRow['Agent目标人服比']?.split(':')[1]) || 0;
    const expSize = parseInt(expRow['承接人数']) || 0;
    const ctrlSize = parseInt(ctrlRow['承接人数']) || 0;

    lines.push(`实验期数(${expRow['期数名称']})承接${expSize}人，人服比${expRatio}${expRatio >= targetNum ? '(目标' + expRow['Agent目标人服比'] + '，已达标)' : '(目标' + expRow['Agent目标人服比'] + '，未达标)'}；对照期数(${ctrlRow['期数名称']})承接${ctrlSize}人，人服比${ctrlRatio}。`);

    if (expRow['累计复购率'] && ctrlRow['累计复购率']) {
      const expRate = parseFloat(expRow['累计复购率']);
      const ctrlRate = parseFloat(ctrlRow['累计复购率']);
      if (expRate > ctrlRate) {
        lines.push(`实验期数累计复购率${(expRate * 100).toFixed(2)}%高于对照期数${(ctrlRate * 100).toFixed(2)}%。`);
      } else if (expRate < ctrlRate) {
        lines.push(`实验期数累计复购率${(expRate * 100).toFixed(2)}%低于对照期数${(ctrlRate * 100).toFixed(2)}%。`);
      } else {
        lines.push(`实验期数累计复购率${(expRate * 100).toFixed(2)}%与对照期数持平。`);
      }
    }
  }

  if (hist) {
    lines.push(`往期大盘(${hist['期数名称']})人服比${hist['人服比']}。`);
  }

  return lines.join('');
}

// Output results
const fullMd = messages.join('\n---\n\n');

// Check total byte length (markdown_v2 limit is 4096 bytes per message)
const byteLength = Buffer.byteLength(fullMd, 'utf-8');
console.log(`Total broadcast length: ${byteLength} bytes, ${messages.length} groups`);

// If total exceeds 4096 bytes, split into separate messages
if (byteLength <= 4096) {
  const body = { msgtype: 'markdown_v2', markdown_v2: { content: fullMd } };
  fs.writeFileSync('cache/wecom-pilati-body.json', JSON.stringify(body, null, 2), 'utf-8');
  console.log('Single message body saved to cache/wecom-pilati-body.json');
  console.log('---PREVIEW---');
  console.log(fullMd);
} else {
  // Split by groups
  const bodies = [];
  for (const msg of messages) {
    bodies.push({ msgtype: 'markdown_v2', markdown_v2: { content: msg } });
  }
  fs.writeFileSync('cache/wecom-pilati-body.json', JSON.stringify(bodies, null, 2), 'utf-8');
  console.log(`Split into ${bodies.length} messages (saved as array)`);
  for (let i = 0; i < bodies.length; i++) {
    const len = Buffer.byteLength(bodies[i].markdown_v2.content, 'utf-8');
    console.log(`Message ${i + 1}: ${len} bytes`);
    console.log(`---PREVIEW ${i + 1}---`);
    console.log(bodies[i].markdown_v2.content);
  }
}
