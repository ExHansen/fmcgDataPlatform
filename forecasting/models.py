"""Definisi model & backtest rolling-origin (PLAN 2.8).

Baseline: Naive (minggu lalu) dan rata-rata 4 minggu. Data baru 1 tahun, jadi seasonal naive tahunan
belum bisa dipakai. Statistik: AutoETS, ADIDA (untuk penjualan intermittent). Croston sempat dicoba
tapi over-forecast +155% di data ini (bias Croston yang dikenal pada seri sangat jarang laku), jadi diganti ADIDA.
ML global: LightGBM satu model untuk semua seri, fitur lag + rolling + kalender + atribut statis.
Ensemble: rata-rata MA4, ETS, ADIDA, LightGBM.
Tidak ada fitur harga/promo masa depan (belum diketahui saat forecast dibuat).
"""
from __future__ import annotations

import lightgbm as lgb
import pandas as pd
from mlforecast import MLForecast
from mlforecast.lag_transforms import RollingMean
from statsforecast import StatsForecast
from statsforecast.models import ADIDA, AutoETS, Naive, WindowAverage

FREQ = "W-MON"
BASELINES = ["Naive", "MA4"]
ENSEMBLE_MEMBERS = ["MA4", "ETS", "ADIDA", "LightGBM"]


def stats_models() -> list:
    return [Naive(), WindowAverage(window_size=4, alias="MA4"), AutoETS(season_length=1, alias="ETS"),
            ADIDA()]


def ml_forecaster(seed: int = 42) -> MLForecast:
    model = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=20,
                              objective="tweedie", subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                              random_state=seed, verbose=-1)
    return MLForecast(models={"LightGBM": model}, freq=FREQ, lags=[1, 2, 3, 4, 8],
                      lag_transforms={1: [RollingMean(window_size=4), RollingMean(window_size=8)]},
                      date_features=["month"])


def _with_static(panel: pd.DataFrame, attrs: pd.DataFrame) -> pd.DataFrame:
    s = attrs[["unique_id", "category", "brand", "region"]].copy()
    for col in ["category", "brand", "region"]:
        s[col] = s[col].astype("category").cat.codes
    return panel.merge(s, on="unique_id")


def backtest(panel: pd.DataFrame, attrs: pd.DataFrame, h: int, n_windows: int, step: int) -> pd.DataFrame:
    """Prediksi rolling-origin semua model: kolom unique_id, ds, cutoff, y, <model...>."""
    sf = StatsForecast(models=stats_models(), freq=FREQ, n_jobs=1)
    cv_stats = sf.cross_validation(df=panel, h=h, n_windows=n_windows, step_size=step)
    mf = ml_forecaster()
    cv_ml = mf.cross_validation(df=_with_static(panel, attrs), h=h, n_windows=n_windows, step_size=step,
                                static_features=["category", "brand", "region"])
    cv = cv_stats.merge(cv_ml[["unique_id", "ds", "cutoff", "LightGBM"]], on=["unique_id", "ds", "cutoff"])
    cv[ENSEMBLE_MEMBERS] = cv[ENSEMBLE_MEMBERS].clip(lower=0)
    cv["Ensemble"] = cv[ENSEMBLE_MEMBERS].mean(axis=1)
    model_cols = [c for c in cv.columns if c not in ("unique_id", "ds", "cutoff", "y")]
    cv[model_cols] = cv[model_cols].clip(lower=0)
    return cv


def forecast(panel: pd.DataFrame, attrs: pd.DataFrame, model: str, h: int) -> pd.DataFrame:
    """Latih di seluruh data lalu forecast h minggu; selalu sertakan baseline Naive untuk pembanding.
    Seri yang terlalu pendek untuk ETS (SKU baru listing) memakai fallback Naive."""
    sf = StatsForecast(models=stats_models(), freq=FREQ, n_jobs=1, fallback_model=Naive())
    out = sf.forecast(df=panel, h=h)
    if model in ("LightGBM", "Ensemble"):
        mf = ml_forecaster()
        mf.fit(_with_static(panel, attrs), static_features=["category", "brand", "region"])
        out = out.merge(mf.predict(h), on=["unique_id", "ds"])
    if model == "Ensemble":
        out["Ensemble"] = out[ENSEMBLE_MEMBERS].clip(lower=0).mean(axis=1)
    keep = ["unique_id", "ds"] + sorted({model, "Naive"})
    out = out[keep].copy()
    out[keep[2:]] = out[keep[2:]].clip(lower=0)
    return out
