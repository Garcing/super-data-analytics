-- Test: just query the listen details table
select period_id, topic_name, topic_start_time, count(distinct user_id) as cnt
from xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all
where period_id = '120344421832'
    and topic_start_time >= '2026-06-11'
group by 1,2,3
limit 5
