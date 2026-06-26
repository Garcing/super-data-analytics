with
/*
 作用: 提取指定表的所有主键字段信息
 这里直接绕过兼容层，查底层 constraint 约束表，并通过 any(a.conkey) 阵列匹配出真实的物理挂载主键，100% 准确
 */
pk_info as (
    select
        c.nspname as table_schema,
        b.relname as table_name,
        d.attname as column_name
    from
        pg_constraint as a
        join pg_class as b on a.conrelid = b.oid
        join pg_namespace as c on b.relnamespace = c.oid
        join pg_attribute as d on d.attrelid = b.oid
        and d.attnum = any(a.conkey)
    where
        a.contype = 'p'
)
/*
 作用: 提取指定表的所有字段中文注释
 条件 a.attnum > 0 且 not a.attisdropped 用于过滤掉系统隐藏列和已删除的废弃列
 */
,
comm_info as (
    select
        c.nspname as table_schema,
        b.relname as table_name,
        a.attname as column_name,
        d.description as column_comment
    from
        pg_attribute as a
        join pg_class as b on a.attrelid = b.oid
        join pg_namespace as c on b.relnamespace = c.oid
        join pg_description as d on d.objoid = b.oid
        and d.objsubid = a.attnum
    where
        a.attnum > 0
        and not a.attisdropped
) -- information_schema.columns 为核心主表驱动，保证全量字段不丢失。
select
    a.ordinal_position as 序号,
    a.column_name as 字段名,
    a.data_type as 数据类型,
    a.column_default as 默认值,
    a.is_nullable as 是否允许为空,
case
        when b.column_name is not null then 'YES'
        else 'NO'
    end as 是否为主键,
    c.column_comment as 字段注释
from
    information_schema.columns as a
    left join pk_info as b on a.table_schema = b.table_schema
    and a.table_name = b.table_name
    and a.column_name = b.column_name
    left join comm_info as c on a.table_schema = c.table_schema
    and a.table_name = c.table_name
    and a.column_name = c.column_name
where
    a.table_schema = 'schema_name'
    and a.table_name = 'table_name'
order by
    a.ordinal_position;