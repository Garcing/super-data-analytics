-- Test: join with dim_xqd_course_period_hf and generate_series
with t_period as (
    select * from (values
        ('蜕变第11A期26-0419', '对照期数', 'Agent第一期'),
        ('蜕变第十一期26-0419', '实验期数', 'Agent第一期'),
        ('蜕变第16A期26-0606', '实验期数', 'Agent第二期'),
        ('蜕变第十六期26-0606', '对照期数', 'Agent第二期'),
        ('蜕变第十七期26-0611', '混合期数', 'Agent第二期')
    ) as t(period_name, period_group, agent_group)
)
,t_agent_desc as (
    select 'Agent第一期' as agent_group, 'desc1' as agent_desc, '1:120' as agent_target_recep
    union select 'Agent第二期', 'desc2', '1:70'
)
,t_link as (
    select
         a.order_id, a.category_name, a.camp_name, a.period_name, a.period_id
        ,coalesce(b.period_group, '往期大盘') as period_group, b.agent_group
        ,a.sale_after_wework_user_id, a.camp_start_time, a.camp_end_time
        ,case when current_date > camp_end_time then his_sale_after_sys_user_name else sale_after_sys_user_name end as sale_after_sys_user_name
        ,a.user_id, 1 as is_recep
        ,case when permissions_status = 'Y' AND retain_scope = '否' then 0 else 1 end as is_refund
        ,0 as is_change_period_out
    from xqd_data_analysis.ads_xqd_service_after_sales_recep_details_hour_bi_all as a
    left join t_period as b on a.period_name = b.period_name
    where a.order_id is not null and a.camp_name = '25天普拉提瘦身蜕变营' and sale_after_rn = 1 and camp_start_time >= '2026-04-01'
    union all
    select
         null::text, a.category_name, a.old_camp_name, a.old_period_name, a.old_period_id
        ,coalesce(b.period_group, '往期大盘'), agent_group
        ,null::text, old_camp_start_time, old_camp_end_time
        ,old_sale_after_sys_user_name, a.user_id, 0, 0, 1
    from xqd_data_analysis.ads_xqd_platform_stu_mana_change_period_class_detail_hour_bi_all as a
    left join t_period as b on a.old_period_name = b.period_name
    where 1=1
        and old_camp_start_time >= '2026-04-01' and camp_start_time > old_camp_start_time
        and change_period_type = '换期'
        and (censor_change_period_type is null or censor_change_period_type <> '插班上课')
        and a.old_camp_name = '25天普拉提瘦身蜕变营'
)
,t_window as (
    select *, row_number() over(partition by period_id, user_id order by is_recep desc) as period_rn
        ,count(1) over(partition by period_id, sale_after_sys_user_name) as sale_after_recep_num
    from t_link
)
,t_link_n as (
    select a.*, b.sales_conversion_time
        ,case
            when current_date < camp_start_time::date then '开营前'
            when current_date >= camp_start_time::date and current_date < sales_conversion_time::date then '开营第' || (current_date - camp_start_time::date + 1) || '天'
            when current_date = sales_conversion_time::date then '前置销转日'
            when current_date > sales_conversion_time::date and current_date < camp_end_time::date - 10 then '前置期'
            when current_date = camp_end_time::date - 10 then '结营日'
            when current_date > camp_end_time::date - 10 then 'T+10'
            else '报错'
          end as cur_period_progress
        ,case
            when camp_start_time::date + c.day_num - 1 >= sales_conversion_time::date and camp_start_time::date + c.day_num - 1 < camp_end_time::date - 10 then '前置期'
            when camp_start_time::date + c.day_num - 1 = camp_end_time::date - 10 then '结营日'
            when camp_start_time::date + c.day_num - 1 > camp_end_time::date - 10 then 'T+10'
            else '非销转状态'
          end as period_progress_sale_section
        ,case
            when camp_start_time::date + c.day_num - 1 < sales_conversion_time::date
            then '开营第' || lpad(c.day_num::text, 2, '0') || '天'
            else '销转第' || lpad((c.day_num - (b.sales_conversion_time::date - a.camp_start_time::date))::text, 2, '0') || '天'
          end as period_progress
        ,c.day_num, d.agent_desc, d.agent_target_recep
        ,dense_rank() over(partition by a.camp_name order by d.agent_group is null desc, a.camp_end_time < current_date desc, camp_end_time desc) as rn
    from t_window as a
    join xqd_data_analysis.dim_xqd_course_period_hf as b on a.period_id = b.period_id
    join (select generate_series(1, 100) as day_num) c
        on c.day_num <= (a.camp_end_time::date - a.camp_start_time::date + 1)
        and (a.camp_start_time::date + c.day_num - 1) <= current_date
    left join t_agent_desc as d on a.agent_group = d.agent_group
    where period_rn = 1 and sale_after_recep_num > 10
)

-- Test: does t_link_n work?
select period_id, period_name, period_group, agent_group, day_num, cur_period_progress, period_progress
from t_link_n
limit 10
