"""Marts & rekonsiliasi vs kebenaran simulator: masalah yang disisipkan harus terdeteksi, tanpa alarm palsu.

Membaca warehouse utama (read-only) setelah `python scripts/run_dbt.py build`.
Jalankan: RUN_INTEGRATION=1 pytest tests/test_integration_marts.py
"""
import os

import pandas as pd
import psycopg
import pytest

from ingestion.common.settings import env
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


def week_start(s: pd.Series) -> pd.Series:
    return s - pd.to_timedelta(s.dt.day_of_week, unit="D")


def test_missing_distributor_files_detected_exactly(query):
    sec = pd.read_parquet(TRUTH_DIR / "secondary.parquet")
    idx = pd.read_parquet(TRUTH_DIR / "dms_index.parquet")
    shipped = sec[["distributor_code", "ship_date"]].drop_duplicates()
    sent = idx[["distributor_code", "business_date"]].drop_duplicates().rename(columns={"business_date": "ship_date"})
    truth = shipped.merge(sent, how="left", indicator="src").query("src == 'left_only'").drop(columns="src")

    status = query("select distributor_code, business_date, status from marts.dms_file_status")
    status["ship_date"] = pd.to_datetime(status["business_date"])
    lo, hi = status["ship_date"].min(), status["ship_date"].max()
    truth = truth[truth["ship_date"].between(lo, hi)]
    found = status[status["status"] == "MISSING"][["distributor_code", "ship_date"]]

    assert len(truth) > 0, "chaos file hilang tidak terjadi di periode ini"
    assert set(map(tuple, found.values)) == set(map(tuple, truth.values))


def test_unreported_pos_store_weeks_detected_exactly(query):
    sellout = pd.read_parquet(TRUTH_DIR / "sellout.parquet")
    stores = pd.read_parquet(TRUTH_DIR / "stores.parquet")[["store_id", "retailer_store_code"]]
    sellout["week"] = week_start(sellout["sales_date"])
    expected = sellout.merge(stores)[["retailer_store_code", "week"]].drop_duplicates()
    files = pd.concat([pd.read_csv(p, usecols=["STORE_CODE", "SALES_DATE"])
                       for p in pd.read_parquet(TRUTH_DIR / "pos_index.parquet")["local_path"]])
    files["week"] = week_start(pd.to_datetime(files["SALES_DATE"]))
    reported = files[["STORE_CODE", "week"]].drop_duplicates().rename(columns={"STORE_CODE": "retailer_store_code"})

    status = query("select store_id, week_start_date, status from marts.pos_store_week_status")
    status["week"] = pd.to_datetime(status["week_start_date"])
    truth = expected.merge(reported, how="left", indicator="src").query("src == 'left_only'")
    truth = truth[truth["week"].between(status["week"].min(), status["week"].max())]
    found = status[status["status"] == "MISSING"]

    assert len(truth) > 0
    assert set(zip(found["store_id"], found["week"])) == set(zip(truth["retailer_store_code"], truth["week"]))


def test_fill_rate_matches_truth(query):
    orders = pd.read_parquet(TRUTH_DIR / "primary_orders.parquet")
    prices = pd.read_parquet(TRUTH_DIR / "prices.parquet")[["product_id", "pcs_per_case"]]
    o = orders.merge(prices)
    closed_until = query("select max(goods_issue_date) d from marts.fct_primary_sales")["d"][0]
    o = o[o["order_date"] + pd.Timedelta(days=2) <= pd.Timestamp(closed_until)]
    truth = (o["cases_delivered"] * o["pcs_per_case"]).sum() / (o["cases_final"] * o["pcs_per_case"]).sum()
    got = query("select sum(qty_delivered_pcs) / sum(qty_ordered_pcs) r from marts.fct_primary_sales "
                "where delivery_status <> 'OPEN'")["r"][0]
    assert float(got) == pytest.approx(truth, abs=1e-9)


def test_cancelled_invoices_are_rebilled_and_not_double_counted(query):
    r = query("select count(*) filter (where status <> 'PASS') bad, count(*) n from marts.recon_billing_vs_delivery")
    assert r["n"][0] > 0 and r["bad"][0] == 0
    assert query("select count(*) n from marts.fct_primary_sales where has_cancelled_invoice")["n"][0] > 0


def test_every_failed_secondary_vs_sellout_period_has_injected_cause(query):
    """Tiap FAIL harus bisa dijelaskan: toko tidak lapor POS, file distributor hilang, atau produk belum ter-mapping."""
    fails = query("""
        select r.dimension_key as store_id, r.period_start, r.period_end,
               (select count(*) from marts.pos_store_week_status p where p.store_id = r.dimension_key
                  and p.status = 'MISSING' and p.week_start_date between r.period_start and r.period_end) as pos_missing,
               (select count(*) from marts.dms_file_status d where d.distributor_code = st.distributor_code
                  and d.status = 'MISSING' and d.business_date between r.period_start - 4 and r.period_end) as dms_missing
        from marts.recon_secondary_vs_sellout r
        join marts.dim_store st on st.store_id = r.dimension_key
        where r.status = 'FAIL'""")
    assert len(fails) > 0
    unexplained = fails[(fails["pos_missing"] == 0) & (fails["dms_missing"] == 0)]
    assert unexplained.empty, unexplained


def test_ops_tables_filled_by_dbt_hooks(query):
    last = query("select l.run_id from ops.pipeline_run_log l where l.source_system = 'DBT' and l.status = 'SUCCESS' "
                 "and exists (select 1 from ops.recon_results r where r.run_id = l.run_id) "
                 "order by l.started_at desc limit 1")["run_id"][0]
    dq = query(f"select count(*) n from ops.dq_results where run_id = '{last}'")["n"][0]
    recon = query(f"select count(*) n, count(distinct check_name) checks from ops.recon_results where run_id = '{last}'")
    assert dq > 50
    assert recon["checks"][0] == 6 and recon["n"][0] > 1000
