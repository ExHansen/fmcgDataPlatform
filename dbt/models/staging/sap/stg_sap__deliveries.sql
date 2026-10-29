with src as (
    {{ latest_version(source('raw_sap', 'likp'), ['vbeln']) }}
)

select
    vbeln                               as delivery_no,
    lfart                               as delivery_type,
    {{ sap_date('erdat') }}             as created_date,
    {{ sap_date('aedat') }}             as changed_date,
    vstel                               as shipping_point,
    {{ strip_zeros('kunnr') }}          as ship_to_id,
    {{ sap_date('lfdat') }}             as delivery_date,
    {{ sap_date('wadat') }}             as planned_goods_issue_date,
    {{ sap_date('wadat_ist') }}         as actual_goods_issue_date,
    {{ sap_date('wadat_ist') }} is not null as is_goods_issued,
    _ingested_at
from src
