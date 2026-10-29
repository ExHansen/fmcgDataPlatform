"""Bangun seluruh "kebenaran" simulasi + data tiap sistem sumber (deterministik dari seed).

Output di data/sim/:
  truth/*.parquet        kebenaran bisnis (untuk tes & validasi, TIDAK dibaca pipeline)
  truth/sap/*.parquet    tabel SAP berversi (_event_date)
  outbox/dms, outbox/pos file yang akan "dikirim" sistem sumber + index-nya
"""
from __future__ import annotations

import logging
import shutil

import numpy as np
import pandas as pd

from simulators.common import dataset, masters, supply
from simulators.dms_sftp.render import render_dms_files
from simulators.pos_drop.render import render_pos_files
from simulators.sap_mock import build as sap_build
from simulators.settings import OUTBOX_DIR, TRUTH_DIR, config

log = logging.getLogger(__name__)


def generate() -> dict[str, int]:
    cfg = config()
    rng = np.random.default_rng(cfg["seed"])

    log.info("Memuat dataset dunnhumby ...")
    trans, all_products = dataset.load_source(cfg)
    principal = dataset.principal_products(all_products, cfg)
    sellout = dataset.build_sellout(trans, principal, cfg, rng)
    del trans

    products = masters.build_products(principal, sellout, cfg, rng)
    distributors = masters.build_distributors(cfg)
    stores = masters.build_stores(sellout, distributors, cfg, rng)
    retailer_items = masters.build_retailer_items(products, cfg, rng)

    log.info("Simulasi secondary & primary ...")
    prices = supply.product_prices(sellout, products, cfg)
    secondary = supply.build_secondary(sellout, stores, prices, cfg, rng)
    orders = supply.build_primary_orders(secondary, prices, cfg, rng)

    log.info("Membangun tabel SAP ...")
    sap = sap_build.build_masters(products, distributors, cfg, sellout["sales_date"].min(), rng)
    sap.update(sap_build.build_transactions(orders, products, distributors, prices, cfg, rng))

    for d in (TRUTH_DIR, OUTBOX_DIR):
        shutil.rmtree(d, ignore_errors=True)
    (TRUTH_DIR / "sap").mkdir(parents=True)

    log.info("Render file distributor & POS ...")
    dms_index = render_dms_files(secondary, products, stores, distributors, cfg, rng)
    pos_index = render_pos_files(sellout, products, stores, retailer_items, cfg, rng)

    truth = {
        "products": products, "distributors": distributors.assign(cities=distributors["cities"].map(",".join)),
        "stores": stores.assign(delivery_weekdays=stores["delivery_weekdays"].map(lambda t: ",".join(map(str, t)))),
        "retailer_items": retailer_items, "prices": prices, "sellout": sellout,
        "secondary": secondary, "primary_orders": orders,
        "dms_index": dms_index, "pos_index": pos_index,
    }
    for name, df in truth.items():
        df.to_parquet(TRUTH_DIR / f"{name}.parquet", index=False)
    for name, df in sap.items():
        df.to_parquet(TRUTH_DIR / "sap" / f"{name}.parquet", index=False)

    stats = {f"truth.{k}": len(v) for k, v in truth.items()}
    stats.update({f"sap.{k}": len(v) for k, v in sap.items()})
    stats["period_start"] = str(sellout["sales_date"].min().date())
    stats["period_end"] = str(sellout["sales_date"].max().date())
    return stats
