{#
  Kelengkapan laporan POS: toko yang aktif (punya penjualan) di minggu sebelum dan sesudahnya,
  tapi tidak ada satu baris pun di minggu ini = MISSING (toko tidak lapor).
#}
with weeks as (
    select distinct week_start_date from {{ ref('stg_pos__sellout') }}
),

store_weeks as (
    select store_code, week_start_date, count(*) as lines, sum(qty) filter (where not is_return) as units
    from {{ ref('stg_pos__sellout') }}
    group by 1, 2
),

stores as (
    select store_code, min(week_start_date) as first_week, max(week_start_date) as last_week
    from store_weeks group by 1
)

select
    s.store_code                                    as store_id,
    w.week_start_date,
    case when sw.store_code is null then 'MISSING' else 'RECEIVED' end as status,
    coalesce(sw.lines, 0)                           as lines,
    coalesce(sw.units, 0)                           as units
from stores s
join weeks w on w.week_start_date between s.first_week and s.last_week
left join store_weeks sw on sw.store_code = s.store_code and sw.week_start_date = w.week_start_date
