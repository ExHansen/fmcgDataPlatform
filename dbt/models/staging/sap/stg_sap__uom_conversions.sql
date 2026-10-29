with src as (
    {{ latest_version(source('raw_sap', 'marm'), ['matnr', 'meinh']) }}
)

select
    {{ strip_zeros('matnr') }}                  as material_id,
    meinh                                       as alt_uom,
    umrez::numeric / umren::numeric             as base_uom_per_alt_uom,
    lpad(nullif(trim(ean11), ''), 13, '0')      as ean,
    _ingested_at
from src
