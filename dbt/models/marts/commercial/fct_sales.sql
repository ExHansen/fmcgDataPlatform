{#
  Sell-out (tertiary): 1 baris = 1 toko x 1 produk x 1 hari. Baris harga outlier dikarantina (ops.quarantine_*).
  Incremental: ganti seluruh tanggal yang muncul di batch (delete+insert), lookback 14 hari
  untuk menampung file POS yang telat / dikirim ulang. Data lebih lama -> --full-refresh.
#}
{{ config(materialized='incremental', unique_key=['date_key'], incremental_strategy='delete+insert',
          on_schema_change='fail') }}

with s as (
    select *
    from {{ ref('int_sellout_mapped') }}
    where not is_price_outlier
    {% if is_incremental() %}
      and sales_date >= (select max(sales_date) - 14 from {{ this }})
    {% endif %}
),

lines as (
    select
        s.*,
        coalesce(p.product_key, '-1')       as product_key,
        coalesce(pr.promotion_key, '-1')    as promotion_key
    from s
    {{ scd2_join('dim_product', 'p', 'sku_id', 's.sku_id', 's.sales_date') }}
    left join {{ ref('dim_promotion') }} pr
        on pr.retailer_code = s.retailer_code and pr.sku_id = s.sku_id and pr.start_date = s.week_start_date
)

select
    to_char(sales_date, 'YYYYMMDD')                             as date_key,
    sales_date,
    product_key,
    {{ store_key('store_id') }}                                 as store_key,
    max(promotion_key)                                          as promotion_key,
    sum(qty) filter (where not is_return)                       as units_sold,
    coalesce(-sum(qty) filter (where is_return), 0)             as units_returned,
    sum(gross_sales) filter (where not is_return)               as gross_sales_value,
    sum(discount) filter (where not is_return)                  as discount_value,
    sum(net_sales) filter (where not is_return)                 as net_sales_value,
    coalesce(-sum(net_sales) filter (where is_return), 0)       as returned_value,
    max(retailer_code)                                          as source_retailer,
    max(received_at)                                            as received_at
from lines
group by 1, 2, 3, 4
