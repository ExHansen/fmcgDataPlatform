-- PLAN 2.7 #6: numeric distribution = % toko aktif yang menjual SKU dalam 4 minggu terakhir.
with last4 as (
    select * from {{ ref('fct_sales') }}
    where sales_date > (select max(sales_date) - 28 from {{ ref('fct_sales') }}) and units_sold > 0
),

active_stores as (
    select count(distinct store_key) as n from last4
)

select
    p.brand,
    p.sku_id,
    p.product_name,
    count(distinct l.store_key)                                         as stores_selling,
    round(100.0 * count(distinct l.store_key) / (select n from active_stores), 1) as numeric_distribution_pct,
    sum(l.units_sold)                                                   as units_4w
from last4 l
join {{ ref('dim_product') }} p using (product_key)
group by 1, 2, 3
order by units_4w desc
limit 15
