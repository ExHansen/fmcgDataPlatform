{#
  PLAN 2.5 #6: jumlah baris file jauh dari median pembanding -> kemungkinan file terpotong / dobel.
  Ambang per tipe sumber dari profil data (var volume_anomaly_bounds), bukan +-50% seperti draf PLAN:
  volume harian DMS wajar berada di 0,45x-2,1x median (persentil 1-99) karena tergantung toko yang dikirimi.
  Pembanding: DMS = file hari yang sama dalam minggu, 4 minggu sebelumnya (volume tergantung jadwal kirim toko);
  POS = 4 file mingguan sebelumnya. Butuh minimal 3 file pembanding.
  Versi terakhir per tanggal bisnis saja (file koreksi menggantikan versi lama).
#}
with files as (
    select source_system, business_date, rows, received_at, file_path,
           row_number() over (partition by source_system, business_date order by version desc) as rnk
    from {{ source('ops', 'file_manifest') }}
    where status = 'LOADED'
),

latest as (
    select * from files where rnk = 1
),

compared as (
    select
        l.source_system, l.business_date, l.rows, l.received_at, l.file_path,
        (select percentile_cont(0.5) within group (order by p.rows)
         from latest p
         where p.source_system = l.source_system
           and p.business_date < l.business_date
           and p.business_date >= l.business_date - 28
           and (l.source_system like 'POS\_%' or extract(isodow from p.business_date) = extract(isodow from l.business_date))
        )::numeric as baseline_rows,
        (select count(*)
         from latest p
         where p.source_system = l.source_system
           and p.business_date < l.business_date
           and p.business_date >= l.business_date - 28
           and (l.source_system like 'POS\_%' or extract(isodow from p.business_date) = extract(isodow from l.business_date))
        ) as baseline_files
    from latest l
)

select
    source_system,
    business_date,
    file_path,
    received_at,
    rows,
    baseline_rows,
    round(100.0 * (rows - baseline_rows) / nullif(baseline_rows, 0), 1) as diff_pct,
    case when baseline_files < 3 then 'INSUFFICIENT_HISTORY'
         {%- set b = var('volume_anomaly_bounds') %}
         when source_system like 'DMS\_%' and (rows < {{ b.DMS.min_ratio }} * baseline_rows or rows > {{ b.DMS.max_ratio }} * baseline_rows) then 'ANOMALY'
         when source_system like 'POS\_%' and (rows < {{ b.POS.min_ratio }} * baseline_rows or rows > {{ b.POS.max_ratio }} * baseline_rows) then 'ANOMALY'
         else 'OK' end                                                  as status
from compared
