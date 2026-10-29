{#
  Hook run dbt -> tabel ops (PLAN 2.4.5):
    on-run-start: 1 baris ops.pipeline_run_log (run_id = invocation_id dbt)
    on-run-end:   hasil tiap tes -> ops.dq_results; isi recon_all -> ops.recon_results; status run diperbarui
#}
{% macro _logged_command() %}
    {{ return(flags.WHICH in ['run', 'build', 'test', 'seed', 'snapshot']) }}
{% endmacro %}

{% macro _q(value) -%}
    {%- if value is none -%}null{%- else -%}'{{ value | string | replace("'", "''") }}'{%- endif -%}
{%- endmacro %}

{% macro log_run_start() %}
    {% if execute and _logged_command() %}
        insert into ops.pipeline_run_log (run_id, dag_id, task_id, source_system, object_name, started_at, status)
        values ('{{ invocation_id }}', {{ _q(env_var('AIRFLOW_CTX_DAG_ID', '') or none) }}, {{ _q(env_var('AIRFLOW_CTX_TASK_ID', '') or none) }},
                'DBT', '{{ flags.WHICH }}', now(), 'RUNNING')
        on conflict (run_id) do nothing
    {% endif %}
{% endmacro %}

{% macro save_run_results(results) %}
    {% if not (execute and _logged_command()) %}{{ return('') }}{% endif %}

    {# ---------- dq_results ---------- #}
    {% set rows = [] %}
    {% for r in results if r.node.resource_type == 'test' %}
        {% set meta = r.node.test_metadata %}
        {% set model = r.node.attached_node or (r.node.depends_on.nodes | first) %}
        {% do rows.append("(" ~ _q(invocation_id ~ '.' ~ r.node.unique_id) ~ ", '" ~ invocation_id ~ "', now(), "
            ~ _q(model.split('.')[-1] if model else none) ~ ", " ~ _q(r.node.name) ~ ", "
            ~ _q(meta.name if meta else 'singular') ~ ", "
            ~ _q((r.node.config.meta or {}).get('alert_severity', r.node.config.severity) | lower) ~ ", "
            ~ (r.failures if r.failures is not none else 'null') ~ ", "
            ~ _q(r.node.config.error_if) ~ ", " ~ _q(r.status | string) ~ ")") %}
    {% endfor %}
    {% if rows %}
        {% call statement('save_dq_results') %}
            insert into ops.dq_results (dq_result_id, run_id, executed_at, model_name, test_name, test_type,
                                        severity, failed_rows, threshold, status)
            values {{ rows | join(',\n') }}
            on conflict (dq_result_id) do nothing
        {% endcall %}
    {% endif %}

    {# ---------- recon_results (hanya jika recon_all dibangun di run ini) ---------- #}
    {% set recon_built = results | selectattr('node.name', 'equalto', 'recon_all')
                                 | selectattr('status', 'equalto', 'success') | list %}
    {% if recon_built %}
        {# ref() tidak boleh di blok kondisional hook; relasi dibentuk dari node yang dibangun #}
        {% set recon_node = recon_built[0].node %}
        {% set recon_relation = api.Relation.create(database=recon_node.database, schema=recon_node.schema,
                                                    identifier=recon_node.alias) %}
        {% call statement('save_recon_results') %}
            insert into ops.recon_results (recon_id, run_id, check_name, period_start, period_end, dimension_key,
                                           source_value, target_value, diff_abs, diff_pct, threshold_pct, status)
            select '{{ invocation_id }}.' || md5(check_name || '|' || coalesce(period_start::text, '') || '|' || dimension_key),
                   '{{ invocation_id }}', check_name, period_start, period_end, dimension_key,
                   source_value, target_value, diff_abs, diff_pct, threshold_pct, status
            from {{ recon_relation }}
        {% endcall %}
    {% endif %}

    {# ---------- status run ---------- #}
    {% set failed = results | selectattr('status', 'in', ['error', 'fail']) | list %}
    {% call statement('finish_run_log') %}
        update ops.pipeline_run_log
        set ended_at = now(),
            status = '{{ "FAILED" if failed else "SUCCESS" }}',
            rows_loaded = {{ results | selectattr('node.resource_type', 'in', ['model', 'snapshot', 'seed']) | list | length }},
            error_message = {{ _q((failed | map(attribute='node.name') | join(', '))[:2000] if failed else none) }}
        where run_id = '{{ invocation_id }}'
    {% endcall %}
    {{ return('') }}
{% endmacro %}
