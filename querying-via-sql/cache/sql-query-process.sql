-- Process data for Agent第二期 experiment: 蜕变第16A期26-0606
-- period_id: 120344415734 (need to look up)
-- 实验期数 and 对照期数 process data at day_num=9

with t_link_sub as (
    select period_id, day_num, camp_start_time::date + day_num - 1 as act_date, count(1) as user_num
    from (
        select a.period_id, a.camp_start_time, a.camp_end_time, a.period_rn, a.sale_after_recep_num, c.day_num
        from (
            select a.period_id, a.camp_start_time, a.camp_end_time
                ,row_number() over(partition by a.period_id, a.user_id order by a.is_recep desc) as period_rn
                ,count(1) over(partition by a.period_id, a.sale_after_sys_user_name) as sale_after_recep_num
            from (
                select order_id, category_name, camp_name, period_name, period_id
                    ,sale_after_wework_user_id, camp_start_time, camp_end_time
                    ,case when current_date > camp_end_time then his_sale_after_sys_user_name else sale_after_sys_user_name end as sale_after_sys_user_name
                    ,user_id, 1 as is_recep
                    ,case when permissions_status = 'Y' AND retain_scope = '否' then 0 else 1 end as is_refund
                from xqd_data_analysis.ads_xqd_service_after_sales_recep_details_hour_bi_all as a
                where order_id is not null and camp_name = '25天普拉提瘦身蜕变营' and sale_after_rn = 1 and camp_start_time >= '2026-04-01'
            ) a
        ) a
        join (select generate_series(1, 100) as day_num) c
            on c.day_num <= (a.camp_end_time::date - a.camp_start_time::date + 1)
            and (a.camp_start_time::date + c.day_num - 1) <= current_date
        where period_rn = 1 and sale_after_recep_num > 10
    ) t
    group by 1,2,3
)

-- 完课率
select 'learn' as metric_type, period_id, day_num, user_num
    ,json_object_agg(topic_name, round((finish_learn_num * 1.0 / user_num), 4) order by topic_start_time) as rate_dict
from (
    select ls.period_id, ls.day_num, ls.user_num, b.topic_name, b.topic_start_time
        ,count(distinct b.user_id) filter(where is_finish_learn = '是') as finish_learn_num
    from t_link_sub ls
    left join xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all as b
        on ls.period_id = b.period_id and b.topic_start_time::date <= ls.act_date and b.topic_finish_time < now()
    group by 1,2,3,4,5
) t
where period_id in (
    select period_id from t_link_sub where day_num = 9
)
group by 1,2,3,4

union all

-- 问卷提交率
select 'question' as metric_type, period_id, day_num, user_num
    ,json_object_agg(questionnaire_name, round((question_num * 1.0 / user_num), 4) order by question_visit_create_time) as rate_dict
from (
    select ls.period_id, ls.day_num, ls.user_num, b.questionnaire_name
        ,min(b.question_visit_create_time) as question_visit_create_time
        ,count(distinct b.user_id) as question_num
    from t_link_sub ls
    left join xqd_data_analysis.ads_xqd_platform_question_user_questionnaire_detail_hour_bi_all as b
        on ls.period_id = b.period_id and b.question_visit_create_time::date <= ls.act_date and b.question_visit_create_time < now()
    group by 1,2,3,4
) t
where period_id in (
    select period_id from t_link_sub where day_num = 9
)
group by 1,2,3,4

union all

-- 打卡率
select 'clock' as metric_type, period_id, day_num, user_num
    ,json_object_agg(clock_task_name, round((clock_num * 1.0 / user_num), 4) order by clock_time) as rate_dict
from (
    select ls.period_id, ls.day_num, ls.user_num, b.clock_task_name
        ,min(b.clock_time) as clock_time
        ,count(distinct b.user_id) as clock_num
    from t_link_sub ls
    left join xqd_data_analysis.ads_xqd_study_user_clock_detail_hour_bi_all as b
        on ls.period_id = b.period_id and b.clock_time::date <= ls.act_date and b.clock_time < now()
    group by 1,2,3,4
) t
where period_id in (
    select period_id from t_link_sub where day_num = 9
)
group by 1,2,3,4
