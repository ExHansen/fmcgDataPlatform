{# Pakai nama schema custom apa adanya (staging, intermediate, ...) tanpa prefix target. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name else target.schema }}
{%- endmacro %}
