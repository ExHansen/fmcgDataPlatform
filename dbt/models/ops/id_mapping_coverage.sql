{#
  Cakupan mapping per sumber: % ID dan % nilai penjualan yang sudah punya ID kanonik.
  Nilai penjualan lebih bermakna daripada jumlah ID: 1 SKU baru yang belum ter-mapping
  tidak sama pentingnya dengan 1 toko besar yang belum ter-mapping.
#}
with secondary as (
    select 'DMS' as source_type, distributor_code as source_entity, net_value as value,
           sku_id is not null as product_mapped, store_id is not null as store_mapped,
           distributor_customer_id is not null as customer_mapped
    from {{ ref('int_secondary_sales_mapped') }}
),

sellout as (
    select 'POS', retailer_code, net_sales, sku_id is not null, store_id is not null, true
    from {{ ref('int_sellout_mapped') }}
    where not is_return
),

lines as (
    select * from secondary
    union all
    select * from sellout
),

by_value as (
    select source_type, source_entity, 'PRODUCT' as entity_type,
           sum(value) as value_total, sum(value) filter (where product_mapped) as value_mapped
    from lines group by 1, 2
    union all
    select source_type, source_entity, 'STORE', sum(value), sum(value) filter (where store_mapped)
    from lines group by 1, 2
    union all
    select source_type, source_entity, 'CUSTOMER', sum(value), sum(value) filter (where customer_mapped)
    from lines where source_type = 'DMS' group by 1, 2
)

select
    source_type,
    source_entity,
    entity_type,
    value_total,
    coalesce(value_mapped, 0)                                           as value_mapped,
    round(100.0 * coalesce(value_mapped, 0) / nullif(value_total, 0), 2) as pct_value_mapped,
    {{ var('mapping_coverage_min_pct') }}                               as threshold_pct
from by_value
