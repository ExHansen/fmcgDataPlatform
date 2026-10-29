with src as (
    {{ latest_version(source('raw_sap', 'mara'), ['matnr']) }}
)

select
    {{ strip_zeros('matnr') }}          as material_id,
    matnr                               as material_no,
    mtart                               as material_type,
    trim(matkl)                         as material_group,
    trim(prdha)                         as product_hierarchy,
    meins                               as base_uom,
    lpad(nullif(trim(ean11), ''), 13, '0') as ean,
    brgew::numeric                      as gross_weight,
    gewei                               as weight_unit,
    {{ sap_date('ersda') }}             as created_date,
    {{ sap_date('laeda') }}             as changed_date,
    coalesce(trim(lvorm), '') = 'X'     as is_deletion_flagged,
    _ingested_at
from src
