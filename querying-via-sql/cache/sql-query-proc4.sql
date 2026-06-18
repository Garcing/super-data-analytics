-- Process data for broadcast periods - fixed
with t_link_sub as (
    select period_id, day_num, camp_start_date + day_num - 1 as act_date, user_num from (
        select period_id, day_num, (camp_start_time::date + day_num - 1) as camp_start_date, count(1) as user_num
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
    ) s
)
,periods as (
    select period_name, period_id from xqd_data_analysis.dim_xqd_course_period_hf
    where period_name in ('蜕变第16A期26-0606', '蜕变第十六期26-0606', '蜕变第十七期26-0611')
)
select 'learn' as metric, p.period_name, ls.day_num, ls.user_num
    ,json_object_agg(topic_name, round((finish_num * 1.0 / ls.user_num), 4)) as detail
from periods p
join t_link_sub ls on p.period_id = ls.period_id
    and ls.day_num = case when p.period_name = '蜕变第十七期26-0611' then 4 else 9 end
left join (
    select sub.period_id, sub.day_num, sub.topic_name
        ,count(distinct sub.uid) filter(where is_finish_learn = '是') as finish_num
    from (
        select ls2.period_id, ls2.day_num, b.topic_name, b.user_id as uid, b.is_finish_learn
        from t_link_sub ls2
        left join xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all as b
            on ls2.period_id = b.period_id and b.topic_start_time::date <= ls2.act_date and b.topic_finish_time < now()
    ) sub
    group by 1,2,3
) b on ls.period_id = b.period_id and ls.day_num = b.day_num
group by 1,2,3,4

union all

select 'question' as metric, p.period_name, ls.day_num, ls.user_num
    ,json_object_agg(qn, round((qnum * 1.0 / ls.user_num), 4)) as detail
from periods p
join t_link_sub ls on p.period_id = ls.period_id
    and ls.day_num = case when p.period_name = '蜕变第十七期26-0611' then 4 else 9 end
left join (
    select sub2.period_id, sub2.day_num, sub2.qn, count(distinct sub2.uid) as qnum
    from (
        select ls2.period_id, ls2.day_num, b.questionnaire_name as qn, b.user_id as uid
        from t_link_sub ls2
        left join xqd_data_analysis.ads_xqd_platform_question_user_questionnaire_detail_hour_bi_all as b
            on ls2.period_id = b.period_id and b.question_visit_create_time::date <= ls2.act_date and b.question_visit_create_time < now()
    ) sub2
    group by 1,2,3
) b on ls.period_id = b.period_id and ls.day_num = b.day_num
group by 1,2,3,4

union all

select 'clock' as metric, p.period_name, ls.day_num, ls.user_num
    ,json_object_agg(cn, round((cnum * 1.0 / ls.user_num), 4)) as detail
from periods p
join t_link_sub ls on p.period_id = ls.period_id
    and ls.day_num = case when p.period_name = '蜕变第十七期26-0611' then 4 else 9 end
left join (
    select sub3.period_id, sub3.day_num, sub3.cn, count(distinct sub3.uid) as cnum
    from (
        select ls2.period_id, ls2.day_num, b.clock_task_name as cn, b.user_id as uid
        from t_link_sub ls2
        left join xqd_data_analysis.ads_xqd_study_user_clock_detail_hour_bi_all as b
            on ls2.period_id = b.period_id and b.clock_time::date <= ls2.act_date and b.clock_time < now()
    ) sub3
    group by 1,2,3
) b on ls.period_id = b.period_id and ls.day_num = b.day_num
group by 1,2,3,4
