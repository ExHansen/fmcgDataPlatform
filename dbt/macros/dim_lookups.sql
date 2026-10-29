{# Join ke versi dimensi SCD2 yang berlaku pada tanggal transaksi; tanpa padanan -> unknown member '-1'. #}
{% macro scd2_join(dim, alias, natural_key_col, fact_key_expr, date_expr) -%}
    left join {{ ref(dim) }} {{ alias }}
        on {{ alias }}.{{ natural_key_col }} = {{ fact_key_expr }}
        and {{ date_expr }} >= {{ alias }}.valid_from and {{ date_expr }} < {{ alias }}.valid_to
{%- endmacro %}

{% macro store_key(store_id_expr) -%}
    case when {{ store_id_expr }} is null then '-1'
         else {{ dbt_utils.generate_surrogate_key([store_id_expr]) }} end
{%- endmacro %}
