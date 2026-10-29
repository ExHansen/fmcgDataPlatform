"""Hasil dbt dibandingkan dengan kebenaran simulator (data/sim/truth).

Membaca warehouse utama (read-only) setelah `python scripts/run_dbt.py build`.
Jalankan: RUN_INTEGRATION=1 pytest tests/test_integration_dbt.py
"""
import os

import pandas as pd
import psycopg
import pytest

from ingestion.common.settings import env
from simulators.dms_sftp.render import _local_product_codes
from simulators.settings import TRUTH_DIR

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="butuh warehouse + dbt build")


@pytest.fixture(scope="module")
def query():
    conn = psycopg.connect(host=env("DWH_DB_HOST"), port=env("DWH_DB_PORT"), dbname=env("DWH_DB_NAME"),
                           user=env("DWH_DB_USER"), password=env("DWH_DB_PASSWORD"))

    def run(sql: str) -> pd.DataFrame:
        cur = conn.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])

    yield run
    conn.close()


def test_product_mapping_matches_truth(query):
    products = pd.read_parquet(TRUTH_DIR / "products.parquet")
    codes = _local_product_codes(products)
    truth = pd.concat([
        pd.DataFrame({"source_system": src, "source_id": codes[dist], "expected": products["matnr"].str.lstrip("0")})
        for src, dist in [("DMS_A", "DIST_A"), ("DMS_B", "DIST_B"), ("DMS_C", "DIST_C")]
    ])
    mapped = query("select source_system, source_id, sku_id from intermediate.int_product_xref "
                   "where source_system like 'DMS%' and sku_id is not null")
    m = mapped.merge(truth, on=["source_system", "source_id"], how="left")
    assert len(m) > 6000
    assert (m["sku_id"] == m["expected"]).all(), m[m["sku_id"] != m["expected"]].head()


def test_store_mapping_matches_truth(query):
    stores = pd.read_parquet(TRUTH_DIR / "stores.parquet")
    x = query("select source_id, store_id from intermediate.int_store_xref where source_system like 'DMS%'")
    m = x.merge(stores.drop(columns="store_id"), left_on="source_id", right_on="distributor_outlet_code")
    assert len(m) == len(stores)
    assert (m["store_id"] == m["retailer_store_code"]).all()


def test_secondary_qty_pcs_matches_truth(query):
    """Setelah versi file terakhir + konversi karton, qty & nilai per hari = kebenaran secondary."""
    sec = pd.read_parquet(TRUTH_DIR / "secondary.parquet")
    got = query("select distributor_code, invoice_date, sum(qty_pcs) qty, sum(net_value) net "
                "from intermediate.int_secondary_sales_mapped where sku_id is not null group by 1, 2")
    got["invoice_date"] = pd.to_datetime(got["invoice_date"])
    unmapped = set(query("select source_id from ops.unmapped_ids where source_system = 'DMS_A'")["source_id"])
    codes = _local_product_codes(pd.read_parquet(TRUTH_DIR / "products.parquet")).set_index("product_id")["DIST_A"]
    sec = sec[~((sec["distributor_code"] == "DIST_A") & sec["product_id"].map(codes).isin(unmapped))]
    exp = (sec.groupby(["distributor_code", "ship_date"], as_index=False)
           .agg(qty_exp=("qty_pcs", "sum"), net_exp=("net_value", "sum")))
    m = got.merge(exp, left_on=["distributor_code", "invoice_date"], right_on=["distributor_code", "ship_date"])
    assert len(m) == len(got) > 700
    assert (m["qty"].astype(float) == m["qty_exp"]).all()
    assert (m["net"].astype(float) - m["net_exp"]).abs().max() < 1


def test_pos_dedup_and_ean_repair(query):
    s = query("select count(*) n, count(*) filter (where is_return) returns, "
              "count(*) filter (where is_ean_repaired) repaired, count(*) filter (where is_price_outlier) outliers, "
              "sum(qty) filter (where not is_return) units from staging.stg_pos__sellout")
    sellout = pd.read_parquet(TRUTH_DIR / "sellout.parquet")
    pos_index = pd.read_parquet(TRUTH_DIR / "pos_index.parquet")
    weeks = query("select distinct business_date from ops.file_manifest where source_system like 'POS%'")
    truth = sellout[(sellout["sales_date"] - pd.to_timedelta(sellout["sales_date"].dt.day_of_week, unit="D"))
                    .dt.date.isin(weeks["business_date"])]
    row = s.iloc[0]
    assert row["repaired"] > 0 and row["returns"] > 0 and row["outliers"] > 0
    # Baris dobel dibuang; toko yang tidak lapor membuat unit sedikit di bawah kebenaran
    assert row["n"] - row["returns"] <= len(truth)
    assert float(row["units"]) == pytest.approx(truth["units"].sum(), rel=0.02)
    assert len(pos_index) > 0
