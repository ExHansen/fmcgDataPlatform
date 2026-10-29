{#
  Cross-reference toko. Toko modern trade: store_id kanonik = kode toko retailer (sudah berprefix retailer).
  Outlet di file distributor dicocokkan ke toko POS lewat nama ternormalisasi yang unik.
#}
with pos_stores as (
    select source_system, store_code, max(store_name) as store_name,
           min(sales_date) as first_seen, max(sales_date) as last_seen, count(*) as occurrences
    from {{ ref('stg_pos__sellout') }}
    group by 1, 2
),

store_names as (
    select {{ normalize_name('store_name') }} as name_key, min(store_code) as store_id
    from pos_stores
    group by 1
    having count(*) = 1
),

dms_outlets as (
    select source_system, outlet_code, max(outlet_name) as outlet_name,
           min(invoice_date) as first_seen, max(invoice_date) as last_seen, count(*) as occurrences
    from {{ ref('stg_dms__secondary_sales') }}
    group by 1, 2
)

select 'STORE' as entity_type, source_system, store_code as source_id, store_name as source_description,
       store_code as store_id, 'EXACT_KEY' as match_method, 1.00 as match_confidence,
       first_seen, last_seen, occurrences
from pos_stores

union all

select 'STORE', o.source_system, o.outlet_code, o.outlet_name,
       n.store_id, case when n.store_id is not null then 'NORMALIZED_NAME' end, 0.95,
       o.first_seen, o.last_seen, o.occurrences
from dms_outlets o
left join store_names n on n.name_key = {{ normalize_name('o.outlet_name') }}
