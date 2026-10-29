{#
  Tabel id_mapping (PLAN 2.4.4): satu baris per (entity_type, source_system, source_id, valid_from)
  untuk ID yang sudah ter-mapping. ID yang belum ter-mapping ada di ops.unmapped_ids.
#}
with all_xref as (
    select entity_type, source_system, source_id, sku_id as canonical_id, match_method, match_confidence,
           approved_by, approved_at, first_seen
    from {{ ref('int_product_xref') }}
    union all
    select entity_type, source_system, source_id, store_id, match_method, match_confidence,
           null, null, first_seen
    from {{ ref('int_store_xref') }}
    union all
    select entity_type, source_system, source_id, customer_id, match_method, match_confidence,
           case when match_method = 'MANUAL' then 'sales.ops' end, null, first_seen
    from {{ ref('int_customer_xref') }}
)

select
    entity_type,
    source_system,
    source_id,
    canonical_id,
    match_method,
    match_confidence::numeric(3, 2) as match_confidence,
    first_seen                      as valid_from,
    date '9999-12-31'               as valid_to,
    true                            as is_active,
    approved_by,
    approved_at
from all_xref
where canonical_id is not null
