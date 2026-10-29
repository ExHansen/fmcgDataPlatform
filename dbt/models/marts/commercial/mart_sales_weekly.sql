{# Sell-out mingguan per toko x produk, dengan atribut siap pakai untuk dashboard. #}
select
    d.week_start_date,
    d.iso_year_week,
    d.period_4w,
    f.store_key,
    st.store_id,
    st.retailer_name,
    st.store_format,
    st.region,
    st.distributor_code,
    f.product_key,
    p.sku_id,
    p.product_name,
    p.brand,
    p.category,
    sum(f.units_sold)                                       as units_sold,
    sum(f.units_returned)                                   as units_returned,
    sum(f.net_sales_value)                                  as net_sales_value,
    sum(f.gross_sales_value)                                as gross_sales_value,
    sum(f.discount_value)                                   as discount_value,
    count(*) filter (where f.promotion_key <> '-1')         as promo_days
from {{ ref('fct_sales') }} f
join {{ ref('dim_date') }} d on d.date_key = f.date_key
join {{ ref('dim_store') }} st on st.store_key = f.store_key
join {{ ref('dim_product') }} p on p.product_key = f.product_key
group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14
