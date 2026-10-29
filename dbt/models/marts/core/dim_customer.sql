{#
  Customer komersial principal (MVP: distributor = sold-to SAP), SCD Type 2 dari snap_sap_customers.
  customer_key '-1' = unknown member.
#}
with snap as (
    select *, row_number() over (partition by customer_id order by dbt_valid_from) as version_no
    from {{ ref('snap_sap_customers') }}
),

versions as (
    select s.*,
        case when version_no = 1 then timestamp '1900-01-01' else dbt_valid_from end as valid_from,
        coalesce(dbt_valid_to, timestamp '9999-12-31') as valid_to,
        dbt_valid_to is null as is_current
    from snap s
)

select
    {{ dbt_utils.generate_surrogate_key(['v.customer_id', 'v.valid_from']) }} as customer_key,
    v.customer_id,
    v.customer_kunnr                    as sap_kunnr,
    m.distributor_code,
    v.customer_name,
    case when v.is_distributor then 'DISTRIBUTOR' else 'KEY_ACCOUNT' end as customer_type,
    'MODERN_TRADE'                      as channel,
    m.region,
    v.city,
    v.valid_from,
    v.valid_to,
    v.is_current
from versions v
left join {{ ref('distributor_master') }} m on {{ strip_zeros('m.sap_kunnr') }} = v.customer_id

union all

select '-1', 'UNKNOWN', null, null, 'Customer belum ter-mapping', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', null,
       timestamp '1900-01-01', timestamp '9999-12-31', true
