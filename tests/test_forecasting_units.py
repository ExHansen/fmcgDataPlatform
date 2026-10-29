import math

import pandas as pd
import pytest

from forecasting import features, metrics


def test_wape_and_bias():
    actual = pd.Series([10.0, 0.0, 5.0])
    pred = pd.Series([12.0, 1.0, 2.0])
    assert metrics.wape(actual, pred) == pytest.approx((2 + 1 + 3) / 15)
    assert metrics.bias(actual, pred) == pytest.approx((15 - 15) / 15)
    assert math.isnan(metrics.wape(pd.Series([0.0]), pd.Series([1.0])))


def test_panel_starts_at_first_sale_and_fills_zero_weeks():
    weekly = pd.DataFrame({
        "week_start_date": pd.to_datetime(["2026-01-05", "2026-01-19", "2026-01-12", "2026-01-26"]),
        "sku_id": ["A", "A", "B", "B"], "region": ["R1"] * 4, "category": ["C"] * 4, "brand": ["X"] * 4,
        "units": [3.0, 4.0, 5.0, 6.0],
    })
    panel, attrs = features.to_panel(weekly)
    a = panel[panel["unique_id"] == "A|R1"]
    b = panel[panel["unique_id"] == "B|R1"]
    assert a["y"].tolist() == [3.0, 0.0, 4.0, 0.0]          # minggu kosong = 0, sampai minggu terakhir data
    assert b["ds"].min() == pd.Timestamp("2026-01-12")     # seri B mulai saat listing, bukan dari awal data
    assert set(attrs["unique_id"]) == {"A|R1", "B|R1"}


def test_score_aggregates_before_computing_category_wape():
    cv = pd.DataFrame({
        "unique_id": ["A|R1", "B|R1"], "ds": pd.to_datetime(["2026-02-02"] * 2),
        "cutoff": pd.to_datetime(["2026-01-26"] * 2), "y": [10.0, 0.0], "M": [0.0, 10.0],
    })
    attrs = pd.DataFrame({"unique_id": ["A|R1", "B|R1"], "category": ["C", "C"], "region": ["R1", "R1"]})
    s = metrics.score(cv, ["M"], attrs).set_index(["level", "category"])
    assert s.loc[("sku_region", None), "wape"] == pytest.approx(2.0)      # error per seri tidak saling menutup
    assert s.loc[("category_region", None), "wape"] == pytest.approx(0.0)  # di level kategori saling menutup
