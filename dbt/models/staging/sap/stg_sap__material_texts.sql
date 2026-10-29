with src as (
    {{ latest_version(source('raw_sap', 'makt'), ['matnr', 'spras']) }}
)

select
    {{ strip_zeros('matnr') }}      as material_id,
    spras                           as language,
    trim(maktx)                     as material_description,
    _ingested_at
from src
where spras = 'E'
