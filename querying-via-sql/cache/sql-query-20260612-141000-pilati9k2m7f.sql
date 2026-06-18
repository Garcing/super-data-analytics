/*
 35天普拉提骨态轻龄营
 2180-普拉提骨态轻龄轻量营
1380-普拉提骨态轻龄精练营
 */



with
-- Agent项目关联期数
t_period as (
    select * from (values
        ('蜕变第11A期26-0419', '对照期数', 'Agent第一期'),
        ('蜕变第十一期26-0419', '实验期数', 'Agent第一期'),
        ('蜕变第16A期26-0606', '实验期数', 'Agent第二期'),
        ('蜕变第十六期26-0606', '对照期数', 'Agent第二期'),
        ('蜕变第十七期26-0611', '混合期数', 'Agent第二期')
    ) as t(period_name, period_group, agent_group)
)

-- Agent项目关联功能和人服比
,t_agent_desc as (
    select
        'Agent第一期' as agent_group,
        '验证运营策略、熟悉产品/用户画像' as agent_desc,
        '1:120' as agent_target_recep
    union
    select
        'Agent第二期',
        'AI上新首版：Agent接量期/W1 SOP；AI外呼、360画像/问答、AI点评；MA接量期+W1/2，被动应答接量期+W1',
        '1:70'
    union
    select
        'Agent第三期',
        'AI迭代优化版：Agent接量期/W1 SOP；新增智群管家；MA接量期+W1/2/3/4，被动应答接量期+W1/2',
        '1:150'
    union
    select
        'Agent第四期',
        'Agent接量期/W1-W3 SOP迭代；AI工具同测试3期；MA接量期+W1/2/3/4，被动应答接量期+W1/2/3/4',
        '1:180'

)

-- 拼接链路表
,t_link as (
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
    where
        1=1
        and a.order_id is not null
        and a.camp_name = '25天普拉提瘦身蜕变营'
        and sale_after_rn = 1
        and camp_start_time >= '2026-04-01'

    union all

    select
         null::text
        ,a.category_name
        ,a.old_camp_name
        ,a.old_period_name
        ,a.old_period_id
        ,coalesce(b.period_group, '往期大盘')
        ,agent_group
        ,null::text
        ,old_camp_start_time
        ,old_camp_end_time
        ,old_sale_after_sys_user_name
        ,a.user_id
        ,0 as is_recep
        ,0 as is_refund
        ,1 as is_change_period_out
    from xqd_data_analysis.ads_xqd_platform_stu_mana_change_period_class_detail_hour_bi_all as a
    left join t_period as b on a.old_period_name = b.period_name
    where 1=1
        and old_camp_start_time >= '2026-04-01'
        and camp_start_time > old_camp_start_time
        and change_period_type = '换期'
        and (censor_change_period_type is null or censor_change_period_type <> '插班上课')
        and a.old_camp_name = '25天普拉提瘦身蜕变营'
)


-- 窗口函数实现异常值过滤
-- 第一是 period_id x user_id 分组下去重，第二是承接人数要大于 10
,t_window as (
    select
         *
        ,row_number() over(partition by period_id, user_id order by is_recep desc) as period_rn
        ,count(1) over(partition by period_id, sale_after_sys_user_name) as sale_after_recep_num
    from t_link
)


-- 将明细膨胀到营期天数的倍数
,t_link_n as (
    select
          a.*
         ,b.sales_conversion_time

         -- 相对本日 期数所处状态
         ,case
            when current_date < camp_start_time::date then '开营前第' || (camp_start_time::date - current_date) || '天'
            when current_date >= camp_start_time::date and current_date < sales_conversion_time::date then '开营第' || (current_date - camp_start_time::date + 1) || '天'
            when current_date = sales_conversion_time::date then '前置销转日'
            when current_date > sales_conversion_time::date and current_date < camp_end_time::date - 10 then '前置销转后第' || (current_date - sales_conversion_time::date) || '天'
            when current_date = camp_end_time::date - 10 then '结营日'
            when current_date > camp_end_time::date - 10 then '结营后第' || (current_date - camp_end_time::date + 10) || '天'
            else '报错'
          end as cur_period_progress

        -- 相对实际代表那日 期数所处状态（区间）
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

         ,c.day_num
         ,d.agent_desc
         ,d.agent_target_recep
         ,dense_rank() over(
            partition by a.camp_name
            order by
                d.agent_group is null desc,
                a.camp_end_time < current_date desc,
                camp_end_time desc
          ) as rn

    from t_window as a
    join xqd_data_analysis.dim_xqd_course_period_hf as b on a.period_id = b.period_id
    join (select generate_series(1, 100) as day_num) c
        on c.day_num <= (a.camp_end_time::date - a.camp_start_time::date + 1)
        and (a.camp_start_time::date + c.day_num - 1) <= current_date
    left join t_agent_desc as d on a.agent_group = d.agent_group
    where
        period_rn = 1 and sale_after_recep_num > 10
)


