with src as (
    {{ latest_version(source('raw_sap', 'vbfa'), ['vbelv', 'posnv', 'vbeln', 'posnn']) }}
)

select
    vbelv                       as preceding_doc_no,
    posnv                       as preceding_item_no,
    vbeln                       as subsequent_doc_no,
    posnn                       as subsequent_item_no,
    case vbtyp_n when 'J' then 'DELIVERY' when 'M' then 'INVOICE' when 'N' then 'INVOICE_CANCELLATION'
         else vbtyp_n end      as subsequent_doc_category,
    rfmng::numeric              as referenced_qty,
    {{ sap_date('erdat') }}     as created_date,
    _ingested_at
from src
