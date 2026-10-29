"""Muat mart_forecast_features -> panel mingguan per seri (SKU x region) dengan minggu kosong = 0."""
from __future__ import annotations

import pandas as pd

from ingestion.common.connections import dwh_connect

SEP = "|"


def load_weekly() -> pd.DataFrame:
    with dwh_connect() as conn:
        cur = conn.execute("select week_start_date, sku_id, region, category, brand, units "
                           "from marts.mart_forecast_features")
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    df["week_start_date"] = pd.to_datetime(df["week_start_date"])
    df["units"] = df["units"].astype(float)
    return df


def to_panel(weekly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Format Nixtla (unique_id, ds, y) + tabel atribut seri.

    Tiap seri dimulai dari minggu jual pertamanya (produk belum listing != penjualan nol)
    dan diisi 0 sampai minggu terakhir data.
    """
    weekly = weekly.assign(unique_id=weekly["sku_id"] + SEP + weekly["region"])
    last = weekly["week_start_date"].max()
    first = weekly.groupby("unique_id")["week_start_date"].min()
    frames = [pd.DataFrame({"unique_id": uid, "ds": pd.date_range(start, last, freq="W-MON")})
              for uid, start in first.items()]
    panel = (pd.concat(frames, ignore_index=True)
             .merge(weekly[["unique_id", "week_start_date", "units"]],
                    left_on=["unique_id", "ds"], right_on=["unique_id", "week_start_date"], how="left")
             .drop(columns="week_start_date")
             .rename(columns={"units": "y"}))
    panel["y"] = panel["y"].fillna(0.0)
    attrs = (weekly.groupby("unique_id")
             .agg(sku_id=("sku_id", "first"), region=("region", "first"),
                  category=("category", "first"), brand=("brand", "first"))
             .reset_index())
    return panel.sort_values(["unique_id", "ds"]).reset_index(drop=True), attrs
