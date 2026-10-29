with src as (
    {{ latest_version(source('raw_sap', 'lips'), ['vbeln', 'posnr']) }}
)

select
    vbeln                                           as delivery_no,
    posnr                                           as item_no,
    {{ strip_zeros('matnr') }}                      as material_id,
    lfimg::numeric                                  as qty_sales_uom,
    vrkme                                           as sales_uom,
    lfimg::numeric * umvkz::numeric / umvkn::numeric as qty_base_uom,
    werks                                           as plant,
    vgbel                                           as sales_order_no,
    vgpos                                           as sales_order_item_no,
    {{ sap_date('erdat') }}                         as created_date,
    _ingested_at
from src
