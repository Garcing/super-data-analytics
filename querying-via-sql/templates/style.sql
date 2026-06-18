-- ═══════════════════════════════════════════════════
-- SQL 编写风格指南（Hologres / PostgreSQL）
-- ═══════════════════════════════════════════════════

-- 1. 关键字和函数小写，表名/字段名保持原始大小写
-- 2. 子查询用 with (cte) 代替嵌套，提高可读性
-- 3. 每个查询必须带 limit，防止返回过多数据，默认 1000
-- 4. 字符串用单引号，字段和表别名不可忽略 as
-- 5. 字段别名存在特殊符号时加双引号
-- 6. 除了 select 要另起一行，其他关键字直接跟在后面
-- 7. select 的字段把逗号放在前面，第一个字段空一格对齐
-- 8. 表别名依次用a-z，每次子查询重新从a开始
-- 9. where 后面先用 1=1 占位，然后每个条件另起一行
-- 10. group by 和 order by 的字段用数字表示


-- ═══ 示例 ═══
with daily_stats as (
    select
         a.dt
        ,b.user_level
        ,count(distinct a.user_id) as dau
    from dw_user.user_detail as a 
    left join dw_user.user_level as b on a.user_id = b.user_id 
    where 1=1
        and a.dt between '2026-05-01' and '2026-05-10'
        and b.user_level in (1,2,3)
    group by 1,2
    having count(distinct a.user_id) > 100
)

select
     dt
    ,user_level
    ,dau
    ,dau - lag(dau) over(order by dt) as dau_diff
from daily_stats
order by 1,2
limit 100

