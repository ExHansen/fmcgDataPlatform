{# PLAN 2.5 #8: jumlah baris per file di manifest (dihitung saat parse) vs baris yang ada di raw. #}
with raw_counts as (
    select _batch_id, count(*) as n from {{ source('raw_dms', 'secondary_sales') }} group by 1
    union all
    select _batch_id, count(*) from {{ source('raw_pos', 'sellout') }} group by 1
)

select
    'ingestion_file_rows'                   as check_name,
    m.business_date                         as period_start,
    m.business_date                         as period_end,
    m.source_system || ':' || m.file_path   as dimension_key,
    m.rows                                  as source_value,
    coalesce(r.n, 0)                        as target_value,
    m.rows - coalesce(r.n, 0)               as diff_abs,
    round(100.0 * (coalesce(r.n, 0) - m.rows) / nullif(m.rows, 0), 2) as diff_pct,
    0.0                                     as threshold_pct,
    case when m.rows = coalesce(r.n, 0) then 'PASS' else 'FAIL' end as status
from {{ source('ops', 'file_manifest') }} m
left join raw_counts r on r._batch_id = m.batch_id
where m.status = 'LOADED'
