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

for (const r of data.rows) {
  if (r['是否播报期数'] === '是' && r['期数分组'] === '实验期数') {
    const d = parseDict(r['完课率字典']);
    console.log(r['期数名称'], 'progress:', r['实际期数进度']);
    console.log('  learn keys (last 5):', Object.keys(d).slice(-5));
    const q = parseDict(r['问卷提交率字典']);
    console.log('  question keys:', Object.keys(q));
    const c = parseDict(r['打卡率字典']);
    console.log('  clock keys:', Object.keys(c));
    console.log();
  }
}
