{#
  Input forecasting (PLAN 2.8): 1 baris = SKU x region x minggu (hanya minggu lengkap, Senin-Minggu).
  Minggu tanpa penjualan tidak ada di sini; zero-filling dilakukan di forecasting/ per seri.
  Fitur harga/promo disertakan untuk analisis, tapi TIDAK dipakai model: nilainya untuk minggu
  depan belum diketahui (rencana promo dari CRM belum ada di MVP).
#}
with complete_weeks as (
    select
        case when extract(isodow from min(sales_date)) = 1 then min(sales_date)
             else date_trunc('week', min(sales_date))::date + 7 end    as first_week,
        date_trunc('week', max(sales_date) + 1)::date - 7               as last_week
    from {{ ref('fct_sales') }}
),

weekly as (
    select
        d.week_start_date,
        p.sku_id,
        st.region,
        max(p.category)                                         as category,
        max(p.brand)                                            as brand,
        sum(f.units_sold)                                       as units,
        sum(f.net_sales_value)                                  as net_sales,
        sum(f.net_sales_value) / nullif(sum(f.units_sold), 0)   as avg_price,
        count(distinct f.store_key) filter (where f.units_sold > 0) as stores_selling,
        count(*) filter (where f.promotion_key <> '-1')         as promo_store_days,
        bool_or(d.is_holiday)                                   as has_holiday
    from {{ ref('fct_sales') }} f
    join {{ ref('dim_date') }} d on d.date_key = f.date_key
    join {{ ref('dim_product') }} p on p.product_key = f.product_key
    join {{ ref('dim_store') }} st on st.store_key = f.store_key
    where p.sku_id <> 'UNKNOWN'
      and d.week_start_date between (select first_week from complete_weeks) and (select last_week from complete_weeks)
    group by 1, 2, 3
)

select
    *,
    max(avg_price) over (partition by sku_id, region order by week_start_date
                         rows between 8 preceding and 1 preceding)  as regular_price_8w,
    avg_price / nullif(max(avg_price) over (partition by sku_id, region order by week_start_date
                         rows between 8 preceding and 1 preceding), 0) as price_ratio,
    extract(week from week_start_date)::int                          as week_of_year
from weekly
