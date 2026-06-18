-- Test json_object_agg specifically - fixed
select
    period_id, json_object_agg(topic_name, round(cnt * 1.0, 4)) as test_dict
from (
    select period_id, topic_name, count(1) as cnt
    from xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all
    where period_id = '120344421832' and topic_start_time >= '2026-06-11'
    group by 1,2
    limit 5
) t
group by 1
