SELECT '2026-05-28'::date - '2026-05-11'::date + 1 as max_day_num
-- camp_end: 2026-05-28, sales_conversion: 2026-05-11, max day_num = 18
-- today is 2026-05-29, day_num 19 > 18, so no data
