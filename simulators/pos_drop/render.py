"""Sell-out truth -> file CSV mingguan per retailer (dikirim tiap Selasa) + chaos.

Chaos: baris dobel, EAN kehilangan leading zero, baris retur bernilai negatif,
toko tidak lapor satu minggu, harga tidak masuk akal (outlier).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from simulators.settings import OUTBOX_DIR


def render_pos_files(sellout: pd.DataFrame, products: pd.DataFrame, stores: pd.DataFrame,
                     retailer_items: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    ch = cfg["chaos"]["pos"]
    s = (sellout
         .merge(stores[["store_id", "retailer_code", "retailer_store_code", "store_name"]], on="store_id")
         .merge(products[["product_id", "ean", "product_name"]], on="product_id")
         .merge(retailer_items, on=["retailer_code", "product_id"]))
    s["week_start"] = s["sales_date"] - pd.to_timedelta(s["sales_date"].dt.day_of_week, unit="D")

    out_dir = OUTBOX_DIR / "pos"
    index = []
    for (ret, week_start), wk in s.groupby(["retailer_code", "week_start"]):
        # Toko yang tidak lapor minggu ini
        stores_in = wk["retailer_store_code"].unique()
        skip = stores_in[rng.random(len(stores_in)) < ch["missing_store_week_prob"]]
        wk = wk[~wk["retailer_store_code"].isin(skip)]

        f = pd.DataFrame({
            "STORE_CODE": wk["retailer_store_code"],
            "STORE_NAME": wk["store_name"].str.upper(),
            "ARTICLE_CODE": wk["retailer_item_code"],
            "EAN": wk["ean"],
            "DESCRIPTION": wk["product_name"].str.upper().str.slice(0, 30),
            "SALES_DATE": wk["sales_date"].dt.strftime("%Y-%m-%d"),
            "QTY": wk["units"].astype(int),
            "GROSS_SALES": wk["gross_sales"],
            "DISCOUNT": wk["discount"],
            "NET_SALES": wk["net_sales"],
        })
        n = len(f)
        strip = f["EAN"].str.startswith("0") & (rng.random(n) < ch["ean_strip_zero_rate"])
        f.loc[strip, "EAN"] = f.loc[strip, "EAN"].str.lstrip("0")
        outlier = rng.random(n) < ch["price_outlier_rate"]
        f.loc[outlier, ["GROSS_SALES", "NET_SALES"]] = f.loc[outlier, ["GROSS_SALES", "NET_SALES"]] * 100

        returns = f[rng.random(n) < ch["return_row_rate"]].copy()
        if len(returns):
            q = rng.integers(1, 4, len(returns))
            unit_gross = returns["GROSS_SALES"] / returns["QTY"]
            unit_net = returns["NET_SALES"] / returns["QTY"]
            returns["QTY"] = -q
            returns["GROSS_SALES"] = (-q * unit_gross).round()
            returns["NET_SALES"] = (-q * unit_net).round()
            returns["DISCOUNT"] = returns["GROSS_SALES"] - returns["NET_SALES"]
        dups = f[rng.random(n) < ch["duplicate_row_rate"]]
        f = pd.concat([f, returns, dups]).sort_values(["SALES_DATE", "STORE_CODE", "ARTICLE_CODE"], kind="stable")

        iso = week_start.isocalendar()
        week_label = f"{iso.year}-{iso.week:02d}"
        key = f"pos/{ret}/week={week_label}/sellout_{ret}_{iso.year}{iso.week:02d}.csv"
        arrival = week_start + pd.Timedelta(days=8, hours=int(rng.integers(7, 11)), minutes=int(rng.integers(60)))
        local = out_dir / key
        local.parent.mkdir(parents=True, exist_ok=True)
        f.to_csv(local, index=False, float_format="%.0f")
        index.append({"retailer_code": ret, "object_key": key, "week_start": week_start, "arrival_ts": arrival,
                      "local_path": str(local), "n_rows": len(f)})
    return pd.DataFrame(index)
