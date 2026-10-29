"""Backtest semua model, pilih yang terbaik, forecast 8 minggu ke depan, simpan ke schema forecast.

    python -m forecasting.train_backtest [--horizon 8 --windows 4 --step 4] [--dry-run]

Pemilihan model: WAPE terendah di level kategori x region (target PLAN 2.8: mengalahkan baseline).
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import uuid

import pandas as pd

from forecasting import features, metrics, models
from ingestion.common.connections import dwh_connect

log = logging.getLogger(__name__)
SELECTION_LEVEL = "category_region"
MIN_TRAIN_WEEKS = 8


def save(run_id: str, panel: pd.DataFrame, attrs: pd.DataFrame, selected: str, scores: pd.DataFrame,
         cv: pd.DataFrame, fc: pd.DataFrame, params: dict) -> None:
    model_cols = [c for c in fc.columns if c not in ("unique_id", "ds")]
    fc_long = (fc.melt(id_vars=["unique_id", "ds"], value_vars=model_cols, var_name="model", value_name="forecast_units")
               .merge(attrs[["unique_id", "sku_id", "region"]], on="unique_id"))
    cv_cat = (cv.merge(attrs[["unique_id", "category", "region"]], on="unique_id")
              .groupby(["cutoff", "ds", "category", "region"], as_index=False)
              [["y"] + [c for c in cv.columns if c not in ("unique_id", "ds", "cutoff", "y")]].sum())
    cv_long = cv_cat.melt(id_vars=["cutoff", "ds", "category", "region", "y"], var_name="model",
                          value_name="forecast_units")

    with dwh_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into forecast.forecast_runs (run_id, cutoff_week, horizon_weeks, n_series, selected_model, "
            "selection_level, params) values (%s, %s, %s, %s, %s, %s, %s)",
            (run_id, panel["ds"].max().date(), params["horizon"], panel["unique_id"].nunique(), selected,
             SELECTION_LEVEL, json.dumps(params)))
        with cur.copy("copy forecast.forecast_values (run_id, sku_id, region, target_week, model, forecast_units) "
                      "from stdin") as cp:
            for r in fc_long.itertuples():
                cp.write_row((run_id, r.sku_id, r.region, r.ds.date(), r.model, round(float(r.forecast_units), 4)))
        with cur.copy("copy forecast.backtest_metrics (run_id, model, level, category, wape, bias, mae, "
                      "actual_units, n_points) from stdin") as cp:
            for r in scores.itertuples():
                cp.write_row((run_id, r.model, r.level, r.category if r.category is not None else "ALL",
                              r.wape, r.bias, r.mae, r.actual_units, r.n_points))
        with cur.copy("copy forecast.backtest_values (run_id, model, cutoff_week, target_week, category, region, "
                      "actual_units, forecast_units) from stdin") as cp:
            for r in cv_long.itertuples():
                cp.write_row((run_id, r.model, r.cutoff.date(), r.ds.date(), r.category, r.region,
                              float(r.y), round(float(r.forecast_units), 4)))
        conn.commit()


def run(horizon: int = 8, n_windows: int = 4, step: int = 4, dry_run: bool = False) -> dict:
    t0 = time.time()
    panel, attrs = features.to_panel(features.load_weekly())
    log.info("%d seri, %d minggu (%s s/d %s)", panel["unique_id"].nunique(), panel["ds"].nunique(),
             panel["ds"].min().date(), panel["ds"].max().date())

    # Backtest hanya untuk seri yang cukup panjang (SKU baru listing belum bisa dievaluasi 4 lipatan);
    # forecast produksi tetap untuk semua seri.
    min_len = horizon + step * (n_windows - 1) + MIN_TRAIN_WEEKS
    lengths = panel.groupby("unique_id").size()
    eligible = lengths[lengths >= min_len].index
    bt_panel = panel[panel["unique_id"].isin(eligible)]
    log.info("Backtest: %d dari %d seri (panjang >= %d minggu), %.1f%% volume",
             len(eligible), len(lengths), min_len, 100 * bt_panel["y"].sum() / panel["y"].sum())
    cv = models.backtest(bt_panel, attrs, h=horizon, n_windows=n_windows, step=step)
    model_cols = [c for c in cv.columns if c not in ("unique_id", "ds", "cutoff", "y")]
    scores = metrics.score(cv, model_cols, attrs)
    overall = scores[scores["category"].isna()].pivot(index="model", columns="level", values="wape")
    selected = overall[SELECTION_LEVEL].idxmin()
    best_baseline = overall.loc[models.BASELINES, SELECTION_LEVEL].min()
    log.info("WAPE backtest:\n%s", overall.round(3).to_string())

    fc = models.forecast(panel, attrs, selected, h=horizon)
    run_id = str(uuid.uuid4())
    params = {"horizon": horizon, "n_windows": n_windows, "step": step, "models": model_cols,
              "backtest_series": int(len(eligible)), "backtest_min_weeks": int(min_len)}
    if not dry_run:
        save(run_id, panel, attrs, selected, scores, cv, fc, params)
    result = {
        "run_id": run_id if not dry_run else None,
        "selected_model": selected,
        "wape_category_region": round(float(overall.loc[selected, SELECTION_LEVEL]), 4),
        "wape_best_baseline": round(float(best_baseline), 4),
        "beats_baseline": bool(overall.loc[selected, SELECTION_LEVEL] < best_baseline),
        "wape_by_model": overall.round(4).to_dict(),
        "backtest_series": int(len(eligible)),
        "seconds": round(time.time() - t0, 1),
    }
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--horizon", type=int, default=8)
    p.add_argument("--windows", type=int, default=4)
    p.add_argument("--step", type=int, default=4)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.horizon, a.windows, a.step, a.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
