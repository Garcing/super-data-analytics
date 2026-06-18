const { Pool } = require('pg');
const fs = require('fs');

async function test() {
  const pool = new Pool({
    host: process.env.HOLOGRES_HOST,
    port: Number(process.env.HOLOGRES_PORT),
    database: process.env.HOLOGRES_DATABASE,
    user: process.env.HOLOGRES_USER,
    password: process.env.HOLOGRES_PASSWORD,
  });
  const client = await pool.connect();
  try {
    const sqlFile = 'C:\\Users\\Administrator\\.agents\\skills\\super-data-analyst\\querying-data-via-sql\\cache\\sql-query-20260614-141024-ac876be4210d.sql';
    const sql = fs.readFileSync(sqlFile, 'utf-8');
    console.log('SQL length:', sql.length);
    console.log('Executing...');
    const res = await client.query(sql);
    console.log('rows:', res.rows.length);
    console.log('fields:', res.fields.length);
    for (const f of res.fields) {
      if (!f.name) console.log('NULL FIELD at index:', res.fields.indexOf(f));
    }
    if (res.rows.length > 0) console.log('First row keys:', Object.keys(res.rows[0]));
  } catch(e) {
    console.error('Error:', e.message);
    if (e.stack) console.error('Stack:', e.stack.substring(0, 500));
  }
  client.release();
  await pool.end();
}
test();
