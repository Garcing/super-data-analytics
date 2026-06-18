-- Process data for specific broadcast periods at day 4 and 9
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

-- 完课率 - latest day for each period
select 'learn' as metric_type, p.period_name, ls.day_num, ls.user_num
    ,count(distinct b.topic_name) as total_topics
    ,count(distinct b.topic_name) filter(where avg_finish_rate >= 0.5) as high_finish_topics
    ,round(avg(finish_rate), 4) as avg_finish_rate
from (
    select period_name, period_id, max(day_num) as day_num
    from xqd_data_analysis.dim_xqd_course_period_hf
    where period_name in ('蜕变第16A期26-0606', '蜕变第十六期26-0606', '蜕变第十七期26-0611')
    group by 1,2
) p
join t_link_sub ls on p.period_id = ls.period_id and ls.day_num = case when p.period_name = '蜕变第十七期26-0611' then 4 else 9 end
left join (
    select ls2.period_id, ls2.day_num, b.topic_name
        ,round(count(distinct b.user_id) filter(where is_finish_learn = '是') * 1.0 / ls2.user_num, 4) as finish_rate
        ,round(avg(case when is_finish_learn = '是' then 1 else 0 end), 4) as avg_finish_rate
    from t_link_sub ls2
    join xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all as b
        on ls2.period_id = b.period_id and b.topic_start_time::date <= ls2.act_date and b.topic_finish_time < now()
    group by 1,2,3
) b on ls.period_id = b.period_id and ls.day_num = b.day_num
group by 1,2,3,4

union all

-- 问卷提交率
select 'question' as metric_type, p.period_name, ls.day_num, ls.user_num
    ,count(distinct b.questionnaire_name) as total_topics
    ,count(distinct b.questionnaire_name) filter(where avg_submit_rate >= 0.3) as high_finish_topics
    ,round(avg(submit_rate), 4) as avg_submit_rate
from (
    select period_name, period_id, max(day_num) as day_num
    from xqd_data_analysis.dim_xqd_course_period_hf
    where period_name in ('蜕变第16A期26-0606', '蜕变第十六期26-0606', '蜕变第十七期26-0611')
    group by 1,2
) p
join t_link_sub ls on p.period_id = ls.period_id and ls.day_num = case when p.period_name = '蜕变第十七期26-0611' then 4 else 9 end
left join (
    select ls2.period_id, ls2.day_num, b.questionnaire_name
        ,round(count(distinct b.user_id) * 1.0 / ls2.user_num, 4) as submit_rate
    from t_link_sub ls2
    join xqd_data_analysis.ads_xqd_platform_question_user_questionnaire_detail_hour_bi_all as b
        on ls2.period_id = b.period_id and b.question_visit_create_time::date <= ls2.act_date and b.question_visit_create_time < now()
    group by 1,2,3
) b on ls.period_id = b.period_id and ls.day_num = b.day_num
group by 1,2,3,4

union all

-- 打卡率
select 'clock' as metric_type, p.period_name, ls.day_num, ls.user_num
    ,count(distinct b.clock_task_name) as total_topics
    ,count(distinct b.clock_task_name) filter(where avg_clock_rate >= 0.3) as high_finish_topics
    ,round(avg(clock_rate), 4) as avg_clock_rate
from (
    select period_name, period_id, max(day_num) as day_num
    from xqd_data_analysis.dim_xqd_course_period_hf
    where period_name in ('蜕变第16A期26-0606', '蜕变第十六期26-0606', '蜕变第十七期26-0611')
    group by 1,2
) p
join t_link_sub ls on p.period_id = ls.period_id and ls.day_num = case when p.period_name = '蜕变第十七期26-0611' then 4 else 9 end
left join (
    select ls2.period_id, ls2.day_num, b.clock_task_name
        ,round(count(distinct b.user_id) * 1.0 / ls2.user_num, 4) as clock_rate
    from t_link_sub ls2
    join xqd_data_analysis.ads_xqd_study_user_clock_detail_hour_bi_all as b
        on ls2.period_id = b.period_id and b.clock_time::date <= ls2.act_date and b.clock_time < now()
    group by 1,2,3
) b on ls.period_id = b.period_id and ls.day_num = b.day_num
group by 1,2,3,4
