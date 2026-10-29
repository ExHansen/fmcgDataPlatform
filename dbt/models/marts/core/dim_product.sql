{#
  1 baris per versi SKU (SCD Type 2 dari snap_sap_materials).
  Versi pertama tiap SKU berlaku sejak 1900-01-01: snapshot baru dimulai saat pipeline dipasang,
  jadi transaksi historis memakai atribut versi pertama yang tercatat.
  product_key '-1' = unknown member untuk kode yang belum ter-mapping.
#}
with snap as (
    select *,
        row_number() over (partition by material_id order by dbt_valid_from) as version_no
    from {{ ref('snap_sap_materials') }}
),

versions as (
    select
        s.*,
        case when version_no = 1 then timestamp '1900-01-01' else dbt_valid_from end as valid_from,
        coalesce(dbt_valid_to, timestamp '9999-12-31') as valid_to,
        dbt_valid_to is null as is_current
    from snap s
),

case_size as (
    select material_id, base_uom_per_alt_uom::int as pcs_per_case
    from {{ ref('stg_sap__uom_conversions') }} where alt_uom = 'CS'
)

select
    {{ dbt_utils.generate_surrogate_key(['v.material_id', 'v.valid_from']) }} as product_key,
    v.material_id                       as sku_id,
    v.material_no                       as sap_matnr,
    v.ean,
    t.material_description              as product_name,
    h.product_hierarchy_name            as brand,
    v.product_hierarchy                 as brand_code,
    g.material_group_name               as category,
    v.material_group                    as category_code,
    v.base_uom,
    c.pcs_per_case,
    v.valid_from,
    v.valid_to,
    v.is_current
from versions v
left join {{ ref('stg_sap__material_texts') }} t using (material_id)
left join {{ ref('stg_sap__product_hierarchies') }} h on h.product_hierarchy = v.product_hierarchy
left join {{ ref('stg_sap__material_groups') }} g on g.material_group = v.material_group
left join case_size c using (material_id)

union all

select '-1', 'UNKNOWN', null, null, 'Produk belum ter-mapping', 'UNKNOWN', null, 'UNKNOWN', null, null, null,
       timestamp '1900-01-01', timestamp '9999-12-31', true
