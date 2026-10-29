"""Metrik akurasi forecast (PLAN 2.8). Forecast accuracy FMCG = 1 - WAPE."""
from __future__ import annotations

import pandas as pd


def wape(actual: pd.Series, pred: pd.Series) -> float:
    total = actual.abs().sum()
    return float((actual - pred).abs().sum() / total) if total else float("nan")


def bias(actual: pd.Series, pred: pd.Series) -> float:
    """> 0 = over-forecast (stok berlebih), < 0 = under-forecast (risiko out-of-stock)."""
    total = actual.sum()
    return float((pred - actual).sum() / total) if total else float("nan")


def score(cv: pd.DataFrame, models: list[str], attrs: pd.DataFrame) -> pd.DataFrame:
    """Metrik per model di 3 level: seri (sku x region), kategori x region, total; plus per kategori."""
    df = cv.merge(attrs[["unique_id", "category", "region"]], on="unique_id")
    rows = []
    levels = {
        "sku_region": df,
        "category_region": df.groupby(["category", "region", "cutoff", "ds"], as_index=False)[["y", *models]].sum(),
        "total": df.groupby(["cutoff", "ds"], as_index=False)[["y", *models]].sum(),
    }
    for level, d in levels.items():
        for m in models:
            rows.append({"model": m, "level": level, "category": None, "wape": wape(d["y"], d[m]),
                         "bias": bias(d["y"], d[m]), "mae": float((d["y"] - d[m]).abs().mean()),
                         "actual_units": float(d["y"].sum()), "n_points": len(d)})
    cat = levels["category_region"]
    for (category, m) in ((c, m) for c in cat["category"].unique() for m in models):
        d = cat[cat["category"] == category]
        rows.append({"model": m, "level": "category_region", "category": category, "wape": wape(d["y"], d[m]),
                     "bias": bias(d["y"], d[m]), "mae": float((d["y"] - d[m]).abs().mean()),
                     "actual_units": float(d["y"].sum()), "n_points": len(d)})
    return pd.DataFrame(rows)
