{#
  Cross-reference produk: kode produk di tiap sistem -> sku_id kanonik (= nomor material SAP tanpa leading zero).
  Urutan aturan (yang pertama cocok dipakai):
    SAP        material sendiri                         EXACT_KEY        1.00
    DMS_A      seed mapping tim MDM                      MANUAL           1.00
               nama produk persis sama & unik di SAP     NORMALIZED_NAME  0.90
    DMS_B      SKU = MATNR tanpa leading zero            EXACT_KEY        1.00
    DMS_C      ITEM_CODE = EAN                           EAN              1.00
    POS_*      EAN artikel (sudah dipad 13 digit)        EAN              1.00
  Kode yang tidak cocok tetap ada dengan sku_id null -> ops.unmapped_ids.
#}
with materials as (
    select m.material_id, m.ean, m.created_date, t.material_description
    from {{ ref('stg_sap__materials') }} m
    left join {{ ref('stg_sap__material_texts') }} t using (material_id)
),

unique_names as (
    select {{ normalize_name('material_description') }} as name_key, min(material_id) as material_id
    from materials
    group by 1
    having count(*) = 1
),

manual as (
    select distributor_code, local_product_code, {{ strip_zeros('sap_matnr') }} as material_id, mapped_by, mapped_at
    from {{ ref('dms_product_mapping') }}
),

dms_codes as (
    select distributor_code, source_system, product_code, max(product_name) as product_name,
           min(invoice_date) as first_seen, max(invoice_date) as last_seen, count(*) as occurrences
    from {{ ref('stg_dms__secondary_sales') }}
    group by 1, 2, 3
),

pos_codes as (
    select source_system, article_code, max(ean) as ean, max(article_description) as article_description,
           min(sales_date) as first_seen, max(sales_date) as last_seen, count(*) as occurrences
    from {{ ref('stg_pos__sellout') }}
    group by 1, 2
),

sap as (
    select 'SAP' as source_system, material_id as source_id, material_description as source_description,
           material_id as sku_id, 'EXACT_KEY' as match_method, 1.00 as match_confidence,
           null::text as approved_by, null::date as approved_at,
           created_date as first_seen, created_date as last_seen, 1 as occurrences
    from materials
),

dms as (
    select
        d.source_system, d.product_code as source_id, d.product_name as source_description,
        coalesce(mn.material_id, b.material_id, c.material_id, nm.material_id) as sku_id,
        case when mn.material_id is not null then 'MANUAL'
             when b.material_id is not null then 'EXACT_KEY'
             when c.material_id is not null then 'EAN'
             when nm.material_id is not null then 'NORMALIZED_NAME' end as match_method,
        case when nm.material_id is not null and coalesce(mn.material_id, b.material_id, c.material_id) is null
             then 0.90 else 1.00 end as match_confidence,
        mn.mapped_by as approved_by, mn.mapped_at as approved_at,
        d.first_seen, d.last_seen, d.occurrences
    from dms_codes d
    left join manual mn
        on mn.distributor_code = d.distributor_code and mn.local_product_code = d.product_code
    left join materials b
        on d.distributor_code = 'DIST_B' and b.material_id = {{ strip_zeros('d.product_code') }}
    left join materials c
        on d.distributor_code = 'DIST_C' and c.ean = lpad(d.product_code, 13, '0')
    left join unique_names nm
        on d.distributor_code = 'DIST_A' and nm.name_key = {{ normalize_name('d.product_name') }}
),

pos as (
    select
        p.source_system, p.article_code as source_id, p.article_description as source_description,
        m.material_id as sku_id, case when m.material_id is not null then 'EAN' end as match_method,
        1.00 as match_confidence, null::text as approved_by, null::date as approved_at,
        p.first_seen, p.last_seen, p.occurrences
    from pos_codes p
    left join materials m on m.ean = p.ean
)

select 'PRODUCT' as entity_type, * from sap
union all
select 'PRODUCT', * from dms
union all
select 'PRODUCT', * from pos
