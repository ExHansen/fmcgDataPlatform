"""Integrasi dengan docker compose: publish bertahap harus = publish sekali jalan.

Jalankan: RUN_INTEGRATION=1 pytest tests/test_integration_publish.py
Tes ini mengosongkan sistem sumber (reset) lalu mengembalikan state ke tanggal semula.
"""
import os
from datetime import date

import pytest

from simulators import publish as pub
from simulators.sap_mock.build import PRIMARY_KEYS

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="butuh docker compose up")


def snapshot() -> dict:
    out = {}
    with pub.sap_connect() as conn:
        for t, pk in PRIMARY_KEYS.items():
            out[t] = conn.execute(
                f"select count(*), md5(coalesce(string_agg(t::text, '|' order by {', '.join(pk)}), '')) from sap.{t} t"
            ).fetchone()
    for dist in pub.DIST_USERS:
        client, sftp = pub.sftp_connect(dist)
        out[dist] = sorted((a.filename, a.st_size, int(a.st_mtime)) for a in sftp.listdir_attr("upload"))
        sftp.close()
        client.close()
    s3 = pub.s3_client()
    objs = [o for p in s3.get_paginator("list_objects_v2").paginate(Bucket=pub.env("S3_RETAILER_BUCKET"))
            for o in p.get("Contents", [])]
    out["pos"] = sorted((o["Key"], o["Size"]) for o in objs)
    return out


def test_incremental_equals_full_publish():
    original = pub.read_state().get("published_until")
    target = date(2026, 6, 30)
    try:
        pub.reset()
        pub.publish(target)
        full = snapshot()

        pub.reset()
        for until in [date(2026, 2, 15), date(2026, 2, 16), date(2026, 4, 1), target]:
            pub.publish(until)
        assert snapshot() == full
        assert pub.publish(target)["skipped"]          # publish ulang tanggal sama = no-op
    finally:
        pub.reset()
        if original:
            pub.publish(date.fromisoformat(original))
