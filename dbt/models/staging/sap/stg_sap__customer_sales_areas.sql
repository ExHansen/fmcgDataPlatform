with src as (
    {{ latest_version(source('raw_sap', 'knvv'), ['kunnr', 'vkorg', 'vtweg', 'spart']) }}
)

select
    {{ strip_zeros('kunnr') }}      as customer_id,
    vkorg                           as sales_org,
    vtweg                           as distribution_channel,
    spart                           as division,
    kdgrp                           as customer_group,
    {{ sap_date('erdat') }}         as created_date,
    _ingested_at
from src
