{#
  Cross-reference customer (distributor). customer_id kanonik = nomor customer SAP tanpa leading zero.
  Kode distributor di file DMS dipetakan lewat seed distributor_master.
#}
with sap_customers as (
    select customer_id, customer_name, created_date
    from {{ ref('stg_sap__customers') }}
),

dms as (
    select distributor_code, source_system, min(invoice_date) as first_seen, max(invoice_date) as last_seen,
           count(*) as occurrences
    from {{ ref('stg_dms__secondary_sales') }}
    group by 1, 2
)

select 'CUSTOMER' as entity_type, 'SAP' as source_system, customer_id as source_id,
       customer_name as source_description, customer_id, 'EXACT_KEY' as match_method, 1.00 as match_confidence,
       created_date as first_seen, created_date as last_seen, 1 as occurrences
from sap_customers

union all

select 'CUSTOMER', d.source_system, d.distributor_code, m.distributor_name,
       c.customer_id, case when c.customer_id is not null then 'MANUAL' end, 1.00,
       d.first_seen, d.last_seen, d.occurrences
from dms d
left join {{ ref('distributor_master') }} m using (distributor_code)
left join sap_customers c on c.customer_id = {{ strip_zeros('m.sap_kunnr') }}
