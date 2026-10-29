"""Monitoring terhadap warehouse utama (hanya membaca; tidak mengirim alert).

Jalankan: RUN_INTEGRATION=1 pytest tests/test_integration_monitoring.py
"""
import os

import pytest

from ingestion.common.connections import dwh_connect
from monitoring import report

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="butuh warehouse + dbt build")


def test_freshness_covers_every_source():
    with dwh_connect() as conn:
        rows = dict(conn.execute("select source_system, status from ops.source_freshness").fetchall())
    assert set(rows) == {"SAP", "DMS_A", "DMS_B", "DMS_C", "POS_LST", "POS_MTM", "POS_SNT"}
    assert set(rows.values()) <= {"OK", "WARN", "ERROR"}


def test_injected_missing_file_becomes_alert_issue():
    """File distributor yang hilang (chaos) dalam 30 hari terakhir muncul sebagai issue alert."""
    with dwh_connect() as conn:
        run_id = report.latest_dbt_run(conn)
        recent_missing = conn.execute(
            "select distributor_code, business_date from marts.dms_file_status where status = 'MISSING' "
            "and business_date >= (now() at time zone 'Asia/Jakarta')::date - 30").fetchall()
        issues = report.collect(conn, run_id)
    keys = {i.key for i in issues}
    assert recent_missing, "tidak ada file hilang 30 hari terakhir untuk diuji"
    for dist, day in recent_missing:
        assert f"recon:dms_file_received:{dist}:{day}" in keys


def test_alerted_issues_are_not_sent_again():
    with dwh_connect() as conn:
        issues = report.collect(conn, report.latest_dbt_run(conn))
        alerted = {r[0] for r in conn.execute("select alert_key from ops.alert_log where source = 'monitoring'")}
        fresh = report.dedup(conn, issues)
    once_only = {i.key for i in fresh if i.key.startswith(("recon:", "pipeline:"))}
    assert not once_only & alerted
