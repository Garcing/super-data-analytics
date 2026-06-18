-- Test UNION with null columns
select 'a' as c1, 'x' as c2, null::text as c3
union all
select 'b', 'y', null::text
