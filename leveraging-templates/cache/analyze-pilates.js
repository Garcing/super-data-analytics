const fs = require('fs');
const data = JSON.parse(fs.readFileSync('cache/result-20260620-220000-pilates.json', 'utf-8'));

// Filter only rows that are for broadcasting (是否播报期数 = 是)
const broadcastRows = data.rows.filter(r => r['是否播报期数'] === '是');
console.log('=== 播报期数 ===');
broadcastRows.forEach(r => {
  console.log(`期数名称: ${r['期数名称']}, 期数分组: ${r['期数分组']}, 实际期数进度: ${r['实际期数进度']}, 数据分组: ${r['数据分组']}`);
});

// Group by 实际期数进度
const progressGroups = {};
data.rows.filter(r => r['数据分组'] === '期数-明细').forEach(r => {
  const p = r['实际期数进度'];
  if (!progressGroups[p]) progressGroups[p] = [];
  progressGroups[p].push(r);
});

console.log('\n=== 按实际期数进度分组 ===');
Object.keys(progressGroups).sort().forEach(p => {
  console.log(`\n[${p}]`);
  progressGroups[p].forEach(r => {
    console.log(`  ${r['期数分组']} | ${r['期数名称']} | 人服比:${r['人服比']} | 累计复购率:${r['累计复购率']} | 人效:${r['人效']}`);
  });
});

// 往期大盘
const historical = data.rows.filter(r => r['数据分组'] === '往期大盘-汇总');
console.log('\n=== 往期大盘 ===');
historical.forEach(r => {
  console.log(`实际期数进度: ${r['实际期数进度']}, 期数名称: ${r['期数名称']}, 人服比:${r['人服比']}, 累计复购率:${r['累计复购率']}`);
});
