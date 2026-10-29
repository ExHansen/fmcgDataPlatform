"""Simulasi rantai pasok dari sell-out:

secondary: distributor mengirim ke toko 2x seminggu sebanyak sell-out sampai kiriman berikutnya.
primary:   distributor memesan ke principal tiap Senin untuk menjaga stok N minggu (simulasi stok).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def product_prices(sellout: pd.DataFrame, products: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    sc = cfg["supply_chain"]
    retail = sellout.groupby("product_id")["gross_unit_price"].median()
    out = products[["product_id", "pcs_per_case"]].copy()
    out["retail_price"] = out["product_id"].map(retail)
    out["distributor_price"] = (out["retail_price"] * sc["distributor_price_ratio"] / 100).round().clip(lower=1) * 100
    out["principal_price_ea"] = (out["retail_price"] * sc["principal_price_ratio"] / 10).round().clip(lower=1) * 10
    out["principal_price_cs"] = out["principal_price_ea"] * out["pcs_per_case"]
    return out


def build_secondary(sellout: pd.DataFrame, stores: pd.DataFrame, prices: pd.DataFrame, cfg: dict,
                    rng: np.random.Generator) -> pd.DataFrame:
    sd = cfg["supply_chain"]["secondary_qty_noise_sd"]
    start = sellout["sales_date"].min() - pd.Timedelta(days=7)
    end = sellout["sales_date"].max()
    days = pd.date_range(start, end, freq="D")

    parts = []
    for st in stores.itertuples():
        so = sellout[sellout["store_id"] == st.store_id]
        if so.empty:
            continue
        ship_days = days[days.day_of_week.isin(st.delivery_weekdays)].to_numpy()
        idx = np.searchsorted(ship_days, so["sales_date"].to_numpy(), side="right") - 1
        b = so.assign(ship_date=ship_days[idx])
        g = b.groupby(["product_id", "ship_date"], as_index=False)["units"].sum()
        g["store_id"] = st.store_id
        g["distributor_code"] = st.distributor_code
        parts.append(g)
    sec = pd.concat(parts, ignore_index=True)

    noise = rng.normal(0.05, sd, len(sec))
    sec["qty_pcs"] = np.maximum(1, np.ceil(sec["units"] * (1 + noise))).astype(int)
    sec = sec.merge(prices[["product_id", "distributor_price"]], on="product_id")
    disc_pct = rng.choice([0.0, 0.02, 0.05], len(sec), p=[0.7, 0.2, 0.1])
    sec["gross_value"] = sec["qty_pcs"] * sec["distributor_price"]
    sec["discount_value"] = (sec["gross_value"] * disc_pct).round()
    sec["net_value"] = sec["gross_value"] - sec["discount_value"]

    # 1 invoice = 1 distributor x 1 toko x 1 hari kirim
    sec = sec.sort_values(["distributor_code", "ship_date", "store_id", "product_id"]).reset_index(drop=True)
    inv_key = sec[["distributor_code", "ship_date", "store_id"]].drop_duplicates().copy()
    inv_key["inv_seq"] = inv_key.groupby("distributor_code").cumcount() + 1
    sec = sec.merge(inv_key, on=["distributor_code", "ship_date", "store_id"])
    sec["line_no"] = sec.groupby(["distributor_code", "inv_seq"]).cumcount() + 1

    def inv_no(r) -> str:
        d = r.ship_date
        return {
            "DIST_A": f"INV/A/{d:%Y}/{r.inv_seq:06d}",
            "DIST_B": f"B-{d:%y%m%d}-{r.inv_seq:05d}",
            "DIST_C": f"{7_000_000 + r.inv_seq}",
        }[r.distributor_code]

    sec["invoice_no"] = [inv_no(r) for r in sec.itertuples()]
    cols = ["distributor_code", "invoice_no", "line_no", "ship_date", "store_id", "product_id",
            "qty_pcs", "distributor_price", "gross_value", "discount_value", "net_value"]
    return sec[cols]


def build_primary_orders(secondary: pd.DataFrame, prices: pd.DataFrame, cfg: dict,
                         rng: np.random.Generator) -> pd.DataFrame:
    """Satu baris per order line distributor -> principal, termasuk hasil chaos qty."""
    sc = cfg["supply_chain"]
    ch = cfg["chaos"]["sap"]
    cover = sc["distributor_target_cover_weeks"]

    s = secondary.copy()
    s["week"] = s["ship_date"] - pd.to_timedelta(s["ship_date"].dt.day_of_week, unit="D")
    weeks = pd.date_range(s["week"].min() - pd.Timedelta(weeks=1), s["week"].max(), freq="7D")
    demand = (
        s.pivot_table(index=["distributor_code", "product_id"], columns="week", values="qty_pcs", aggfunc="sum")
        .reindex(columns=weeks, fill_value=0).fillna(0)
    )
    keys = demand.index.to_frame(index=False).merge(prices[["product_id", "pcs_per_case"]], on="product_id", how="left")
    ppc = keys["pcs_per_case"].to_numpy()
    D = demand.to_numpy()
    n_series, n_weeks = D.shape

    inv = cover * D[:, 1:5].mean(axis=1)
    rows = []
    for w in range(n_weeks):
        hist = D[:, max(1, w - 4):w] if w > 1 else D[:, 1:5]
        forecast = hist.mean(axis=1)
        need = np.maximum(0.0, (cover + 1) * forecast - inv)
        cases = np.ceil(need / ppc)
        order = cases > 0

        changed = order & (rng.random(n_series) < ch["order_change_rate"])
        change_factor = rng.choice([0.5, 0.8, 1.2, 1.5], n_series)
        final_cases = np.where(changed, np.maximum(1, np.round(cases * change_factor)), cases)
        rejected = order & (rng.random(n_series) < ch["reject_item_rate"])
        partial = order & ~rejected & (rng.random(n_series) < ch["partial_delivery_rate"])
        delivered = np.where(rejected, 0, np.where(partial, np.floor(final_cases * rng.uniform(0.6, 0.95, n_series)), final_cases))
        each_uom = order & (rng.random(n_series) < ch["each_uom_line_rate"])

        inv = inv + delivered * ppc - D[:, w]
        for i in np.flatnonzero(order):
            rows.append((keys.at[i, "distributor_code"], keys.at[i, "product_id"], weeks[w],
                         int(cases[i]), int(final_cases[i]), bool(changed[i]), bool(rejected[i]),
                         int(delivered[i]), bool(each_uom[i])))

    return pd.DataFrame(rows, columns=["distributor_code", "product_id", "order_date", "cases_ordered",
                                       "cases_final", "is_changed", "is_rejected", "cases_delivered", "is_each_uom"])
