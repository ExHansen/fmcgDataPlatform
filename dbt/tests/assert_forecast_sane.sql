{#
  PLAN 2.5 #12: forecast sanity. Total forecast model terpilih per minggu (run terbaru) harus dalam
  +-50% rata-rata penjualan 8 minggu terakhir. Di luar itu -> alert ke owner forecasting.
#}
{{ config(severity='warn', meta={'alert_severity': 'warn'}) }}

with fc as (
    select target_week, sum(forecast_units) as forecast_units
    from {{ ref('fct_forecast') }}
    where is_latest_run and model_role = 'SELECTED'
    group by 1
),

recent as (
    select avg(units) as avg_units
    from (
        select week_start_date, sum(units) as units
        from {{ ref('mart_forecast_features') }}
        group by 1
        order by 1 desc
        limit 8
    ) w
)

select fc.target_week, fc.forecast_units, r.avg_units,
       round(100.0 * (fc.forecast_units / r.avg_units - 1), 1) as diff_pct
from fc cross join recent r
where fc.forecast_units not between 0.5 * r.avg_units and 1.5 * r.avg_units
