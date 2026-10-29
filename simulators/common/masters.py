"""Master data kanonik: produk (SKU), distributor, dan toko.

Ini "kebenaran" yang tidak dilihat pipeline secara langsung; tiap sistem sumber
hanya melihat kodenya sendiri (MATNR, EAN, kode lokal distributor, kode retailer).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from simulators.common.ids import ean13, sap_alpha

# Brand fiktif per manufacturer dunnhumby
BRANDS = {
    "764": ("KLU", "KILAU"),
    "103": ("SGR", "SEGARA"),
    "1208": ("TRT", "TIRTA"),
    "544": ("RNY", "RENYAH"),
    "317": ("SSK", "SUSUKU"),
    "1251": ("HGT", "HANGAT"),
    "194": ("PGI", "PAGI"),
    "1046": ("CRA", "CERIA"),
}
GS1_COMPANY_PREFIX = "8991234"   # 899 = prefix GS1 Indonesia


def build_products(products: pd.DataFrame, sellout: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    p = products[products["product_id"].isin(sellout["product_id"].unique())].copy()
    p = p.sort_values(["manufacturer_id", "product_category", "product_id"]).reset_index(drop=True)
    n = len(p)

    p["sku_id"] = [f"SKU{100001 + i}" for i in range(n)]
    p["matnr"] = [sap_alpha(100001 + i, 18) for i in range(n)]
    # Sebagian produk impor memakai UPC-A (EAN-13 berawalan 0) -> rawan kehilangan leading zero
    is_upc = rng.random(n) < cfg["chaos"]["pos"]["upc_share"]
    upc_body = rng.integers(10**9, 10**10, n)
    p["ean"] = [
        ean13(f"0{int(b):011d}") if u else ean13(f"{GS1_COMPANY_PREFIX}{i + 1:05d}")
        for i, (u, b) in enumerate(zip(is_upc, upc_body))
    ]
    p["brand_code"] = p["manufacturer_id"].map(lambda m: BRANDS[m][0])
    p["brand"] = p["manufacturer_id"].map(lambda m: BRANDS[m][1])
    p["category"] = p["product_category"].fillna("OTHER").str.strip()
    p["subcategory"] = p["product_type"].fillna("OTHER").str.strip()
    cats = sorted(p["category"].unique())
    p["matkl"] = p["category"].map({c: f"NC{i + 1:03d}" for i, c in enumerate(cats)})
    p["prdha"] = "NCG" + p["brand_code"]
    size = p["package_size"].fillna("").str.strip()
    p["product_name"] = (p["brand"] + " " + p["subcategory"].str.title() + " " + size).str.strip().str.slice(0, 40)
    p["pcs_per_case"] = rng.choice(cfg["supply_chain"]["case_sizes"], n)

    first_sale = sellout.groupby("product_id")["sales_date"].min()
    data_start = sellout["sales_date"].min()
    created = p["product_id"].map(first_sale) - pd.to_timedelta(rng.integers(20, 60, n), unit="D")
    p["created_date"] = created.where(created < data_start, data_start - pd.Timedelta(days=180))
    cols = ["product_id", "sku_id", "matnr", "ean", "product_name", "brand_code", "brand", "category",
            "subcategory", "matkl", "prdha", "pcs_per_case", "created_date", "manufacturer_id"]
    return p[cols]


def build_distributors(cfg: dict) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(cfg["distributors"]):
        rows.append({
            "distributor_code": d["code"],
            "kunnr": sap_alpha(200001 + i, 10),
            "name": d["name"],
            "region": d["region"],
            "file_format": d["file_format"],
            "cities": d["cities"],
        })
    return pd.DataFrame(rows)


def build_stores(sellout: pd.DataFrame, distributors: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    store_ids = sellout.groupby("store_id")["units"].sum().sort_values(ascending=False).index.tolist()
    retailers = cfg["retailers"]
    rows = []
    for i, sid in enumerate(store_ids):
        r = retailers[i % len(retailers)]
        d = distributors.iloc[(i // len(retailers)) % len(distributors)]
        city = d["cities"][int(rng.integers(len(d["cities"])))]
        n = i + 1
        rows.append({
            "store_id": sid,
            "canonical_store_id": f"ST{n:04d}",
            "retailer_code": r["code"],
            "retailer_name": r["name"],
            "store_format": r["format"],
            "retailer_store_code": f"{r['code']}-{int(rng.integers(100, 999)):03d}{n:02d}",
            "store_name": f"{r['name']} {city} {n:02d}",
            "city": city,
            "region": d["region"],
            "distributor_code": d["distributor_code"],
            # Kode outlet versi tiap distributor berbeda formatnya
            "distributor_outlet_code": {
                "DIST_A": f"OT{50000 + n * 7:05d}",
                "DIST_B": f"CUST-{n:04d}",
                "DIST_C": f"{300000 + n * 13}",
            }[d["distributor_code"]],
            "delivery_weekdays": [(0, 3), (1, 4), (2, 5)][i % 3],
        })
    return pd.DataFrame(rows)


def build_retailer_items(products: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Kode artikel versi retailer (tiap retailer punya penomoran sendiri)."""
    frames = []
    for r in cfg["retailers"]:
        codes = rng.choice(np.arange(1_000_000, 9_999_999), len(products), replace=False)
        prefix = {"MTM": "", "SNT": "SNT", "LST": "2"}.get(r["code"], "")
        frames.append(pd.DataFrame({
            "retailer_code": r["code"],
            "product_id": products["product_id"].to_numpy(),
            "retailer_item_code": [f"{prefix}{c}" for c in codes],
        }))
    return pd.concat(frames, ignore_index=True)
