with src as (
    {{ latest_version(source('raw_sap', 'vbap'), ['vbeln', 'posnr']) }}
)

select
    vbeln                                           as sales_order_no,
    posnr                                           as item_no,
    {{ strip_zeros('matnr') }}                      as material_id,
    matnr                                           as material_no,
    arktx                                           as item_description,
    kwmeng::numeric                                 as qty_sales_uom,
    vrkme                                           as sales_uom,
    meins                                           as base_uom,
    kwmeng::numeric * umvkz::numeric / umvkn::numeric as qty_base_uom,
    netwr::numeric                                  as net_value,
    waerk                                           as currency,
    werks                                           as plant,
    nullif(trim(abgru), '')                         as rejection_reason,
    nullif(trim(abgru), '') is not null             as is_rejected,
    {{ sap_date('erdat') }}                         as created_date,
    {{ sap_date('aedat') }}                         as changed_date,
    _ingested_at
from src
