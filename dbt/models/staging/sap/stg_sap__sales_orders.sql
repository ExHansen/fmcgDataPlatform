with src as (
    {{ latest_version(source('raw_sap', 'vbak'), ['vbeln']) }}
)

select
    vbeln                                   as sales_order_no,
    auart                                   as order_type,
    {{ sap_date('audat') }}                 as order_date,
    {{ sap_date('erdat') }}                 as created_date,
    {{ sap_date('aedat') }}                 as changed_date,
    {{ strip_zeros('kunnr') }}              as sold_to_id,
    kunnr                                   as sold_to_kunnr,
    vkorg                                   as sales_org,
    vtweg                                   as distribution_channel,
    spart                                   as division,
    nullif(trim(bstnk), '')                 as customer_po_no,
    netwr::numeric                          as net_value,
    waerk                                   as currency,
    _ingested_at
from src
