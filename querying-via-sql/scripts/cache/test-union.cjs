const { Pool } = require('pg');
const path = require('path');
const fs = require('fs');

for (let dir = __dirname; dir !== path.dirname(dir); dir = path.dirname(dir)) {
  try {
    const content = fs.readFileSync(path.join(dir, '.env'), 'utf-8');
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eq = trimmed.indexOf('=');
      if (eq === -1) continue;
      const key = trimmed.slice(0, eq).trim();
      const val = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '');
      if (!process.env[key]) process.env[key] = val;
    }
    break;
  } catch {}
}

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
    const sql = `with t as (
      select 'a' as x, null::text as y
      union all
      select 'b', null::text
    )
    select * from t`;
    const res = await client.query(sql);
    console.log('fields:', JSON.stringify(res.fields));
    console.log('rows:', JSON.stringify(res.rows));
  } catch(e) {
    console.error('Error:', e.message);
    console.error('Stack:', e.stack);
  }
  client.release();
  await pool.end();
}
test();
