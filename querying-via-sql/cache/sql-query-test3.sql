with
t_period as (
    select * from (values
        ('蜕变第11A期26-0419', '对照期数', 'Agent第一期'),
        ('蜕变第十一期26-0419', '实验期数', 'Agent第一期'),
        ('蜕变第16A期26-0606', '实验期数', 'Agent第二期'),
        ('蜕变第十六期26-0606', '对照期数', 'Agent第二期'),
        ('蜕变第十七期26-0611', '混合期数', 'Agent第二期')
    ) as t(period_name, period_group, agent_group)
),
t_agent_desc as (
    select 'Agent第一期' as agent_group, 'desc1' as agent_desc, '1:120' as agent_target_recep
    union all select 'Agent第二期', 'desc2', '1:70'
),
t_link as (
    select
         a.order_id
        ,a.category_name
        ,a.camp_name
        ,a.period_name
        ,a.period_id
        ,coalesce(b.period_group, '往期大盘') as period_group
        ,b.agent_group
        ,a.sale_after_wework_user_id
        ,a.camp_start_time
        ,a.camp_end_time
        ,case when current_date > camp_end_time then his_sale_after_sys_user_name else sale_after_sys_user_name end as sale_after_sys_user_name
        ,a.user_id
        ,1 as is_recep
        ,case when permissions_status = 'Y' AND retain_scope = '否' then 0 else 1 end as is_refund
        ,0 as is_change_period_out
    from xqd_data_analysis.ads_xqd_service_after_sales_recep_details_hour_bi_all as a
    left join t_period as b on a.period_name = b.period_name
    where a.order_id is not null and a.camp_name = '25天普拉提瘦身蜕变营' and sale_after_rn = 1 and camp_start_time >= '2026-04-01'
    union all
    select null::text, a.category_name, a.old_camp_name, a.old_period_name, a.old_period_id,
        coalesce(b.period_group, '往期大盘'), agent_group, null::text, old_camp_start_time, old_camp_end_time,
        old_sale_after_sys_user_name, a.user_id, 0, 0, 1
    from xqd_data_analysis.ads_xqd_platform_stu_mana_change_period_class_detail_hour_bi_all as a
    left join t_period as b on a.old_period_name = b.period_name
    where old_camp_start_time >= '2026-04-01' and camp_start_time > old_camp_start_time
        and change_period_type = '换期' and (censor_change_period_type is null or censor_change_period_type <> '插班上课')
        and a.old_camp_name = '25天普拉提瘦身蜕变营'
)
select period_name, period_group, count(1) as cnt from t_link group by 1,2 order by 1