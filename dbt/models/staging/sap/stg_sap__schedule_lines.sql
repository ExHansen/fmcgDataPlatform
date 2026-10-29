with src as (
    {{ latest_version(source('raw_sap', 'vbep'), ['vbeln', 'posnr', 'etenr']) }}
)

select
    vbeln                           as sales_order_no,
    posnr                           as item_no,
    etenr                           as schedule_line_no,
    {{ sap_date('edatu') }}         as requested_delivery_date,
    wmeng::numeric                  as qty_requested_sales_uom,
    bmeng::numeric                  as qty_confirmed_sales_uom,
    _ingested_at
from src
