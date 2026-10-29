{#
  Promosi TERDETEKSI dari harga POS (MVP belum punya rencana promo dari CRM):
  1 promosi = retailer x SKU x minggu dengan harga jual rata-rata < 90% dari harga tertinggi
  8 minggu sebelumnya. Kolom source disiapkan untuk PLANNED/BOTH saat CRM ditambahkan.
#}
with weekly_price as (
    select retailer_code, sku_id, week_start_date,
           sum(net_sales) / nullif(sum(qty), 0) as avg_price
    from {{ ref('int_sellout_mapped') }}
    where not is_return and not is_price_outlier and sku_id is not null
    group by 1, 2, 3
),

with_ref as (
    select *,
        max(avg_price) over (partition by retailer_code, sku_id order by week_start_date
                             rows between 8 preceding and 1 preceding) as ref_price
    from weekly_price
),

detected as (
    select *, round(100 * (1 - avg_price / ref_price), 1) as discount_pct
    from with_ref
    where ref_price is not null and avg_price < 0.9 * ref_price
)

select
    {{ dbt_utils.generate_surrogate_key(['retailer_code', 'sku_id', 'week_start_date']) }} as promotion_key,
    retailer_code || '-' || sku_id || '-' || to_char(week_start_date, 'IYYY"W"IW') as promotion_id,
    null::text                  as crm_promotion_id,
    retailer_code,
    sku_id,
    'PRICE_DISCOUNT'            as promo_mechanic,
    discount_pct,
    week_start_date             as start_date,
    week_start_date + 6         as end_date,
    'DETECTED'                  as source
from detected

union all

select '-1', 'NO_PROMO', null, null, null, 'NONE', 0, null, null, 'NONE'
