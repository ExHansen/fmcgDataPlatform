-- PLAN 2.7 #1: tren sell-out per brand x region, minggu ini vs minggu lalu (4 minggu lengkap terakhir).
-- (Pembanding tahun lalu belum ada: data baru 1 tahun.)
with weekly as (
    select week_start_date, brand, region, sum(net_sales_value) as net_sales, sum(units_sold) as units
    from {{ ref('mart_sales_weekly') }}
    where week_start_date < date_trunc('week', (select max(sales_date) from {{ ref('fct_sales') }}) + 1)
    group by 1, 2, 3
)

select
    week_start_date, brand, region,
    round(net_sales / 1e6, 1)                                                       as net_sales_juta_idr,
    units,
    round(100.0 * (net_sales / nullif(lag(net_sales) over w, 0) - 1), 1)            as wow_pct
from weekly
window w as (partition by brand, region order by week_start_date)
order by week_start_date desc, net_sales desc
limit 24
