{#
  PLAN 2.4.3: 1 baris = SKU x region x minggu target x versi forecast (run).
  Semua run disimpan (snapshot) supaya akurasi forecast bisa dinilai setelah aktual masuk;
  is_latest_run menandai versi terbaru. Kolom model_role: SELECTED = model terpilih, BASELINE = Naive.
#}
with runs as (
    select *, row_number() over (order by created_at desc) = 1 as is_latest_run
    from {{ source('forecast', 'forecast_runs') }}
),

actuals as (
    select week_start_date, sku_id, region, units
    from {{ ref('mart_forecast_features') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['v.run_id', 'v.sku_id', 'v.region', 'v.target_week', 'v.model']) }} as forecast_line_id,
    v.run_id,
    r.created_at                                    as forecast_created_at,
    r.is_latest_run,
    r.cutoff_week,
    to_char(v.target_week, 'YYYYMMDD')              as target_date_key,
    v.target_week,
    (v.target_week - r.cutoff_week) / 7             as horizon_week,
    coalesce(p.product_key, '-1')                   as product_key,
    v.sku_id,
    v.region,
    v.model,
    case when v.model = r.selected_model then 'SELECTED' else 'BASELINE' end as model_role,
    v.forecast_units,
    a.units                                         as actual_units
from {{ source('forecast', 'forecast_values') }} v
join runs r using (run_id)
left join {{ ref('dim_product') }} p on p.sku_id = v.sku_id and p.is_current
left join actuals a on a.sku_id = v.sku_id and a.region = v.region and a.week_start_date = v.target_week
