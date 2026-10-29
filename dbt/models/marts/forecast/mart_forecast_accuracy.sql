{# Hasil backtest per run x model x level (WAPE, bias, akurasi = 1 - WAPE). #}
select
    m.run_id,
    r.created_at                                    as forecast_created_at,
    r.selected_model,
    m.model,
    m.model = r.selected_model                      as is_selected,
    m.model in ('Naive', 'MA4')                     as is_baseline,
    m.level,
    m.category,
    m.wape,
    round(greatest(0, 1 - m.wape) * 100, 1)         as forecast_accuracy_pct,
    m.bias,
    m.mae,
    m.actual_units,
    m.n_points
from {{ source('forecast', 'backtest_metrics') }} m
join {{ source('forecast', 'forecast_runs') }} r using (run_id)
