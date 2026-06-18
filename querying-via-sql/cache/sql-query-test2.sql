with t as (
    select 'a' as x, null::text as y
    union all
    select 'b', null::text
)
select x, y from t