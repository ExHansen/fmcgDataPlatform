{#
  1 baris per toko fisik (modern trade). Atribut dari POS + master retailer; distributor pelayan =
  distributor dengan nilai kiriman terbesar ke toko itu (region mengikuti distributor).
  MVP tanpa CRM: belum ada riwayat perubahan atribut toko, jadi dimensi ini tipe 1.
#}
with stores as (
    select store_id, max(source_description) as store_name, min(first_seen) as first_seen
    from {{ ref('int_store_xref') }}
    where source_system like 'POS\_%' and store_id is not null
    group by 1
),

serving as (
    select store_id, distributor_customer_id,
        row_number() over (partition by store_id order by sum(net_value) desc) as rnk
    from {{ ref('int_secondary_sales_mapped') }}
    where store_id is not null
    group by 1, 2
),

distributor as (
    select customer_id, customer_key, distributor_code, region
    from {{ ref('dim_customer') }}
    where is_current and customer_type = 'DISTRIBUTOR'
)

select
    {{ dbt_utils.generate_surrogate_key(['s.store_id']) }} as store_key,
    s.store_id,
    s.store_id                                  as retailer_store_code,
    r.retailer_code,
    r.retailer_name,
    r.store_format,
    s.store_name,
    d.distributor_code,
    coalesce(d.customer_key, '-1')              as distributor_key,
    coalesce(d.region, 'UNKNOWN')               as region,
    s.first_seen                                as first_sales_date
from stores s
left join {{ ref('retailer_master') }} r on r.retailer_code = split_part(s.store_id, '-', 1)
left join serving sv on sv.store_id = s.store_id and sv.rnk = 1
left join distributor d on d.customer_id = sv.distributor_customer_id

union all

select '-1', 'UNKNOWN', null, null, null, null, 'Toko belum ter-mapping', null, '-1', 'UNKNOWN', null
