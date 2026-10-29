"""Secondary sales truth -> file harian per distributor (3 format berbeda) + chaos.

Chaos: file telat, file hilang, file dikirim ulang (versi pertama salah, versi kedua koreksi),
UoM campur PCS/karton, kode outlet & produk lokal, kolom DIST_C berganti nama di tengah jalan.
"""
from __future__ import annotations

import io
import re
import zipfile

import numpy as np
import pandas as pd

from simulators.settings import OUTBOX_DIR


def _local_product_codes(products: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "product_id": products["product_id"],
        "DIST_A": [f"SD-{50000 + i:05d}" for i in range(len(products))],   # kode internal distributor A
        "DIST_B": products["matnr"].str.lstrip("0"),                       # MATNR tanpa leading zero
        "DIST_C": products["ean"],                                          # barcode
    })


def _fmt_id_number(x: float) -> str:
    """Format angka Indonesia: titik ribuan, koma desimal."""
    s = f"{x:,.2f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _render_a(df: pd.DataFrame) -> bytes:
    out = pd.DataFrame({
        "No_Faktur": df["invoice_no"],
        "Tgl_Faktur": df["ship_date"].dt.strftime("%d/%m/%Y"),
        "Kode_Outlet": df["outlet_code"],
        "Nama_Outlet": df["outlet_name"],
        "Kode_Barang": df["local_product_code"],
        "Nama_Barang": df["product_name"],
        "Qty": df["qty"].map(lambda v: f"{v:g}".replace(".", ",")),
        "Satuan": df["uom"].map({"PCS": "PCS", "CASE": "KRT"}),
        "Harga": df["unit_price"].map(_fmt_id_number),
        "Diskon": df["discount_value"].map(_fmt_id_number),
        "Nilai_Netto": df["net_value"].map(_fmt_id_number),
    })
    return out.to_csv(sep=";", index=False, lineterminator="\r\n").encode("cp1252", errors="replace")


