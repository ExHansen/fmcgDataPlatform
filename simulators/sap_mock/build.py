"""Truth rantai pasok -> tabel SAP SD berversi.

Setiap tabel adalah DataFrame berisi kolom SAP + `_event_date`: tanggal versi baris
itu muncul/berubah di SAP. Publisher menerapkan versi terbaru yang `_event_date <= until`,
sehingga perubahan (AEDAT, FKSTO, WADAT_IST) muncul belakangan seperti di sistem asli.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from simulators.common.ids import sap_alpha, sap_posnr

EMPTY_DATE = "00000000"

PRIMARY_KEYS = {
    "kna1": ["mandt", "kunnr"],
    "knvv": ["mandt", "kunnr", "vkorg", "vtweg", "spart"],
    "mara": ["mandt", "matnr"],
    "makt": ["mandt", "matnr", "spras"],
    "marm": ["mandt", "matnr", "meinh"],
    "t023t": ["mandt", "spras", "matkl"],
    "t179t": ["mandt", "spras", "prodh"],
    "vbak": ["mandt", "vbeln"],
    "vbap": ["mandt", "vbeln", "posnr"],
    "vbep": ["mandt", "vbeln", "posnr", "etenr"],
    "likp": ["mandt", "vbeln"],
    "lips": ["mandt", "vbeln", "posnr"],
    "vbrk": ["mandt", "vbeln"],
    "vbrp": ["mandt", "vbeln", "posnr"],
    "vbfa": ["mandt", "vbelv", "posnv", "vbeln", "posnn"],
}


def dats(ts: pd.Series | pd.Timestamp) -> pd.Series | str:
    if isinstance(ts, pd.Series):
        return ts.dt.strftime("%Y%m%d")
    return ts.strftime("%Y%m%d")


def _times(rng: np.random.Generator, n: int, start_h: int = 8, end_h: int = 17) -> list[str]:
    secs = rng.integers(start_h * 3600, end_h * 3600, n)
    return [f"{s // 3600:02d}{s % 3600 // 60:02d}{s % 60:02d}" for s in secs]


def build_masters(products: pd.DataFrame, distributors: pd.DataFrame, cfg: dict, data_start: pd.Timestamp,
                  rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    co = cfg["company"]
    mandt = co["sap_client"]
    cust_created = data_start - pd.Timedelta(days=365)

    kna1 = pd.DataFrame({
        "mandt": mandt,
        "kunnr": distributors["kunnr"],
        "name1": distributors["name"].str.upper().str.slice(0, 35),
        "land1": "ID",
        "regio": distributors["region"].map({"JABODETABEK": "31", "JAWA BARAT": "32", "JAWA TIMUR": "35"}),
        "ort01": distributors["cities"].map(lambda c: c[0].upper()),
        "stras": [f"JL. INDUSTRI RAYA NO. {10 + i}" for i in range(len(distributors))],
        "ktokd": "ZDIS",
        "erdat": dats(cust_created),
        "_event_date": cust_created,
    })
    knvv = kna1[["mandt", "kunnr", "erdat", "_event_date"]].assign(
        vkorg=co["sales_org"], vtweg=co["distribution_channel"], spart=co["division"], kdgrp="01")

    mara = pd.DataFrame({
        "mandt": mandt,
        "matnr": products["matnr"],
        "mtart": "FERT",
        "matkl": products["matkl"],
        "prdha": products["prdha"],
        "meins": "EA",
        "ean11": products["ean"],
        "brgew": np.round(rng.uniform(0.05, 2.5, len(products)), 3),
        "gewei": "KG",
        "ersda": dats(products["created_date"]),
        "laeda": dats(products["created_date"]),
        "lvorm": "",
        "_event_date": products["created_date"],
    })
    # Chaos: sebagian material dipindah material group di tengah tahun -> bahan SCD Type 2
    n_reclass = cfg["chaos"]["sap"]["material_reclass_count"]
    groups = mara["matkl"].unique()
    idx = rng.choice(len(mara), n_reclass, replace=False)
    reclass = mara.iloc[idx].copy()
    change_dates = data_start + pd.to_timedelta(rng.integers(120, 250, n_reclass), unit="D")
    reclass["matkl"] = [rng.choice([g for g in groups if g != old]) for old in reclass["matkl"]]
    reclass["laeda"] = dats(pd.Series(change_dates, index=reclass.index))
    reclass["_event_date"] = change_dates
    mara = pd.concat([mara, reclass], ignore_index=True)

    makt = pd.DataFrame({"mandt": mandt, "matnr": products["matnr"], "spras": "E",
                         "maktx": products["product_name"].str.upper(), "_event_date": products["created_date"]})
    marm = pd.concat([
        pd.DataFrame({"mandt": mandt, "matnr": products["matnr"], "meinh": "EA", "umrez": 1, "umren": 1,
                      "ean11": products["ean"], "_event_date": products["created_date"]}),
        pd.DataFrame({"mandt": mandt, "matnr": products["matnr"], "meinh": "CS", "umrez": products["pcs_per_case"],
                      "umren": 1, "ean11": "", "_event_date": products["created_date"]}),
    ], ignore_index=True)

    first = products["created_date"].min()
    cats = products[["matkl", "category"]].drop_duplicates("matkl")
    t023t = pd.DataFrame({"mandt": mandt, "spras": "E", "matkl": cats["matkl"],
                          "wgbez": cats["category"].str.slice(0, 20), "wgbez60": cats["category"].str.slice(0, 60),
                          "_event_date": first})
    brands = products[["prdha", "brand"]].drop_duplicates("prdha")
    t179t = pd.DataFrame({"mandt": mandt, "spras": "E", "prodh": brands["prdha"], "vtext": brands["brand"],
                          "_event_date": first})
    return {"kna1": kna1, "knvv": knvv, "mara": mara, "makt": makt, "marm": marm, "t023t": t023t, "t179t": t179t}


def build_transactions(orders: pd.DataFrame, products: pd.DataFrame, distributors: pd.DataFrame,
                       prices: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    co = cfg["company"]
    mandt = co["sap_client"]
    lead = pd.Timedelta(days=cfg["supply_chain"]["goods_issue_lead_days"])
    one = pd.Timedelta(days=1)

    o = (orders.merge(products[["product_id", "matnr", "product_name", "pcs_per_case"]], on="product_id")
         .merge(prices[["product_id", "principal_price_ea"]], on="product_id")
         .merge(distributors[["distributor_code", "kunnr"]], on="distributor_code")
         .sort_values(["order_date", "distributor_code", "matnr"]).reset_index(drop=True))

    hdr = o[["order_date", "distributor_code", "kunnr"]].drop_duplicates().reset_index(drop=True)
    hdr["vbeln"] = [sap_alpha(100001 + i, 10) for i in range(len(hdr))]
    hdr["erzet"] = _times(rng, len(hdr))
    o = o.merge(hdr[["order_date", "distributor_code", "vbeln"]], on=["order_date", "distributor_code"])
    o["posnr"] = [sap_posnr(i) for i in o.groupby("vbeln").cumcount()]

    # Satuan jual: CS (karton), sebagian baris dipesan dalam EA
    o["vrkme"] = np.where(o["is_each_uom"], "EA", "CS")
    o["umvkz"] = np.where(o["is_each_uom"], 1, o["pcs_per_case"])
    o["price_su"] = o["principal_price_ea"] * o["umvkz"]
    to_su = np.where(o["is_each_uom"], o["pcs_per_case"], 1)
    o["qty_orig"] = o["cases_ordered"] * to_su
    o["qty_final"] = o["cases_final"] * to_su
    o["qty_deliv"] = o["cases_delivered"] * to_su
    o["arktx"] = o["product_name"].str.upper()
    o["erdat"] = dats(o["order_date"])

    item_base = {
        "mandt": mandt, "vbeln": o["vbeln"], "posnr": o["posnr"], "matnr": o["matnr"], "arktx": o["arktx"],
        "vrkme": o["vrkme"], "meins": "EA", "umvkz": o["umvkz"], "umvkn": 1, "waerk": "IDR",
        "werks": co["plant"], "erdat": o["erdat"],
    }
    vbap_v1 = pd.DataFrame({**item_base, "kwmeng": o["qty_orig"], "netwr": o["qty_orig"] * o["price_su"],
                            "abgru": "", "aedat": EMPTY_DATE, "_event_date": o["order_date"]})
    amended = o["is_changed"] | o["is_rejected"]
    oa = o[amended]
    vbap_v2 = pd.DataFrame({k: (v[amended] if isinstance(v, pd.Series) else v) for k, v in item_base.items()})
    vbap_v2 = vbap_v2.assign(
        kwmeng=oa["qty_final"], netwr=oa["qty_final"] * oa["price_su"],
        abgru=np.where(oa["is_rejected"], "Z1", ""), aedat=dats(oa["order_date"] + one),
        _event_date=oa["order_date"] + one)
    vbap = pd.concat([vbap_v1, vbap_v2], ignore_index=True)

    vbep = pd.concat([
        pd.DataFrame({"mandt": mandt, "vbeln": o["vbeln"], "posnr": o["posnr"], "etenr": "0001",
                      "edatu": dats(o["order_date"] + lead + one), "wmeng": o["qty_orig"], "bmeng": o["qty_orig"],
                      "_event_date": o["order_date"]}),
        pd.DataFrame({"mandt": mandt, "vbeln": oa["vbeln"], "posnr": oa["posnr"], "etenr": "0001",
                      "edatu": dats(oa["order_date"] + lead + one), "wmeng": oa["qty_final"],
                      "bmeng": np.where(oa["is_rejected"], 0, oa["qty_final"]), "_event_date": oa["order_date"] + one}),
    ], ignore_index=True)

    net_v1 = (o["qty_orig"] * o["price_su"]).groupby(o["vbeln"]).sum()
    net_v2 = (np.where(o["is_rejected"], 0, o["qty_final"]) * o["price_su"]).groupby(o["vbeln"]).sum()
    hdr_changed = o.loc[amended, "vbeln"].unique()
    vbak_base = pd.DataFrame({
        "mandt": mandt, "vbeln": hdr["vbeln"], "auart": "ZOR", "audat": dats(hdr["order_date"]),
        "erdat": dats(hdr["order_date"]), "erzet": hdr["erzet"], "vkorg": co["sales_org"],
        "vtweg": co["distribution_channel"], "spart": co["division"], "kunnr": hdr["kunnr"],
        "bstnk": "PO-" + hdr["distributor_code"] + "-" + hdr["order_date"].dt.strftime("%y%m%d"), "waerk": "IDR",
    })
    vbak_v1 = vbak_base.assign(aedat=EMPTY_DATE, netwr=vbak_base["vbeln"].map(net_v1), _event_date=hdr["order_date"])
    ch = vbak_base["vbeln"].isin(hdr_changed)
    vbak_v2 = vbak_base[ch].assign(aedat=dats(hdr.loc[ch, "order_date"] + one),
                                   netwr=vbak_base.loc[ch, "vbeln"].map(net_v2),
                                   _event_date=hdr.loc[ch, "order_date"] + one)
    vbak = pd.concat([vbak_v1, vbak_v2], ignore_index=True)

    # ---------- Delivery: dibuat H+1, goods issue di hari H+lead ----------
    d = o[o["qty_deliv"] > 0].copy()
    dhdr = d[["vbeln", "order_date", "kunnr"]].drop_duplicates("vbeln").rename(columns={"vbeln": "so_vbeln"}).reset_index(drop=True)
    dhdr["dlv_vbeln"] = [sap_alpha(80000001 + i, 10) for i in range(len(dhdr))]
    dhdr["created"] = dhdr["order_date"] + one
    dhdr["gi_date"] = dhdr["order_date"] + lead
    likp_base = pd.DataFrame({
        "mandt": mandt, "vbeln": dhdr["dlv_vbeln"], "lfart": "LF", "erdat": dats(dhdr["created"]),
        "erzet": _times(rng, len(dhdr)), "vstel": co["shipping_point"], "kunnr": dhdr["kunnr"],
        "lfdat": dats(dhdr["gi_date"] + one), "wadat": dats(dhdr["gi_date"]),
    })
    likp = pd.concat([
        likp_base.assign(aedat=EMPTY_DATE, wadat_ist=EMPTY_DATE, _event_date=dhdr["created"]),
        likp_base.assign(aedat=dats(dhdr["gi_date"]), wadat_ist=dats(dhdr["gi_date"]), _event_date=dhdr["gi_date"]),
    ], ignore_index=True)

    d = d.merge(dhdr[["so_vbeln", "dlv_vbeln", "created", "gi_date"]], left_on="vbeln", right_on="so_vbeln")
    d["dlv_posnr"] = [sap_posnr(i) for i in d.groupby("dlv_vbeln").cumcount()]
    lips = pd.DataFrame({
        "mandt": mandt, "vbeln": d["dlv_vbeln"], "posnr": d["dlv_posnr"], "matnr": d["matnr"],
        "lfimg": d["qty_deliv"], "vrkme": d["vrkme"], "meins": "EA", "umvkz": d["umvkz"], "umvkn": 1,
        "werks": co["plant"], "vgbel": d["vbeln"], "vgpos": d["posnr"], "erdat": dats(d["created"]),
        "_event_date": d["created"],
    })

    # ---------- Billing: invoice F2 saat goods issue; sebagian dibatalkan & ditagih ulang ----------
    bhdr = dhdr[["dlv_vbeln", "gi_date", "kunnr"]].copy().reset_index(drop=True)
    seq = iter(range(90000001, 99999999))
    bhdr["inv_vbeln"] = [sap_alpha(next(seq), 10) for _ in range(len(bhdr))]
    cancel = rng.random(len(bhdr)) < cfg["chaos"]["sap"]["cancel_invoice_rate"]
    bhdr["cancel_date"] = pd.NaT
    bhdr.loc[cancel, "cancel_date"] = bhdr.loc[cancel, "gi_date"] + pd.to_timedelta(rng.integers(2, 6, cancel.sum()), unit="D")

    d = d.merge(bhdr[["dlv_vbeln", "inv_vbeln"]], on="dlv_vbeln")
    d["line_net"] = d["qty_deliv"] * d["price_su"]

    def billing_docs(lines: pd.DataFrame, heads: pd.DataFrame, vbeln_col: str, fkart: str, doc_date_col: str,
                     sfakn_col: str | None, price_factor: float = 1.0):
        net = (lines["line_net"] * price_factor).round(2)
        items = pd.DataFrame({
            "mandt": mandt, "vbeln": lines[vbeln_col], "posnr": lines["dlv_posnr"], "matnr": lines["matnr"],
            "arktx": lines["arktx"], "fkimg": lines["qty_deliv"], "vrkme": lines["vrkme"], "meins": "EA",
            "umvkz": lines["umvkz"], "umvkn": 1, "netwr": net, "aubel": lines["vbeln"], "aupos": lines["posnr"],
            "vgbel": lines["dlv_vbeln"], "vgpos": lines["dlv_posnr"], "werks": co["plant"],
            "erdat": dats(lines[doc_date_col]), "_event_date": lines[doc_date_col],
        })
        totals = items.groupby("vbeln")["netwr"].sum()
        head = pd.DataFrame({
            "mandt": mandt, "vbeln": heads[vbeln_col], "fkart": fkart, "fkdat": dats(heads[doc_date_col]),
            "erdat": dats(heads[doc_date_col]), "erzet": _times(rng, len(heads), 17, 20), "aedat": EMPTY_DATE,
            "vkorg": co["sales_org"], "vtweg": co["distribution_channel"], "kunag": heads["kunnr"],
            "kunrg": heads["kunnr"], "netwr": heads[vbeln_col].map(totals).fillna(0), "waerk": "IDR",
            "fksto": "", "sfakn": heads[sfakn_col] if sfakn_col else "", "_event_date": heads[doc_date_col],
        })
        return head, items

    vbrk_f2, vbrp_f2 = billing_docs(d.assign(doc_date=d["gi_date"]), bhdr.assign(doc_date=bhdr["gi_date"]),
                                    "inv_vbeln", "F2", "doc_date", None)
    ch_heads = bhdr[cancel].copy()
    ch_heads["s1_vbeln"] = [sap_alpha(next(seq), 10) for _ in range(len(ch_heads))]
    ch_heads["rebill_vbeln"] = [sap_alpha(next(seq), 10) for _ in range(len(ch_heads))]
    ch_lines = d.merge(ch_heads[["dlv_vbeln", "cancel_date", "s1_vbeln", "rebill_vbeln"]], on="dlv_vbeln")
    vbrk_s1, vbrp_s1 = billing_docs(ch_lines, ch_heads, "s1_vbeln", "S1", "cancel_date", "inv_vbeln")
    # Rebill dengan koreksi harga (alasan umum pembatalan: harga/diskon salah)
    vbrk_rb, vbrp_rb = billing_docs(ch_lines, ch_heads, "rebill_vbeln", "F2", "cancel_date", None, price_factor=0.97)
    cancelled_orig = (vbrk_f2.drop(columns="_event_date")
                      .merge(ch_heads[["inv_vbeln", "cancel_date"]], left_on="vbeln", right_on="inv_vbeln")
                      .drop(columns="inv_vbeln").rename(columns={"cancel_date": "_event_date"}))
    cancelled_orig["fksto"] = "X"
    cancelled_orig["aedat"] = dats(cancelled_orig["_event_date"])
    vbrk = pd.concat([vbrk_f2, cancelled_orig, vbrk_s1, vbrk_rb], ignore_index=True)
    vbrp = pd.concat([vbrp_f2, vbrp_s1, vbrp_rb], ignore_index=True)

    # ---------- Document flow ----------
    def flow(vbelv, posnv, vbeln, posnn, typ, qty, when):
        return pd.DataFrame({"mandt": mandt, "vbelv": vbelv, "posnv": posnv, "vbeln": vbeln, "posnn": posnn,
                             "vbtyp_n": typ, "rfmng": qty, "erdat": dats(when), "_event_date": when})

    vbfa = pd.concat([
        flow(d["vbeln"], d["posnr"], d["dlv_vbeln"], d["dlv_posnr"], "J", d["qty_deliv"], d["created"]),
        flow(d["dlv_vbeln"], d["dlv_posnr"], d["inv_vbeln"], d["dlv_posnr"], "M", d["qty_deliv"], d["gi_date"]),
        flow(ch_lines["inv_vbeln"], ch_lines["dlv_posnr"], ch_lines["s1_vbeln"], ch_lines["dlv_posnr"], "N",
             ch_lines["qty_deliv"], ch_lines["cancel_date"]),
        flow(ch_lines["dlv_vbeln"], ch_lines["dlv_posnr"], ch_lines["rebill_vbeln"], ch_lines["dlv_posnr"], "M",
             ch_lines["qty_deliv"], ch_lines["cancel_date"]),
    ], ignore_index=True)

    return {"vbak": vbak, "vbap": vbap, "vbep": vbep, "likp": likp, "lips": lips,
            "vbrk": vbrk, "vbrp": vbrp, "vbfa": vbfa}
