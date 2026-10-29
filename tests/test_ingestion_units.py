import pandas as pd
import pytest

from ingestion.common.files import ContractError, check_contract, parse
from ingestion.common.hashing import row_hashes
from ingestion.common.retry import retry
from ingestion.common.settings import contracts


def test_contract_accepts_known_alias_and_reports_unknown_columns():
    c = contracts()["dms"]["DIST_C"]
    df = pd.DataFrame(columns=["INV_NO", "INV_DATE", "OUTLET_ID", "ITEM_CODE", "QUANTITY", "NET", "PROMO_FLAG"])
    assert check_contract(df, c) == ["PROMO_FLAG"]


def test_contract_rejects_missing_required_column():
    c = contracts()["dms"]["DIST_A"]
    df = pd.DataFrame(columns=["No_Faktur", "Tgl_Faktur", "Kode_Outlet", "Kode_Barang", "Satuan", "Nilai_Netto"])
    with pytest.raises(ContractError, match="qty"):
        check_contract(df, c)


def test_parse_keeps_everything_as_text():
    data = "No_Faktur;Qty;Nilai_Netto\r\nINV/A/1;12;1.234,50\r\n".encode("cp1252")
    df = parse(data, "csv_semicolon")
    assert df.loc[0, "Nilai_Netto"] == "1.234,50"     # desimal koma tidak diubah di layer raw
    ean = parse(b"EAN,QTY\n0012345678905,1\n", "csv")
    assert ean.loc[0, "EAN"] == "0012345678905"       # leading zero aman


def test_row_hash_distinguishes_null_from_empty_string():
    df = pd.DataFrame({"a": ["x", "x"], "b": [None, ""]})
    h = row_hashes(df, ["a", "b"])
    assert h[0] != h[1]


def test_retry_backs_off_then_succeeds():
    calls, sleeps = [], []

    @retry((ConnectionError,), attempts=3, base_delay=1, sleep=sleeps.append)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("putus")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3 and len(sleeps) == 2
    assert all(0 <= s <= 2 for s in sleeps)


def test_retry_gives_up_after_max_attempts():
    @retry((ConnectionError,), attempts=2, sleep=lambda _: None)
    def always_fails():
        raise ConnectionError("mati")

    with pytest.raises(ConnectionError):
        always_fails()
