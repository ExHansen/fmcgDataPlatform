{# Sumber yang terlambat (status WARN/ERROR di ops.source_freshness). #}
{{ config(severity='warn', meta={'alert_severity': 'error'}) }}
select *
from {{ ref('source_freshness') }}
where status <> 'OK'
