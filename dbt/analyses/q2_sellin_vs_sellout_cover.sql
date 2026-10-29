-- PLAN 2.7 #2: apakah sell-in sejalan dengan sell-out? Distributor mana yang stoknya menumpuk?
-- 13 minggu terakhir yang lengkap.
with recent as (
    select *
    from {{ ref('mart_distributor_scorecard') }}
    where week_start_date >= (select max(week_start_date) from {{ ref('mart_distributor_scorecard') }}) - 13 * 7
      and week_start_date < (select max(week_start_date) from {{ ref('mart_distributor_scorecard') }})
)

select
    distributor_code,
    sum(sell_in_pcs)                                                    as sell_in_pcs,
    sum(secondary_pcs)                                                  as secondary_pcs,
    sum(sellout_pcs)                                                    as sellout_pcs,
    round(100.0 * sum(sell_in_pcs) / nullif(sum(sellout_pcs), 0), 1)    as sell_in_per_sellout_pct,
    (array_agg(weeks_of_cover order by week_start_date desc))[1]        as weeks_of_cover_latest,
    (array_agg(implied_stock_pcs order by week_start_date desc))[1]     as implied_stock_pcs_latest
from recent
group by 1
order by weeks_of_cover_latest desc
