with src as (
    {{ latest_version(source('raw_sap', 't023t'), ['spras', 'matkl']) }}
)

select
    trim(matkl)         as material_group,
    trim(wgbez60)       as material_group_name,
    _ingested_at
from src
where spras = 'E'
