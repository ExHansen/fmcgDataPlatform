-- PLAN 2.7 #7: distributor mana yang telat / tidak lengkap mengirim data?
select
    s.distributor_code,
    count(*)                                                    as expected_files,
    count(*) filter (where s.status = 'MISSING')                as missing_files,
    count(*) filter (where s.days_late > 1)                     as late_files,
    count(*) filter (where s.versions > 1)                      as resent_files,
    round(avg(s.days_late), 2)                                  as avg_days_late,
    round(100.0 * count(*) filter (where s.status = 'RECEIVED' and s.days_late <= 1) / count(*), 1) as on_time_pct,
    (select count(*) from {{ ref('unmapped_ids') }} u
     join {{ ref('distributor_master') }} m on m.source_system = u.source_system
     where m.distributor_code = s.distributor_code)             as unmapped_codes
from {{ ref('dms_file_status') }} s
group by 1
order by on_time_pct
