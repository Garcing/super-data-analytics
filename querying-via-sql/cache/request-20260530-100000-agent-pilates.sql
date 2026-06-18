WITH
t_period AS (
    SELECT * FROM (VALUES
        ('蜕变第11A期26-0419', '对照期数', 'Agent第一期'),
        ('蜕变第十一期26-0419', '实验期数', 'Agent第一期')
    ) AS t(period_name, period_group, agent_group)
)
,t_agent_desc AS (
    SELECT 'Agent第一期' AS agent_group, '验证运营策略、熟悉产品/用户画像' AS agent_desc, '1:120' AS agent_target_recep
    UNION
    SELECT 'Agent第二期', 'AI上新首版：Agent接量期/W1 SOP；AI外呼、360画像/问答、AI点评；MA接量期+W1/2，被动应答接量期+W1', '1:70'
    UNION
    SELECT 'Agent第三期', 'AI迭代优化版：Agent接量期/W1 SOP；新增智群管家；MA扩展至W1/2/3/4，被动应答接量期+W1/2', '1:150'
    UNION
    SELECT 'Agent第四期', 'Agent接量期/W1-W3 SOP迭代；AI工具同测试3期；MA接量期+W1/2/3/4，被动应答接量期+W1/2/3/4', '1:180'
)
,t_link AS (
    SELECT a.category_name, a.camp_name, a.period_name, a.period_id, COALESCE(b.period_group, '往期大盘') AS period_group, b.agent_group, a.camp_start_time, a.camp_end_time,
        CASE WHEN current_date > camp_end_time THEN his_sale_after_sys_user_name ELSE sale_after_sys_user_name END AS sale_after_sys_user_name,
        a.user_id, 1 AS is_recep, CASE WHEN permissions_status = 'Y' AND retain_scope = '否' THEN 0 ELSE 1 END AS is_refund, 0 AS is_change_period_out
    FROM xqd_data_analysis.ads_xqd_service_after_sales_recep_details_hour_bi_all AS a
    LEFT JOIN t_period AS b ON a.period_name = b.period_name
    WHERE a.order_id IS NOT NULL AND a.camp_name = '25天普拉提瘦身蜕变营' AND sale_after_rn = 1
    UNION ALL
    SELECT a.category_name, a.old_camp_name, a.old_period_name, a.old_period_id, period_group, agent_group, old_camp_start_time, old_camp_end_time, old_sale_after_sys_user_name,
        a.user_id, 0 AS is_recep, 0 AS is_refund, 1 AS is_change_period_out
    FROM xqd_data_analysis.ads_xqd_platform_stu_mana_change_period_class_detail_hour_bi_all AS a
    JOIN t_period AS b ON a.old_period_name = b.period_name
    WHERE camp_start_time > old_camp_start_time AND change_period_type = '换期' AND (censor_change_period_type IS NULL OR censor_change_period_type <> '插班上课') AND a.old_camp_name = '25天普拉提瘦身蜕变营'
)
,t_window AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY period_id, user_id ORDER BY is_recep DESC) AS period_rn, COUNT(1) OVER(PARTITION BY period_id, sale_after_sys_user_name) AS sale_after_recep_num
    FROM t_link
)
,t_link_n AS (
    SELECT a.*, b.sales_conversion_time,
        CASE WHEN current_date < camp_start_time::date THEN '开营前第' || (camp_start_time::date - current_date) || '天'
            WHEN current_date = camp_start_time::date THEN '开营日'
            WHEN current_date > camp_start_time::date AND current_date < sales_conversion_time::date THEN '开营后第' || (current_date - camp_start_time::date) || '天'
            WHEN current_date = sales_conversion_time::date THEN '前置销转日'
            WHEN current_date > sales_conversion_time::date AND current_date < camp_end_time::date - 10 THEN '前置销转后第' || (current_date - sales_conversion_time::date) || '天'
            WHEN current_date = camp_end_time::date - 10 THEN '结营日'
            WHEN current_date > camp_end_time::date - 10 THEN '结营后第' || (current_date - camp_end_time::date) || '天'
            ELSE '未知状态' END AS cur_period_progress,
        CASE WHEN b.sales_conversion_time::date + c.day_num - 1 >= sales_conversion_time::date AND b.sales_conversion_time::date + c.day_num - 1 < camp_end_time::date - 10 THEN '前置期'
            WHEN b.sales_conversion_time::date + c.day_num - 1 = camp_end_time::date - 10 THEN '结营日'
            WHEN b.sales_conversion_time::date + c.day_num - 1 > camp_end_time::date - 10 THEN 'T+10'
            ELSE '未知状态' END AS period_progress,
        '销转第' || LPAD(c.day_num::text, 2, '0') || '天' AS sale_progress, c.day_num, d.agent_desc, d.agent_target_recep,
        DENSE_RANK() OVER(PARTITION BY a.camp_name ORDER BY d.agent_group IS NULL DESC, a.camp_end_time < current_date DESC, camp_end_time DESC) AS rn
    FROM t_window AS a
    JOIN xqd_data_analysis.dim_xqd_course_period_hf AS b ON a.period_id = b.period_id
    JOIN (SELECT generate_series(1, 100) AS day_num) c ON c.day_num <= (a.camp_end_time::date - b.sales_conversion_time::date + 1) AND (b.sales_conversion_time::date + c.day_num - 1) <= current_date
    LEFT JOIN t_agent_desc AS d ON a.agent_group = d.agent_group
    WHERE period_rn = 1 AND sale_after_recep_num > 10
)
,t_main AS (
    SELECT a.category_name, a.camp_name, a.period_name, a.period_id, a.cur_period_progress, a.period_progress, a.sale_progress, a.period_group, a.agent_group, a.agent_desc, a.agent_target_recep,
        a.camp_start_time, a.camp_end_time, a.sales_conversion_time, a.sale_after_sys_user_name, a.user_id, a.is_recep, a.is_refund, a.is_change_period_out, a.day_num, a.rn,
        CASE WHEN COUNT(b.sku_name) > 0 THEN 1 ELSE 0 END AS is_repurchase,
        CASE WHEN COUNT(b.sku_name) FILTER(WHERE b.order_source_name = '直播间成单') > 0 THEN 1 ELSE 0 END AS is_live_repurchase,
        CASE WHEN COUNT(b.sku_name) FILTER(WHERE b.order_source_name = '社群跟单') > 0 THEN 1 ELSE 0 END AS is_group_repurchase,
        CASE WHEN COUNT(1) FILTER(WHERE b.sku_name = '35天普拉提骨态轻龄营') > 0 THEN 1 ELSE 0 END AS is_main_rep,
        CASE WHEN COUNT(1) FILTER(WHERE b.sku_name IN ('普拉提骨态轻龄轻量营', '普拉提骨态轻龄精练营')) > 0 THEN 1 ELSE 0 END AS is_back_rep,
        COALESCE(SUM(b.order_money - COALESCE(b.refund_money, 0)), 0) AS order_money
    FROM t_link_n AS a
    LEFT JOIN xqd_data_analysis.ads_xqd_revenue_ord_all_order_detail_bi AS b ON a.user_id = b.user_id AND a.is_recep = 1 AND b.order_status IN ('已支付', '已退款')
        AND a.day_num = (b.order_time::date - a.sales_conversion_time::date + 1)
        AND (a.camp_name = '25天普拉提瘦身蜕变营' AND b.sku_name IN ('35天普拉提骨态轻龄营', '普拉提骨态轻龄轻量营', '普拉提骨态轻龄精练营'))
    GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21
)
,res AS (
    SELECT category_name AS 品类名称, camp_name AS 训练营名称, agent_group AS "Agent期数", agent_desc AS "Agent描述", agent_target_recep AS "Agent目标人服比",
        period_group AS 期数分组, period_name AS 期数名称, period_id AS "期数ID", cur_period_progress AS 最新期数进度, period_progress AS 期数进度,
        sale_progress AS 销转进度, camp_start_time::date AS 开营日期, camp_end_time::date AS 结营日期, sales_conversion_time::date AS 销转日期, day_num AS 销转进度序号, rn AS 排序,
        COUNT(DISTINCT sale_after_sys_user_name) AS 售后接待数量, COUNT(1) AS 承接人数, SUM(is_recep) AS 接待人数, SUM(is_refund) AS 退费人数, SUM(is_change_period_out) AS 延期人数,
        SUM(is_repurchase) AS 复购人数, SUM(is_main_rep) AS 复购主链路人数, SUM(is_back_rep) AS 复购回捞课人数, SUM(order_money) AS 复购流水,
        SUM(SUM(is_repurchase)) OVER(PARTITION BY period_id ORDER BY day_num) AS 累计复购人数,
        SUM(SUM(is_main_rep)) OVER(PARTITION BY period_id ORDER BY day_num) AS 累计复购主链路人数,
        SUM(SUM(is_back_rep)) OVER(PARTITION BY period_id ORDER BY day_num) AS 累计复购回捞课人数,
        SUM(SUM(order_money)) OVER(PARTITION BY period_id ORDER BY day_num) AS 累计复购流水,
        SUM(SUM(is_live_repurchase)) OVER(PARTITION BY period_id ORDER BY day_num) AS 累计直播间复购人数,
        SUM(SUM(is_group_repurchase)) OVER(PARTITION BY period_id ORDER BY day_num) AS 累计社群复购人数,
        SUM(SUM(is_repurchase) FILTER(WHERE period_progress = '前置期')) OVER(PARTITION BY period_id ORDER BY day_num) AS 累计前置期复购人数,
        SUM(SUM(is_repurchase) FILTER(WHERE period_progress = '结营日')) OVER(PARTITION BY period_id ORDER BY day_num) AS 累计结营日复购人数,
        SUM(SUM(is_repurchase) FILTER(WHERE period_progress = 'T+10')) OVER(PARTITION BY period_id ORDER BY day_num) AS "累计T+10复购人数"
    FROM t_main GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16
)
,res2 AS (
    SELECT 品类名称, 训练营名称, "Agent期数", "Agent描述", "Agent目标人服比", 期数分组, 期数名称, 最新期数进度 AS 期数进度, 销转进度, 开营日期::text, 结营日期::text, 销转日期::text,
        承接人数, 接待人数, 复购人数, 复购流水, 售后接待数量, 累计复购人数, 累计复购主链路人数, 累计复购回捞课人数, 累计直播间复购人数, 累计社群复购人数,
        累计前置期复购人数, 累计结营日复购人数, "累计T+10复购人数", 累计复购流水,
        承接人数 / 售后接待数量 AS 人服比, 累计复购流水::bigint / 售后接待数量 AS 人效,
        ROUND(累计复购人数 * 1.0 / 承接人数, 4) AS 累计复购率,
        ROUND(累计复购主链路人数 * 1.0 / 承接人数, 4) AS 累计主链路复购率,
        ROUND(累计复购回捞课人数 * 1.0 / 承接人数, 4) AS 累计回捞课复购率,
        ROUND(累计直播间复购人数 * 1.0 / 承接人数, 4) AS 累计直播间复购率,
        ROUND(累计社群复购人数 * 1.0 / 承接人数, 4) AS 累计社群复购率,
        ROUND(累计前置期复购人数 * 1.0 / 承接人数, 4) AS 累计前置期复购率,
        ROUND(累计结营日复购人数 * 1.0 / 承接人数, 4) AS 累计结营日复购率,
        ROUND("累计T+10复购人数" * 1.0 / 承接人数, 4) AS "累计T+10复购率"
    FROM res
    WHERE CASE WHEN "Agent期数" IS NOT NULL THEN 销转日期 + 销转进度序号 - 1 = current_date
        ELSE 排序 <= 3 AND 销转进度 IN (SELECT 销转进度 FROM res WHERE "Agent期数" IS NOT NULL AND 销转日期 + 销转进度序号 - 1 = current_date) END
)
SELECT '期数-明细' AS 数据分组, * FROM res2 WHERE "Agent期数" IS NOT NULL
UNION
SELECT '往期大盘-汇总', 品类名称, 训练营名称, null::text, null::text, null::text, 期数分组,
    STRING_AGG(期数名称, ',' ORDER BY 结营日期 DESC), STRING_AGG(期数进度, ',' ORDER BY 结营日期 DESC), STRING_AGG(销转进度, ',' ORDER BY 结营日期 DESC),
    STRING_AGG(开营日期::text, ',' ORDER BY 结营日期 DESC), STRING_AGG(结营日期::text, ',' ORDER BY 结营日期 DESC), STRING_AGG(销转日期::text, ',' ORDER BY 结营日期 DESC),
    SUM(承接人数), SUM(接待人数), SUM(复购人数), SUM(复购流水), SUM(售后接待数量), SUM(累计复购人数), SUM(累计复购主链路人数), SUM(累计复购回捞课人数),
    SUM(累计直播间复购人数), SUM(累计社群复购人数), SUM(累计前置期复购人数), SUM(累计结营日复购人数), SUM("累计T+10复购人数"), SUM(累计复购流水),
    SUM(承接人数) / SUM(售后接待数量), SUM(累计复购流水::bigint) / SUM(售后接待数量),
    ROUND(SUM(累计复购人数) * 1.0 / SUM(承接人数), 4), ROUND(SUM(累计复购主链路人数) * 1.0 / SUM(承接人数), 4), ROUND(SUM(累计复购回捞课人数) * 1.0 / SUM(承接人数), 4),
    ROUND(SUM(累计直播间复购人数) * 1.0 / SUM(承接人数), 4), ROUND(SUM(累计社群复购人数) * 1.0 / SUM(承接人数), 4),
    ROUND(SUM(累计前置期复购人数) * 1.0 / SUM(承接人数), 4), ROUND(SUM(累计结营日复购人数) * 1.0 / SUM(承接人数), 4), ROUND(SUM("累计T+10复购人数") * 1.0 / SUM(承接人数), 4)
FROM res2 WHERE 期数分组 = '往期大盘' GROUP BY 1,2,3,4,5,6,7
