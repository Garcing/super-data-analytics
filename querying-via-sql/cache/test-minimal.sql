-- Test minimal query to isolate the null field name issue
with t_period as (
    select * from (values
        ('蜕变第11A期26-0419', '对照期数', 'Agent第一期'),
        ('蜕变第十一期26-0419', '实验期数', 'Agent第一期'),
        ('蜕变第16A期26-0606', '实验期数', 'Agent第二期'),
        ('蜕变第十六期26-0606', '对照期数', 'Agent第二期'),
        ('蜕变第十七期26-0611', '混合期数', 'Agent第二期')
    ) as t(period_name, period_group, agent_group)
)
select period_name, period_group, agent_group from t_period limit 5
