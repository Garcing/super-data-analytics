with
-- 关联期数
t_period as (
    select * from (values
        ('蜕变第11A期26-0419', '对照期数', 'Agent第一期'),
        ('蜕变第十一期26-0419', '实验期数', 'Agent第一期')
    ) as t(period_name, period_group, agent_group)
)
,t_agent_desc as (
    select 'Agent第一期' as agent_group, '验证运营策略、熟悉产品/用户画像' as agent_desc, '1:120' as agent_target_recep
    union
    select 'Agent第二期', 'AI上新首版：Agent接量期/W1 SOP；AI外呼、360画像/问答、AI点评；MA接量期+W1/2，被动应答接量期+W1', '1:70'
    union
    select 'Agent第三期', 'AI迭代优化版：Agent接量期/W1 SOP；新增智群管家；MA扩展至W1/2/3/4，被动应答接量期+W1/2', '1:150'
    union
    select 'Agent第四期', 'Agent接量期/W1-W3 SOP迭代；AI工具同测试3期；MA接量期+W1/2/3/4，被动应答接量期+W1/2/3/4', '1:180'
)
,t_link as (
    select a.category_name, a.camp_name, a.period_name, a.period_id, coalesce(b.period_group, '往期大盘') as period_group, b.agent_group, a.camp_start_time, a.camp_end_time, case when current_date > camp_end_time then his_sale_after_sys_user_name else sale_after_sys_user_name end as sale_after_sys_user_name, a.user_id, 1 as is_recep, case when permissions_status = 'Y' AND retain_scope = '否' then 0 else 1 end as is_refund, 0 as is_change_period_out
    from xqd_data_analysis.ads_xqd_service_after_sales_recep_details_hour_bi_all as a
    left join t_period as b on a.period_name = b.period_name
    where a.order_id is not null and a.camp_name = '25天普拉提瘦身蜕变营' and sale_after_rn = 1
    union all
    select a.category_name, a.old_camp_name, a.old_period_name, a.old_period_id, period_group, agent_group, old_camp_start_time, old_camp_end_time, old_sale_after_sys_user_name, a.user_id, 0 as is_recep, 0 as is_refund, 1 as is_change_period_out
    from xqd_data_analysis.ads_xqd_platform_stu_mana_change_period_class_detail_hour_bi_all as a
    join t_period as b on a.old_period_name = b.period_name
    where camp_start_time > old_camp_start_time and change_period_type = '换期' and (censor_change_period_type is null or censor_change_period_type <> '插班上课') and a.old_camp_name = '25天普拉提瘦身蜕变营'
)
,t_listen_detail as (
    select period_id, user_id, count(DISTINCT topic_name) filter(where now() >= topic_start_time) as topic_num, sum(case when is_learn = '是' then 1 else 0 end) as learn_num, sum(case when is_eff_learn = '是' then 1 else 0 end) as eff_learn_num, sum(case when is_finish_learn = '是' then 1 else 0 end) as finish_learn_num
    from xqd_data_analysis.ads_xqd_study_user_listen_details_hour_bi_all
    where topic_type_name in ('视频', '直播', '智能直播') and topic_duration > 0 and camp_name = '25天普拉提瘦身蜕变营'
    group by period_id, user_id
)
,t_window as (
    select *, row_number() over(partition by period_id, user_id order by is_recep desc) as period_rn, count(1) over(partition by period_id, sale_after_sys_user_name) as sale_after_recep_num
    from t_link
)
,t_link_n as (
    select a.*, b.sales_conversion_time,
        case when current_date < camp_start_time::date then '开营前第' || (camp_start_time::date - current_date) || '天'
            when current_date = camp_start_time::date then '开营日'
            when current_date > camp_start_time::date and current_date < sales_conversion_time::date then '开营后第' || (current_date - camp_start_time::date) || '天'
            when current_date = sales_conversion_time::date then '前置销转日'
            when current_date > sales_conversion_time::date and current_date < camp_end_time::date then '前置销转后第' || (current_date - sales_conversion_time::date) || '天'
            when current_date = camp_end_time::date then '结营日'
            when current_date > camp_end_time::date then '结营后第' || (current_date - camp_end_time::date) || '天'
            else '未知状态' end as period_progress,
        '销转第' || lpad(c.day_num::text, 2, '0') || '天' as sale_progress, c.day_num, d.agent_desc, d.agent_target_recep,
        dense_rank() over(partition by a.camp_name order by d.agent_group is null desc, a.camp_end_time < current_date desc, camp_end_time desc) as rn
    from t_window as a
    join xqd_data_analysis.dim_xqd_course_period_hf as b on a.period_id = b.period_id
    join (select generate_series(1, 100) as day_num) c on c.day_num <= (a.camp_end_time::date - b.sales_conversion_time::date + 1) and (b.sales_conversion_time::date + c.day_num - 1) <= current_date
    left join t_agent_desc as d on a.agent_group = d.agent_group
    where period_rn = 1 and sale_after_recep_num > 10
)
,t_main as (
    select a.category_name, a.camp_name, a.period_name, a.period_id, a.period_progress, a.sale_progress, a.period_group, a.agent_group, a.agent_desc, a.agent_target_recep, a.camp_start_time, a.camp_end_time, a.sales_conversion_time, a.sale_after_sys_user_name, a.user_id, a.is_recep, a.is_refund, a.is_change_period_out, a.day_num, a.rn,
        case when count(b.sku_name) > 0 then 1 else 0 end as is_repurchase,
        case when count(1) filter(where b.sku_name = '35天普拉提骨态轻龄营') > 0 then 1 else 0 end is_main_rep,
        case when count(1) filter(where b.sku_name in ('普拉提骨态轻龄轻量营', '普拉提骨态轻龄精练营')) > 0 then 1 else 0 end is_back_rep,
        coalesce(sum(b.order_money - coalesce(b.refund_money, 0)), 0) as order_money
    from t_link_n as a
    left join xqd_data_analysis.ads_xqd_revenue_ord_all_order_detail_bi as b on a.user_id = b.user_id and a.is_recep = 1 and b.order_status in ('已支付', '已退款') and a.day_num = (b.order_time::date - a.sales_conversion_time::date + 1) and (a.camp_name = '25天普拉提瘦身蜕变营' and b.sku_name in ('35天普拉提骨态轻龄营', '普拉提骨态轻龄轻量营', '普拉提骨态轻龄精练营'))
    group by 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20
)
,res as (
    select category_name as 品类名称, camp_name as 训练营名称, agent_group as "Agent期数", agent_desc as "Agent描述", agent_target_recep as "Agent目标人服比", period_group as 期数分组, period_name as 期数名称, period_id as "期数ID", period_progress as 期数进度, sale_progress as 销转进度, camp_start_time::date as 开营日期, camp_end_time::date as 结营日期, sales_conversion_time::date as 销转日期, day_num as 销转进度序号, rn as 排序,
        count(distinct sale_after_sys_user_name) as 售后接待数量, count(1) as 承接人数, sum(is_recep) as 接待人数, sum(is_refund) as 退费人数, sum(is_change_period_out) as 延期人数,
        sum(is_repurchase) as 复购人数, sum(is_main_rep) as 复购主链路人数, sum(is_back_rep) as 复购回捞课人数, sum(order_money) as 复购流水,
        sum(sum(is_repurchase)) over(partition by period_id order by day_num) as 累计复购人数,
        sum(sum(is_main_rep)) over(partition by period_id order by day_num) as 累计复购主链路人数,
        sum(sum(is_back_rep)) over(partition by period_id order by day_num) as 累计回捞课人数,
        sum(sum(order_money)) over(partition by period_id order by day_num) as 累计复购流水
    from t_main group by 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
)
,res2 as (
    select 品类名称, 训练营名称, "Agent期数", "Agent描述", "Agent目标人服比", 期数分组, 期数名称, 期数进度, 销转进度, 开营日期::text, 结营日期::text, 销转日期::text, 承接人数, 接待人数, 售后接待数量, 累计复购人数, 累计复购主链路人数, 累计回捞课人数, 累计复购流水,
        承接人数 / 售后接待数量 as 人服比, 累计复购流水::bigint / 售后接待数量 as 人效, round(累计复购人数 * 1.0 / 承接人数, 4) as 累计复购率, round(累计复购主链路人数 * 1.0 / 承接人数, 4) as 累计主链路复购率, round(累计回捞课人数 * 1.0 / 承接人数, 4) as 累计回捞课复购率
    from res
    where case when "Agent期数" is not null then 销转日期 + 销转进度序号 - 1 = current_date else 排序 <= 3 and 销转进度 in (select 销转进度 from res where "Agent期数" is not null and 销转日期 + 销转进度序号 - 1 = current_date) end
)
select '期数-明细' as 数据分组, * from res2
union
select '往期大盘-汇总', 品类名称, 训练营名称, null::text, null::text, null::text, 期数分组, string_agg(期数名称, ',' order by 结营日期 desc), string_agg(期数进度, ',' order by 结营日期 desc), string_agg(销转进度, ',' order by 结营日期 desc), string_agg(开营日期::text, ',' order by 结营日期 desc), string_agg(结营日期::text, ',' order by 结营日期 desc), string_agg(销转日期::text, ',' order by 结营日期 desc), sum(承接人数), sum(接待人数), sum(售后接待数量), sum(累计复购人数), sum(累计复购主链路人数), sum(累计回捞课人数), sum(累计复购流水), sum(承接人数) / sum(售后接待数量), sum(累计复购流水::bigint) / sum(售后接待数量), round(sum(累计复购人数) * 1.0 / sum(承接人数), 4) as 累计复购率, round(sum(累计复购主链路人数) * 1.0 / sum(承接人数), 4) as 累计主链路复购率, round(sum(累计回捞课人数) * 1.0 / sum(承接人数), 4) as 累计回捞课复购率
from res2 where 期数分组 = '往期大盘' group by 1,2,3,4,5,6,7