,t_link_sub as (
    select
         period_id
        ,day_num
        ,camp_start_time::date + day_num -1 as act_date
        ,count(1) as user_num
    from t_link_n
    group by 1,2,3
)

-- 过程数据补充在此
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

,t_question as (
    select
         period_id
        ,day_num
        ,sum(question_num) as question_fenzi
        ,max(user_num) * count(questionnaire_name) as question_fenmu
        ,json_object_agg(
            questionnaire_name,
            round((question_num * 1.0 / user_num), 4)
            order by question_visit_create_time
         ) as question_rate_dict
    from (
        select
             a.period_id
            ,a.day_num
            ,a.user_num
            ,b.questionnaire_name
            ,min(b.question_visit_create_time) as question_visit_create_time
            ,count(distinct b.user_id) as question_num
        from t_link_sub as a
        left join xqd_data_analysis.ads_xqd_platform_question_user_questionnaire_detail_hour_bi_all as b
            on a.period_id = b.period_id
            and b.question_visit_create_time::date <= act_date
            and b.question_visit_create_time < now()
        group by 1,2,3,4
    ) as t
    group by 1,2
)


,t_clock as (
    select
         period_id
        ,day_num
        ,sum(clock_num) as clock_fenzi
        ,max(user_num) * count(clock_task_name) as clock_fenmu
        ,json_object_agg(
            clock_task_name,
            round((clock_num * 1.0 / user_num), 4)
            order by clock_time
         ) as clock_rate_dict
    from (
        select
             a.period_id
            ,a.day_num
            ,a.user_num
            ,b.clock_task_name
            ,min(b.clock_time) as clock_time
            ,count(distinct b.user_id) as clock_num
        from t_link_sub as a
        left join xqd_data_analysis.ads_xqd_study_user_clock_detail_hour_bi_all as b
            on a.period_id = b.period_id
            and b.clock_time::date <= act_date
            and b.clock_time < now()
        group by 1,2,3,4
    ) as t
    group by 1,2
)



-- 关联复购延期退费听课明细，此时还在膨胀状态
,t_main as (
    select
         a.order_id
        ,a.category_name
        ,a.camp_name
        ,a.period_name
        ,a.period_id
        ,a.cur_period_progress
        ,a.period_progress_sale_section
        ,a.period_progress
        ,a.period_group
        ,a.agent_group
        ,a.agent_desc
        ,a.agent_target_recep
        ,a.sale_after_wework_user_id
        ,a.camp_start_time
        ,a.camp_end_time
        ,a.sales_conversion_time
        ,a.sale_after_sys_user_name
        ,a.user_id
        ,a.is_recep
        ,a.is_refund
        ,a.is_change_period_out
        ,a.day_num
        ,a.rn
        ,max(b.charge_type) as repep_charge_type
        ,case when count(b.sku_name) > 0 then 1 else 0 end as is_repurchase
        ,case when count(b.sku_name) filter(where b.order_source_name = '直播间成单') > 0 then 1 else 0 end as is_live_repurchase
        ,case when count(b.sku_name) filter(where b.order_source_name = '社群跟单') > 0 then 1 else 0 end as is_group_repurchase
        ,case when count(1) filter(where b.sku_name = '35天普拉提骨态轻龄营') > 0 then 1 else 0 end is_main_rep
        ,case when count(1) filter(where b.sku_name in ('普拉提骨态轻龄轻量营', '普拉提骨态轻龄精练营')) > 0 then 1 else 0 end is_back_rep
        ,coalesce(sum(b.order_money - coalesce(b.refund_money, 0)), 0) as order_money

    from t_link_n as a
    -- 按支付时间把订单归属导具体的 day_num
    left join xqd_data_analysis.ads_xqd_revenue_ord_all_order_detail_bi as b
        on a.user_id = b.user_id
        and a.is_recep = 1
        and b.order_status in ('已支付', '已退款')
        and a.day_num = (b.order_time::date - a.camp_start_time::date + 1)
        and (
            (a.camp_name = '25天普拉提瘦身蜕变营' and b.sku_name in ('35天普拉提骨态轻龄营', '普拉提骨态轻龄轻量营', '普拉提骨态轻龄精练营'))
        )
    group by
        1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23
)


