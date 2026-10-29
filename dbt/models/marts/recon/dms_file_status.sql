{#
  Status file harian per distributor. Hari "diharapkan" = hari dalam minggu yang biasanya ada kirimannya
  (>= 50% minggu dalam data). Hari diharapkan tanpa file LOADED = MISSING.
  Hanya hari yang sudah lewat batas wajar (D+4) yang dinilai, supaya file yang masih dalam perjalanan
  tidak dianggap hilang.
#}
with files as (
    select m.source_system, dm.distributor_code, m.business_date,
           count(*) as versions,
           min(m.received_at) as first_received_at,
           max(m.received_at) as last_received_at
    from {{ source('ops', 'file_manifest') }} m
    join {{ ref('distributor_master') }} dm using (source_system)
    where m.status = 'LOADED'
    group by 1, 2, 3
),

bounds as (
    select distributor_code, min(business_date) as first_date,
           (select max((received_at at time zone 'Asia/Jakarta')::date) from {{ source('ops', 'file_manifest') }}) - 4 as last_date
    from files group by 1
),

weekday_pattern as (
    select f.distributor_code, extract(isodow from f.business_date)::int as dow,
           count(*)::numeric / greatest(1, (max(b.last_date) - min(b.first_date)) / 7) as share
    from files f join bounds b using (distributor_code)
    group by 1, 2
),

expected as (
    select b.distributor_code, d.date_day as business_date
    from bounds b
    join {{ ref('dim_date') }} d on d.date_day between b.first_date and b.last_date
    join weekday_pattern w on w.distributor_code = b.distributor_code
                          and w.dow = d.iso_day_of_week and w.share >= 0.5
)

select
    e.distributor_code,
    e.business_date,
    case when f.business_date is null then 'MISSING' else 'RECEIVED' end   as status,
    coalesce(f.versions, 0)                                                 as versions,
    f.first_received_at,
    (f.first_received_at at time zone 'Asia/Jakarta')::date - e.business_date as days_late
from expected e
left join files f using (distributor_code, business_date)
