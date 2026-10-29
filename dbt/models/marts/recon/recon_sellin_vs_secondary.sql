{#
  Sell-in (goods issue SAP ke distributor) vs secondary (kiriman distributor ke toko), per distributor
  x periode 4 minggu. Selisih wajar karena stok distributor naik-turun, jadi yang dinilai stok tersirat:
    FAIL  stok tersirat kumulatif < 0  (distributor mengirim lebih banyak dari yang pernah diterima:
          data SAP hilang, atau baris DMS dobel / mapping produk salah)
    WARN  weeks of cover > 6 (stok menumpuk di distributor)
    PASS  selain itu
#}
with periods as (
    select period_4w, min(date_day) as period_start, max(date_day) as period_end
    from {{ ref('dim_date') }} group by 1
),

weekly as (
    select distributor_code, week_start_date, sell_in_pcs, secondary_pcs, implied_stock_pcs, weeks_of_cover
    from {{ ref('mart_distributor_scorecard') }}
),

by_period as (
    select w.distributor_code, p.period_4w, p.period_start, p.period_end,
           sum(w.sell_in_pcs) as sell_in_pcs, sum(w.secondary_pcs) as secondary_pcs,
           (array_agg(w.implied_stock_pcs order by w.week_start_date desc))[1] as implied_stock_pcs,
           (array_agg(w.weeks_of_cover order by w.week_start_date desc))[1] as weeks_of_cover
    from weekly w
    join periods p on w.week_start_date between p.period_start and p.period_end
    group by 1, 2, 3, 4
)

select
    'sellin_vs_secondary'                               as check_name,
    period_start,
    period_end,
    distributor_code                                    as dimension_key,
    sell_in_pcs                                         as source_value,
    secondary_pcs                                       as target_value,
    sell_in_pcs - secondary_pcs                         as diff_abs,
    round(100.0 * (sell_in_pcs - secondary_pcs) / nullif(secondary_pcs, 0), 2) as diff_pct,
    null::numeric                                       as threshold_pct,
    implied_stock_pcs,
    weeks_of_cover,
    case when implied_stock_pcs < 0 then 'FAIL'
         when weeks_of_cover > 6 then 'WARN'
         else 'PASS' end                                as status
from by_period
