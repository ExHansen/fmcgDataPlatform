"""Subset dataset dunnhumby -> sell-out harian "kebenaran" per toko x produk.

Langkah: filter portofolio principal & toko, geser tanggal, proyeksikan panel ke
volume toko, konversi USD -> IDR. Hasil ini menjadi dasar semua sistem sumber.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pyreadr

from simulators.settings import ROOT

# Data asli: 2017-01-01 (Minggu) s/d 2017-12-31 (Minggu); beberapa baris 2018-01-01 dibuang.
SOURCE_START = date(2017, 1, 1)
SOURCE_END = date(2017, 12, 31)


def date_shift_days(anchor_end: date) -> int:
    shift = (anchor_end - SOURCE_END).days
    if shift % 7:
        raise ValueError(f"anchor_end_date {anchor_end} harus hari Minggu agar hari dalam minggu tetap sama")
    return shift


def load_source(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = ROOT / cfg["dataset"]["dir"]
    trans = pyreadr.read_r(str(d / "transactions.rds"))[None]
    products = pyreadr.read_r(str(d / "products.rda"))["products"]
    products["brand"] = products["brand"].astype(str)
    return trans, products


def principal_products(products: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    ds = cfg["dataset"]
    mask = (
        products["department"].isin(ds["departments"])
        & (products["brand"] == ds["brand_type"])
        & products["manufacturer_id"].isin(ds["principal_manufacturers"])
    )
    return products.loc[mask].reset_index(drop=True)


def build_sellout(trans: pd.DataFrame, products: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Sell-out harian (store_id, product_id, sales_date) dengan nilai IDR."""
    ds = cfg["dataset"]
    t = trans[trans["product_id"].isin(products["product_id"]) & (trans["quantity"] > 0)].copy()
    t["src_date"] = t["transaction_timestamp"].dt.date
    t = t[t["src_date"] <= SOURCE_END]

    top_stores = t.groupby("store_id").size().sort_values(ascending=False).index[: ds["n_stores"]]
    t = t[t["store_id"].isin(top_stores)]

    daily = (
        t.groupby(["store_id", "product_id", "src_date"], as_index=False)
        .agg(
            qty=("quantity", "sum"),
            net_usd=("sales_value", "sum"),
            disc_usd=("retail_disc", "sum"),
            match_usd=("coupon_match_disc", "sum"),
        )
    )
    # Panel -> toko: jumlah pembeli diproyeksikan dengan noise Poisson (bukan perkalian
    # kaku) supaya qty tidak selalu kelipatan faktor.
    factor = ds["panel_projection_factor"]
    daily["units"] = rng.poisson(daily["qty"].to_numpy() * factor)
    daily = daily[daily["units"] > 0].copy()

    fx = ds["usd_to_idr"]
    net_unit = daily["net_usd"] / daily["qty"] * fx
    gross_unit = (daily["net_usd"] + daily["disc_usd"] + daily["match_usd"]) / daily["qty"] * fx
    # Harga retail Indonesia dibulatkan ke Rp100
    daily["gross_unit_price"] = (gross_unit / 100).round().clip(lower=1) * 100
    daily["net_unit_price"] = np.minimum((net_unit / 100).round().clip(lower=1) * 100, daily["gross_unit_price"])
    daily["gross_sales"] = daily["units"] * daily["gross_unit_price"]
    daily["net_sales"] = daily["units"] * daily["net_unit_price"]
    daily["discount"] = daily["gross_sales"] - daily["net_sales"]

    shift = timedelta(days=date_shift_days(date.fromisoformat(ds["anchor_end_date"])))
    daily["sales_date"] = pd.to_datetime(daily["src_date"]) + shift
    cols = ["store_id", "product_id", "sales_date", "units", "gross_unit_price", "gross_sales", "discount", "net_sales"]
    return daily[cols].sort_values(["sales_date", "store_id", "product_id"]).reset_index(drop=True)
