with src as (
    {{ latest_version(source('raw_sap', 'vbrp'), ['vbeln', 'posnr']) }}
)

select
    vbeln                                           as billing_no,
    posnr                                           as item_no,
    {{ strip_zeros('matnr') }}                      as material_id,
    arktx                                           as item_description,
    fkimg::numeric                                  as qty_sales_uom,
    vrkme                                           as sales_uom,
    fkimg::numeric * umvkz::numeric / umvkn::numeric as qty_base_uom,
    netwr::numeric                                  as net_value,
    aubel                                           as sales_order_no,
    aupos                                           as sales_order_item_no,
    vgbel                                           as delivery_no,
    vgpos                                           as delivery_item_no,
    werks                                           as plant,
    {{ sap_date('erdat') }}                         as created_date,
    _ingested_at
from src
