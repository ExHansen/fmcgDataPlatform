from datetime import date

import pandas as pd

from simulators.publish import rows_to_publish

PK = ["vbeln"]


def _versions():
    return pd.DataFrame({
        "vbeln": ["A", "A", "B", "C"],
        "kwmeng": [10, 8, 5, 7],
        "_event_date": pd.to_datetime(["2026-01-01", "2026-01-03", "2026-01-02", "2026-01-10"]),
    })


def test_first_publish_takes_latest_visible_version():
    out = rows_to_publish(_versions(), PK, None, date(2026, 1, 5)).set_index("vbeln")
    assert out.loc["A", "kwmeng"] == 8          # versi perubahan sudah terlihat
    assert "C" not in out.index                 # event masa depan belum terkirim
    assert "_event_date" not in out.columns


def test_incremental_publish_only_sends_touched_keys():
    out = rows_to_publish(_versions(), PK, date(2026, 1, 2), date(2026, 1, 5))
    assert out["vbeln"].tolist() == ["A"]       # B tidak berubah setelah 01-02
    assert out["kwmeng"].tolist() == [8]


def test_update_before_until_is_hidden():
    out = rows_to_publish(_versions(), PK, None, date(2026, 1, 2)).set_index("vbeln")
    assert out.loc["A", "kwmeng"] == 10
