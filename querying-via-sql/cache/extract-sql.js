const fs = require('fs');
const { execSync } = require('child_process');

const scriptDir = 'C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\leveraging-report-templates';
const outputFile = 'C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\cache\\sql-query-20260613-220134-74a06c3b8e.sql';

const content = execSync(`node "${scriptDir}\\scripts\\templates.js" read ZxOGdterIodolPxLzbycVvJrnpe`, { encoding: 'utf-8' });

const startMarker = '```SQL';
const endMarker = '```';
const startIdx = content.indexOf(startMarker);
const endIdx = content.indexOf(endMarker, startIdx + startMarker.length);

if (startIdx === -1 || endIdx === -1) {
  console.error('SQL block not found');
  process.exit(1);
}

const sql = content.substring(startIdx + startMarker.length, endIdx).trim();
fs.writeFileSync(outputFile, sql, 'utf-8');
console.log('SQL extracted, length: ' + sql.length);
