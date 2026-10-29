import io
import time

import pandas as pd

from simulators.dms_sftp.render import _render_b


def test_xlsx_render_is_byte_identical_across_runs():
    df = pd.DataFrame({
        "invoice_no": ["B-1"], "ship_date": pd.to_datetime(["2026-03-04"]), "outlet_code": ["CUST-0001"],
        "outlet_name": ["TOKO"], "local_product_code": ["100001"], "product_name": ["X"], "qty": [2.0],
        "uom": ["PCS"], "gross_value": [100.0], "discount_value": [0.0], "net_value": [100.0],
    })
    first = _render_b(df)
    time.sleep(2.1)   # timestamp zip beresolusi 2 detik; pastikan jam berbeda tidak bocor ke output
    assert _render_b(df) == first
    assert pd.read_excel(io.BytesIO(first)).loc[0, "InvoiceNo"] == "B-1"
