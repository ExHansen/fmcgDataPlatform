{# ID sumber yang belum punya padanan kanonik — daftar kerja untuk tim MDM. #}
select entity_type, source_system, source_id, source_description, first_seen, last_seen, occurrences
from {{ ref('int_product_xref') }}
where sku_id is null

union all

select entity_type, source_system, source_id, source_description, first_seen, last_seen, occurrences
from {{ ref('int_store_xref') }}
where store_id is null

union all

select entity_type, source_system, source_id, source_description, first_seen, last_seen, occurrences
from {{ ref('int_customer_xref') }}
where customer_id is null
