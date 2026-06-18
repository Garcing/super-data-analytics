select current_date as utc_date,
'2026-05-11'::date + 18 - 1 as day18_date,
'2026-05-11'::date + 19 - 1 as day19_date,
case when '2026-05-11'::date + 18 - 1 = current_date then 'day18 matches' else 'day18 no match' end as day18_check,
case when '2026-05-11'::date + 19 - 1 = current_date then 'day19 matches' else 'day19 no match' end as day19_check