def _render_b(df: pd.DataFrame) -> bytes:
    out = pd.DataFrame({
        "InvoiceNo": df["invoice_no"],
        "InvoiceDate": df["ship_date"].dt.date,
        "OutletCode": df["outlet_code"],
        "OutletName": df["outlet_name"],
        "SKU": df["local_product_code"],
        "Description": df["product_name"],
        "Qty": df["qty"],
        "UOM": df["uom"].map({"PCS": "PCS", "CASE": "CTN"}),
        "GrossAmount": df["gross_value"],
        "DiscountAmount": df["discount_value"],
        "NetAmount": df["net_value"],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="Penjualan", index=False)
    stamp = f"{df['ship_date'].iloc[0]:%Y-%m-%d}T20:00:00Z"
    return _make_deterministic(buf.getvalue(), stamp)


def _make_deterministic(xlsx: bytes, stamp: str) -> bytes:
    """openpyxl menulis jam saat ini ke docProps (created/modified) dan ke tiap entri zip.
    Ganti dengan nilai tetap agar file untuk data yang sama selalu identik byte-per-byte."""
    src = zipfile.ZipFile(io.BytesIO(xlsx))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "docProps/core.xml":
                data = re.sub(rb'(<dcterms:(created|modified) xsi:type="dcterms:W3CDTF">)[^<]*',
                              rb"\g<1>" + stamp.encode(), data)
            dst.writestr(zipfile.ZipInfo(item.filename, date_time=(1980, 1, 1, 0, 0, 0)), data,
                         compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()


def _render_c(df: pd.DataFrame, renamed: bool) -> bytes:
    out = pd.DataFrame({
        "INV_NO": df["invoice_no"],
        "INV_DATE": df["ship_date"].dt.strftime("%Y%m%d"),
        "OUTLET_ID" if renamed else "CUST_ID": df["outlet_code"],
        "OUTLET_NAME" if renamed else "CUST_NAME": df["outlet_name"],
        "ITEM_CODE": df["local_product_code"],
        "QUANTITY" if renamed else "QTY_PCS": df["qty"].astype(int),
        "GROSS": df["gross_value"].map(lambda v: f"{v:.0f}"),
        "DISC": df["discount_value"].map(lambda v: f"{v:.0f}"),
        "NET": df["net_value"].map(lambda v: f"{v:.0f}"),
    })
    return out.to_csv(sep="|", index=False, lineterminator="\n").encode("utf-8")


EXT = {"csv_semicolon": "csv", "xlsx": "xlsx", "pipe_txt": "txt"}


def render_dms_files(secondary: pd.DataFrame, products: pd.DataFrame, stores: pd.DataFrame,
                     distributors: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    ch = cfg["chaos"]["dms"]
    rename_from = pd.Timestamp(ch["dist_c_column_rename_from"])
    codes = _local_product_codes(products)
    s = (secondary
         .merge(products[["product_id", "product_name", "pcs_per_case"]], on="product_id")
         .merge(stores[["store_id", "distributor_outlet_code", "store_name"]], on="store_id")
         .rename(columns={"distributor_outlet_code": "outlet_code", "store_name": "outlet_name"}))
    s["product_name"] = s["product_name"].str.upper()

    out_dir = OUTBOX_DIR / "dms"
    index = []
    for dist in distributors.itertuples():
        ds = s[s["distributor_code"] == dist.distributor_code].copy()
        ds["local_product_code"] = ds["product_id"].map(codes.set_index("product_id")[dist.distributor_code])
        # UoM: distributor A & B kadang melaporkan dalam karton bila qty pas kelipatan isi karton
        as_case = (dist.distributor_code != "DIST_C") & (ds["qty_pcs"] % ds["pcs_per_case"] == 0) \
            & (rng.random(len(ds)) < ch["carton_uom_rate"])
        ds["uom"] = np.where(as_case, "CASE", "PCS")
        ds["qty"] = np.where(as_case, ds["qty_pcs"] // ds["pcs_per_case"], ds["qty_pcs"]).astype(float)
        ds["unit_price"] = np.where(as_case, ds["distributor_price"] * ds["pcs_per_case"], ds["distributor_price"])

        ext = EXT[dist.file_format]
        for bdate, day in ds.groupby("ship_date"):
            if rng.random() < ch["missing_day_prob"]:
                continue
            day = day.sort_values(["invoice_no", "line_no"])
            arrival = bdate + pd.Timedelta(days=1, hours=int(rng.integers(6, 10)), minutes=int(rng.integers(60)))
            if rng.random() < ch["late_file_prob"]:
                arrival += pd.Timedelta(days=int(rng.integers(1, 4)))
            name = f"secondary_{bdate:%Y%m%d}.{ext}"
            versions = [(day, name, arrival)]
            if rng.random() < ch["resend_prob"]:
                # Versi pertama salah (baris hilang / qty salah), versi kedua = koreksi yang benar
                wrong = day.sample(frac=0.95, random_state=int(rng.integers(1 << 31))).sort_index().copy()
                bump = rng.random(len(wrong)) < 0.05
                wrong.loc[bump, "qty"] = wrong.loc[bump, "qty"] + 1
                resend_name = name if dist.distributor_code != "DIST_B" else f"secondary_{bdate:%Y%m%d}_rev1.{ext}"
                versions = [(wrong, name, arrival),
                            (day, resend_name, arrival + pd.Timedelta(days=int(rng.integers(1, 3)), hours=2))]

            for v, (content, remote_name, arr) in enumerate(versions, start=1):
                if dist.file_format == "csv_semicolon":
                    data = _render_a(content)
                elif dist.file_format == "xlsx":
                    data = _render_b(content)
                else:
                    data = _render_c(content, renamed=bdate >= rename_from)
                local = out_dir / dist.distributor_code / f"{remote_name}.v{v}"
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(data)
                index.append({"distributor_code": dist.distributor_code, "remote_name": remote_name,
                              "version": v, "business_date": bdate, "arrival_ts": arr,
                              "local_path": str(local), "n_rows": len(content)})
    return pd.DataFrame(index)
