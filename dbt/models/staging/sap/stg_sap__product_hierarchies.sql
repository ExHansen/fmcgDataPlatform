with src as (
    {{ latest_version(source('raw_sap', 't179t'), ['spras', 'prodh']) }}
)

select
    trim(prodh)         as product_hierarchy,
    trim(vtext)         as product_hierarchy_name,
    _ingested_at
from src
where spras = 'E'