,res1 as (
    select
         category_name as 品类名称
        ,camp_name as 训练营名称
        ,agent_group as "Agent期数"
        ,agent_desc as "Agent描述"
        ,agent_target_recep as "Agent目标人服比"
        ,case
            when period_group = '混合期数' then
                case when period_name = '蜕变第十七期26-0611' and sale_after_sys_user_name = '周建峰' then '实验期数' else '对照期数' end
            else period_group
         end as 期数分组
        ,case
            when period_group = '混合期数' then
                case when period_name = '蜕变第十七期26-0611' and sale_after_sys_user_name = '周建峰' then period_name || '-周建峰' else period_name end
            else period_name
         end as 期数名称
        ,period_id as "期数ID"
        ,cur_period_progress as 最新期数进度
        ,period_progress as 实际期数进度
        ,period_progress_sale_section as 期数销转区间
        ,camp_start_time::date as 开营日期
        ,camp_end_time::date as 结营日期
        ,sales_conversion_time::date as 销转日期
        ,day_num as 开营天数序号
        ,rn as 排序

        ,count(distinct sale_after_sys_user_name) as 售后接待数量
        ,count(1) as 承接人数
        ,sum(is_recep) as 接待人数
        ,sum(is_refund) as 退费人数
        ,sum(is_change_period_out) as 延期人数

        ,sum(is_repurchase) as 复购人数
        ,sum(is_main_rep) as 复购主链路人数
        ,sum(is_back_rep) as 复购回捞课人数
        ,sum(order_money) as 复购流水

        ,sum(sum(is_repurchase)) over(partition by period_id order by day_num) as 累计复购人数
        ,sum(sum(is_main_rep)) over(partition by period_id order by day_num) as 累计复购主链路人数
        ,sum(sum(is_back_rep)) over(partition by period_id order by day_num) as 累计复购回捞课人数
        ,sum(sum(order_money)) over(partition by period_id order by day_num) as 累计复购流水

        ,sum(sum(is_live_repurchase)) over(partition by period_id order by day_num) as 累计直播间复购人数
        ,sum(sum(is_group_repurchase)) over(partition by period_id order by day_num) as 累计社群复购人数

        ,coalesce(sum(sum(is_repurchase) filter(where period_progress = '前置期')) over(partition by period_id order by day_num), 0) as 累计前置期复购人数
        ,coalesce(sum(sum(is_repurchase) filter(where period_progress = '结营日')) over(partition by period_id order by day_num), 0) as 累计结营日复购人数
        ,coalesce(sum(sum(is_repurchase) filter(where period_progress = 'T+10')) over(partition by period_id order by day_num), 0) as "累计T+10复购人数"
    from t_main
    group by 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16
)


