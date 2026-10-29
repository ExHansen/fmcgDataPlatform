{# Anomali volume file 14 hari terakhir (yang lebih lama sudah pernah di-alert / ditangani). #}
{{ config(severity='warn', meta={'alert_severity': 'warn'}) }}
select *
from {{ ref('volume_anomalies') }}
where status = 'ANOMALY'
  and business_date >= (now() at time zone 'Asia/Jakarta')::date - 14
