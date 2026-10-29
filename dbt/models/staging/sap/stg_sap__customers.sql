with src as (
    {{ latest_version(source('raw_sap', 'kna1'), ['kunnr']) }}
)

select
    {{ strip_zeros('kunnr') }}      as customer_id,
    kunnr                           as customer_kunnr,
    trim(name1)                     as customer_name,
    land1                           as country,
    regio                           as region_code,
    trim(ort01)                     as city,
    trim(stras)                     as street,
    ktokd                           as account_group,
    ktokd = 'ZDIS'                  as is_distributor,
    {{ sap_date('erdat') }}         as created_date,
    _ingested_at
from src
