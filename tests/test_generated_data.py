"""Invariant pada data hasil `python -m simulators generate` (di-skip jika belum di-generate)."""
from pathlib import Path

import pandas as pd
import pytest

from simulators.common.ids import is_valid_ean13
from simulators.sap_mock.build import PRIMARY_KEYS
from simulators.settings import TRUTH_DIR

pytestmark = pytest.mark.skipif(not (TRUTH_DIR / "dms_index.parquet").exists(),
                                reason="jalankan `python -m simulators generate` dulu")


def truth(name: str) -> pd.DataFrame:
    return pd.read_parquet(TRUTH_DIR / f"{name}.parquet")


def sap(table: str) -> pd.DataFrame:
    return pd.read_parquet(TRUTH_DIR / "sap" / f"{table}.parquet")


def latest(table: str) -> pd.DataFrame:
    df = sap(table)
    return df.sort_values("_event_date", kind="stable").drop_duplicates(PRIMARY_KEYS[table], keep="last")


def test_master_ids_unique_and_valid():
    p = truth("products")
    assert p["sku_id"].is_unique and p["matnr"].is_unique and p["ean"].is_unique
    assert p["ean"].map(is_valid_ean13).all()
    assert (p["matnr"].str.len() == 18).all()


def test_sap_versions_never_share_event_date_per_key():
    for table, pk in PRIMARY_KEYS.items():
        df = sap(table)
        assert not df.duplicated(pk + ["_event_date"]).any(), table


def test_delivery_and_billing_reference_existing_documents():
    vbap, lips, vbrp = latest("vbap"), latest("lips"), latest("vbrp")
    so_items = set(zip(vbap["vbeln"], vbap["posnr"]))
    assert set(zip(lips["vgbel"], lips["vgpos"])) <= so_items
    assert set(zip(vbrp["vgbel"], vbrp["vgpos"])) <= set(zip(lips["vbeln"], lips["posnr"]))
    # Item yang direject tidak pernah dikirim
    rejected = set(zip(*vbap.loc[vbap["abgru"] != "", ["vbeln", "posnr"]].T.values))
    assert not rejected & set(zip(lips["vgbel"], lips["vgpos"]))


def test_delivered_never_exceeds_ordered():
    vbap, lips = latest("vbap"), latest("lips")
    m = lips.merge(vbap, left_on=["vgbel", "vgpos"], right_on=["vbeln", "posnr"], suffixes=("_d", "_o"))
    assert (m["lfimg"] <= m["kwmeng"]).all()


def test_cancelled_invoices_have_cancellation_and_rebill():
    vbrk = latest("vbrk")
    cancelled = set(vbrk.loc[vbrk["fksto"] == "X", "vbeln"])
    assert cancelled, "chaos pembatalan invoice tidak terjadi"
    assert cancelled == set(vbrk.loc[vbrk["fkart"] == "S1", "sfakn"])


def _parse_dist_a(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", dtype=str, encoding="cp1252")
    num = lambda s: s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
    return pd.DataFrame({"invoice_no": df["No_Faktur"], "net_value": num(df["Nilai_Netto"])})


def test_final_dms_files_reconcile_to_truth():
    """Versi terakhir tiap file distributor = kebenaran secondary (kecuali hari yang hilang)."""
    idx = truth("dms_index")
    sec = truth("secondary")
    last = idx.sort_values("version").drop_duplicates(["distributor_code", "business_date"], keep="last")
    a = last[last["distributor_code"] == "DIST_A"].head(30)
    parsed = pd.concat([_parse_dist_a(Path(p)) for p in a["local_path"]])
    expected = sec[(sec["distributor_code"] == "DIST_A") & sec["ship_date"].isin(a["business_date"])]
    assert parsed["net_value"].sum() == pytest.approx(expected["net_value"].sum())

    c = last[last["distributor_code"] == "DIST_C"].iloc[-1]
    df = pd.read_csv(c["local_path"], sep="|", dtype=str)
    assert "QUANTITY" in df.columns and "QTY_PCS" not in df.columns   # schema drift setelah tanggal rename


def test_pos_files_contain_chaos_but_totals_close_to_truth():
    idx = truth("pos_index")
    f = pd.concat([pd.read_csv(p, dtype={"EAN": str}) for p in idx["local_path"]])
    assert (f["QTY"] < 0).any(), "baris retur"
    assert (~f["EAN"].map(is_valid_ean13)).any(), "EAN kehilangan leading zero"
    assert f.duplicated().any(), "baris dobel"
    so = truth("sellout")
    assert f.loc[f["QTY"] > 0, "QTY"].sum() == pytest.approx(so["units"].sum(), rel=0.03)
