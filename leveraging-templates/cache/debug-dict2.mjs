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

// Test on first broadcast experimental row
for (const r of data.rows) {
  if (r['是否播报期数'] === '是' && r['期数分组'] === '实验期数' && r['实际期数进度'] === '开营第14天') {
    const d = parseDict(r['完课率字典']);
    console.log('Dict keys count:', Object.keys(d).length);
    console.log('Last 3:', Object.keys(d).slice(-3));
    console.log('latest3Courses:', Object.keys(d).slice(-3));
    break;
  }
}
