import pg from 'pg';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

for (let dir = __dirname; dir !== dirname(dir); dir = dirname(dir)) {
  try {
    const envPath = join(dir, '.env');
    const content = readFileSync(envPath, 'utf-8');
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

const sqlFile = join(__dirname, '..', 'cache', 'sql-query-20260613-220134-74a06c3b8e.sql');
const fullSql = readFileSync(sqlFile, 'utf-8');

const pool = new pg.Pool({
  host: process.env.HOLOGRES_HOST,
  port: Number(process.env.HOLOGRES_PORT),
  database: process.env.HOLOGRES_DATABASE,
  user: process.env.HOLOGRES_USER,
  password: process.env.HOLOGRES_PASSWORD,
  max: 1,
  connectionTimeoutMillis: 15000,
  statementTimeout: 180000,
});

async function testQuery(name, sql) {
  const client = await pool.connect();
  try {
    console.log(`\n=== ${name} ===`);
    const result = await client.query(sql);
    const nullIdx = [];
    result.fields.forEach((f, i) => { if (!f.name) nullIdx.push(i); });
    console.log(`Columns: ${result.fields.length}, Rows: ${result.rows.length}`);
    if (nullIdx.length > 0) {
      console.log(`NULL field names at indices: ${nullIdx.join(', ')}`);
    }
    result.fields.forEach((f, i) => console.log(`  [${i}] name=${JSON.stringify(f.name)}`));
  } catch (e) {
    console.log(`ERROR: ${e.message}`);
  } finally {
    client.release();
  }
}

async function main() {
  // Get CTEs up to t_link_sub
  const tlinksubEnd = fullSql.indexOf('-- 过程数据补充在此');
  const baseSql = fullSql.substring(0, tlinksubEnd);

  // Test 1: t_link_sub
  await testQuery('t_link_sub', baseSql + '\nselect * from t_link_sub limit 1');

  // Test 2: t_learn subquery only (inner)
  const innerLearnSql = baseSql + `
    select
         a.period_id
        ,a.day_num
        ,a.user_num
        ,b.topic_name
        ,b.topic_start_time
        ,count(distinct b.user_id) filter(where is_finish_learn = '是') as finish_learn_num
    from t_link_sub as a
    left join xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all as b
        on a.period_id = b.period_id
        and b.topic_start_time::date <= act_date
        and b.topic_finish_time < now()
    group by 1,2,3,4,5
    limit 1`;
  await testQuery('t_learn inner', innerLearnSql);

  // Test 3: t_learn outer with json_object_agg
  const fullLearnSql = baseSql + `
,t_learn as (
    select
         period_id
        ,day_num
        ,sum(finish_learn_num) as finish_learn_fenzi
        ,max(user_num) * count(topic_name) as finish_learn_fenmu
        ,json_object_agg(
            topic_name,
            round((finish_learn_num * 1.0 / user_num), 4)
            order by topic_start_time
         ) as finish_learn_rate_dict
    from (
        select
             a.period_id
            ,a.day_num
            ,a.user_num
            ,b.topic_name
            ,b.topic_start_time
            ,count(distinct b.user_id) filter(where is_finish_learn = '是') as finish_learn_num
        from t_link_sub as a
        left join xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all as b
            on a.period_id = b.period_id
            and b.topic_start_time::date <= act_date
            and b.topic_finish_time < now()
        group by 1,2,3,4,5
    ) as t
    group by 1,2
)
select * from t_learn limit 1`;
  await testQuery('t_learn full', fullLearnSql);

  // Test 4: without json_object_agg
  const noJsonSql = baseSql + `
,t_learn as (
    select
         period_id
        ,day_num
        ,sum(finish_learn_num) as finish_learn_fenzi
        ,max(user_num) * count(topic_name) as finish_learn_fenmu
        ,null::text as finish_learn_rate_dict
    from (
        select
             a.period_id
            ,a.day_num
            ,a.user_num
            ,b.topic_name
            ,b.topic_start_time
            ,count(distinct b.user_id) filter(where is_finish_learn = '是') as finish_learn_num
        from t_link_sub as a
        left join xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all as b
            on a.period_id = b.period_id
            and b.topic_start_time::date <= act_date
            and b.topic_finish_time < now()
        group by 1,2,3,4,5
    ) as t
    group by 1,2
)
select * from t_learn limit 1`;
  await testQuery('t_learn no json', noJsonSql);

  await pool.end();
}

main().catch(e => { console.error(e); process.exit(1); });
