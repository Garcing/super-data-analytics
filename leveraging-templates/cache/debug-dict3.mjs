import fs from 'fs';

const data = JSON.parse(fs.readFileSync('cache/result-20260624-150500-pilates.json', 'utf-8'));

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

const progressGroups = {};
for (const r of data.rows) {
  if (r['数据分组'] !== '期数-明细') continue;
  const p = r['实际期数进度'];
  if (!progressGroups[p]) progressGroups[p] = [];
  progressGroups[p].push(r);
}

const sortedProgresses = Object.keys(progressGroups).sort();

for (const progress of sortedProgresses) {
  const rows = progressGroups[progress];
  const experimental = rows.filter(r => r['期数分组'] === '实验期数' && r['是否播报期数'] === '是');
  const control = rows.filter(r => r['期数分组'] === '对照期数' && r['是否播报期数'] === '是');
  
  if (experimental.length === 0 && control.length === 0) continue;
  
  const expRow = experimental[0] || rows.find(r => r['期数分组'] === '实验期数') || rows[0];
  
  const expLearnDict = parseDict(expRow['完课率字典']);
  const expQuestionDict = parseDict(expRow['问卷提交率字典']);
  const expClockDict = parseDict(expRow['打卡率字典']);
  
  console.log(`[${progress}] expRow=${expRow['期数名称']}, 是否播报=${expRow['是否播报期数']}`);
  console.log('  完课率字典 raw:', expRow['完课率字典']?.substring(0, 80));
  console.log('  parsed learn keys:', Object.keys(expLearnDict).length);
  console.log('  latest 3:', Object.keys(expLearnDict).slice(-3));
  console.log('  question keys:', Object.keys(expQuestionDict));
  console.log('  clock keys:', Object.keys(expClockDict));
  
  const latest3Courses = Object.keys(expLearnDict).slice(-3);
  const latest1Question = Object.keys(expQuestionDict).slice(-1);
  const latest1Clock = Object.keys(expClockDict).slice(-1);
  console.log('  procHeaders count:', latest3Courses.length + latest1Question.length + latest1Clock.length);
}
