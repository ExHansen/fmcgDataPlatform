{#
  PLAN 2.5 #3: porsi nilai fakta per bulan yang jatuh ke unknown member ('-1').
  Dipakai dua tes (ambang 0,5% dan 2%). Keduanya severity dbt `warn` karena aksinya alert ke
  owner mapping sementara data tetap mengalir; level alert ada di meta.alert_severity.
#}
{% macro unknown_member_shares(min_pct) %}
with shares as (
    select 'fct_sales' as fact, 'product' as dimension, to_char(sales_date, 'YYYY-MM') as month,
           100.0 * sum(net_sales_value) filter (where product_key = '-1') / nullif(sum(net_sales_value), 0) as pct
    from {{ ref('fct_sales') }} group by 3
    union all
    select 'fct_sales', 'store', to_char(sales_date, 'YYYY-MM'),
           100.0 * sum(net_sales_value) filter (where store_key = '-1') / nullif(sum(net_sales_value), 0)
    from {{ ref('fct_sales') }} group by 3
    union all
    select 'fct_shipment', 'product', to_char(invoice_date, 'YYYY-MM'),
           100.0 * sum(net_value) filter (where product_key = '-1') / nullif(sum(net_value), 0)
    from {{ ref('fct_shipment') }} group by 3
    union all
    select 'fct_shipment', 'store', to_char(invoice_date, 'YYYY-MM'),
           100.0 * sum(net_value) filter (where store_key = '-1') / nullif(sum(net_value), 0)
    from {{ ref('fct_shipment') }} group by 3
)
select fact, dimension, month, round(pct, 2) as pct_value_unknown
from shares
where coalesce(pct, 0) > {{ min_pct }}
{% endmacro %}