,res2 as (
    select
         品类名称
        ,训练营名称
        ,"Agent期数"
        ,"Agent描述"
        ,"Agent目标人服比"
        ,期数分组
        ,实际期数进度
        ,期数名称
        ,最新期数进度
        ,期数销转区间
        ,开营日期::text
        ,结营日期::text
        ,销转日期::text
        ,承接人数
        ,接待人数
        ,复购人数
        ,复购流水
        ,售后接待数量
        ,累计复购人数
        ,累计复购主链路人数
        ,累计复购回捞课人数
        ,累计直播间复购人数
        ,累计社群复购人数
        ,累计前置期复购人数
        ,累计结营日复购人数
        ,"累计T+10复购人数"
        ,累计复购流水
        ,承接人数 / 售后接待数量 as 人服比
        ,累计复购流水::bigint / 售后接待数量 as 人效
        ,round(累计复购人数 * 1.0 / 承接人数, 4) as 累计复购率
        ,round(累计复购主链路人数 * 1.0 / 承接人数, 4) as 累计主链路复购率
        ,round(累计复购回捞课人数 * 1.0 / 承接人数, 4) as 累计回捞课复购率

        ,round(累计直播间复购人数 * 1.0 / 承接人数, 4) as 累计直播间复购率
        ,round(累计社群复购人数 * 1.0 / 承接人数, 4) as 累计社群复购率

        ,round(累计前置期复购人数 * 1.0 / 承接人数, 4) as 累计前置期复购率
        ,round(累计结营日复购人数 * 1.0 / 承接人数, 4) as 累计结营日复购率
        ,round("累计T+10复购人数" * 1.0 / 承接人数, 4) as "累计T+10复购率"

        -- 过程数据
        ,concat('"', 期数名称, '": ', b.finish_learn_rate_dict::text) as 完课率字典
        ,concat('"', 期数名称, '": ', c.question_rate_dict::text) as 问卷提交率字典
        ,concat('"', 期数名称, '": ', d.clock_rate_dict::text) as 打卡率字典

        -- 判断播报
        ,case when "Agent期数" is not null and 开营日期 + 开营天数序号 - 1 = current_date then '是' else '否' end as 是否播报期数

    from res1 as a
    left join t_learn as b on a."期数ID" = b.period_id and a.开营天数序号 = b.day_num
    left join t_question as c on a."期数ID" = c.period_id and a.开营天数序号 = c.day_num
    left join t_clock as d on a."期数ID" = d.period_id and a.开营天数序号 = d.day_num
    where

        -- 1. 核心播报期数，当天进度
        ("Agent期数" is not null and 开营日期 + 开营天数序号 - 1 = current_date) or
        -- 2. 往期Agent期数一并拿到
        ("Agent期数" is not null and 实际期数进度 in (
            select 实际期数进度
            from res1
            where "Agent期数" is not null and 开营日期 + 开营天数序号 - 1 = current_date
        )) or
        -- 3. 往期大盘只要3期
        (排序 <= 3 and 实际期数进度 in (
            select 实际期数进度
            from res1
            where "Agent期数" is not null and 开营日期 + 开营天数序号 - 1 = current_date
        ))
)



,res as (
    select '期数-明细' as 数据分组, * from res2 where "Agent期数" is not null
    union
    select
          '往期大盘-汇总'
         ,品类名称
         ,训练营名称
         ,null::text
         ,null::text
         ,null::text
         ,期数分组
         ,实际期数进度
         ,string_agg(期数名称, ',' order by 结营日期 desc)
         ,string_agg(最新期数进度, ',' order by 结营日期 desc)
         ,string_agg(期数销转区间, ',' order by 结营日期 desc)
         ,string_agg(开营日期::text, ',' order by 结营日期 desc)
         ,string_agg(结营日期::text, ',' order by 结营日期 desc)
         ,string_agg(销转日期::text, ',' order by 结营日期 desc)
         ,sum(承接人数)
         ,sum(接待人数)
         ,sum(复购人数)
         ,sum(复购流水)
         ,sum(售后接待数量)
         ,sum(累计复购人数)
         ,sum(累计复购主链路人数)
         ,sum(累计复购回捞课人数)
         ,sum(累计直播间复购人数)
         ,sum(累计社群复购人数)
         ,sum(累计前置期复购人数)
         ,sum(累计结营日复购人数)
         ,sum("累计T+10复购人数")
         ,sum(累计复购流水)
         ,sum(承接人数) / sum(售后接待数量)
         ,sum(累计复购流水::bigint) / sum(售后接待数量)
         ,round(sum(累计复购人数) * 1.0 / sum(承接人数), 4) as 累计复购率
         ,round(sum(累计复购主链路人数) * 1.0 / sum(承接人数), 4) as 累计主链路复购率
         ,round(sum(累计复购回捞课人数) * 1.0 / sum(承接人数), 4) as 累计回捞课复购率

         ,round(sum(累计直播间复购人数) * 1.0 / sum(承接人数), 4) as 累计直播间复购率
         ,round(sum(累计社群复购人数) * 1.0 / sum(承接人数), 4) as 累计社群复购率

         ,round(sum(累计前置期复购人数) * 1.0 / sum(承接人数), 4) as 累计前置期复购率
         ,round(sum(累计结营日复购人数) * 1.0 / sum(承接人数), 4) as 累计结营日复购率
         ,round(sum("累计T+10复购人数") * 1.0 / sum(承接人数), 4) as "累计T+10复购率"

         ,string_agg(完课率字典, ', ' order by 结营日期 desc)
         ,string_agg(问卷提交率字典, ', ' order by 结营日期 desc)
         ,string_agg(打卡率字典, ', ' order by 结营日期 desc)
         ,max('否')

    from res2
    where 期数分组 = '往期大盘'
    group by 1,2,3,4,5,6,7,8
)

select * from res