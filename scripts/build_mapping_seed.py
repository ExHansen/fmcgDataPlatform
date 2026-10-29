"""Bangun dbt/seeds/dms_product_mapping.csv: mapping kode produk lokal DIST_A -> MATNR SAP.

Mensimulasikan file mapping yang dikelola tim MDM principal. Kode lokal DIST_A tidak punya
kunci bersama dengan SAP dan banyak nama produk kembar, jadi butuh keputusan manusia.
Hanya produk yang mulai dikirim sebelum CUTOFF yang sudah dipetakan; listing baru sesudahnya
belum, sehingga muncul di ops.unmapped_ids sampai tim MDM memperbarui file ini.

    python scripts/build_mapping_seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulators.dms_sftp.render import _local_product_codes  # noqa: E402
from simulators.settings import TRUTH_DIR  # noqa: E402

CUTOFF = pd.Timestamp("2026-09-01")
OUT = ROOT / "dbt" / "seeds" / "dms_product_mapping.csv"


def main() -> None:
    products = pd.read_parquet(TRUTH_DIR / "products.parquet")
    secondary = pd.read_parquet(TRUTH_DIR / "secondary.parquet")
    codes = _local_product_codes(products)[["product_id", "DIST_A"]]
    first_ship = (secondary[secondary["distributor_code"] == "DIST_A"]
                  .groupby("product_id")["ship_date"].min().rename("first_ship"))
    m = (codes.merge(first_ship, on="product_id")
         .merge(products[["product_id", "matnr"]], on="product_id"))
    m = m[m["first_ship"] < CUTOFF].sort_values("DIST_A")
    out = pd.DataFrame({
        "distributor_code": "DIST_A",
        "local_product_code": m["DIST_A"],
        "sap_matnr": m["matnr"],
        "mapped_by": "mdm.team",
        "mapped_at": (m["first_ship"] + pd.Timedelta(days=7)).dt.strftime("%Y-%m-%d"),
    })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"{len(out)} mapping ditulis ke {OUT} (dari {len(first_ship)} produk yang pernah dikirim DIST_A)")


if __name__ == "__main__":
    main()
