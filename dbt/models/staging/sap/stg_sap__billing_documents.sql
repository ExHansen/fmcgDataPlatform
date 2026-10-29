with src as (
    {{ latest_version(source('raw_sap', 'vbrk'), ['vbeln']) }}
)

select
    vbeln                               as billing_no,
    fkart                               as billing_type,
    fkart = 'S1'                        as is_cancellation_document,
    coalesce(trim(fksto), '') = 'X'     as is_cancelled,
    nullif(trim(sfakn), '')             as cancelled_billing_no,
    {{ sap_date('fkdat') }}             as billing_date,
    {{ sap_date('erdat') }}             as created_date,
    {{ sap_date('aedat') }}             as changed_date,
    vkorg                               as sales_org,
    vtweg                               as distribution_channel,
    {{ strip_zeros('kunag') }}          as sold_to_id,
    {{ strip_zeros('kunrg') }}          as payer_id,
    netwr::numeric                      as net_value,
    waerk                               as currency,
    _ingested_at
from src
