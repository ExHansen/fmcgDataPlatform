{#
  1 baris per hari. period_4w = kalender retail 13 periode x 4 minggu (dimulai Senin minggu ISO pertama).
  Libur: hanya libur nasional bertanggal tetap (seed id_public_holidays). Libur bertanggal bergerak
  (Idul Fitri, Nyepi, dst.) perlu ditambahkan dari SKB 3 Menteri tahun berjalan.
#}
with days as (
    {{ dbt_utils.date_spine(datepart="day", start_date="cast('2025-01-01' as date)", end_date="cast('2028-01-01' as date)") }}
),

d as (
    select date_day::date as date_day from days
)

select
    to_char(d.date_day, 'YYYYMMDD')                         as date_key,
    d.date_day,
    extract(isoyear from d.date_day)::int                   as iso_year,
    extract(week from d.date_day)::int                      as iso_week,
    to_char(d.date_day, 'IYYY-"W"IW')                       as iso_year_week,
    date_trunc('week', d.date_day)::date                    as week_start_date,
    extract(year from d.date_day)::int                      as year,
    extract(quarter from d.date_day)::int                   as quarter,
    extract(month from d.date_day)::int                     as month,
    to_char(d.date_day, 'YYYY-MM')                          as year_month,
    date_trunc('month', d.date_day)::date                   as month_start_date,
    extract(isodow from d.date_day)::int                    as iso_day_of_week,
    to_char(d.date_day, 'FMDay')                            as day_name,
    extract(isoyear from d.date_day)::int || '-P'
        || lpad(least(13, (extract(week from d.date_day)::int - 1) / 4 + 1)::text, 2, '0') as period_4w,
    extract(isodow from d.date_day) in (6, 7)               as is_weekend,
    h.holiday_name                                          as event_name,
    h.holiday_date is not null                              as is_holiday
from d
left join {{ ref('id_public_holidays') }} h on h.holiday_date = d.date_day
