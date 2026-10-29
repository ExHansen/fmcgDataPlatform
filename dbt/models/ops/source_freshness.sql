{#
  Kesegaran data per sumber (lebih rinci dari `dbt source freshness`: per distributor & retailer).
  - SAP: jam sejak extract sukses terakhir (warn > 26 jam, error > 48 jam)
  - DMS: hari sejak tanggal bisnis file terakhir (warn > 2, error > 4) -> "distributor telat kirim"
  - POS: hari sejak awal minggu file terakhir (warn > 15, error > 22: file minggu lalu tiba Selasa)
  Waktu acuan: now() di zona Asia/Jakarta.
#}
with sap as (
    select 'SAP' as source_system, max(ended_at) as last_success_at, null::date as last_business_date
    from {{ source('ops', 'pipeline_run_log') }}
    where source_system = 'SAP' and status = 'SUCCESS'
),

files as (
    select source_system, max(received_at) as last_success_at, max(business_date) as last_business_date
    from {{ source('ops', 'file_manifest') }}
    where status = 'LOADED'
    group by 1
),

all_sources as (
    select * from sap
    union all
    select * from files
),

measured as (
    select
        source_system,
        last_success_at,
        last_business_date,
        round(extract(epoch from now() - last_success_at) / 3600, 1)                as hours_since_load,
        (now() at time zone 'Asia/Jakarta')::date - last_business_date              as business_lag_days
    from all_sources
)

select
    *,
    case
        when source_system = 'SAP' then
            case when hours_since_load > 48 then 'ERROR' when hours_since_load > 26 then 'WARN' else 'OK' end
        when source_system like 'DMS\_%' then
            case when business_lag_days > 4 then 'ERROR' when business_lag_days > 2 then 'WARN' else 'OK' end
        when source_system like 'POS\_%' then
            case when business_lag_days > 22 then 'ERROR' when business_lag_days > 15 then 'WARN' else 'OK' end
    end as status
from measured
