"""CLI monitoring.

    python -m monitoring notify [--dry-run]     # ringkasan masalah run terakhir -> alert (dedup)
    python -m monitoring alert --severity error --title "..." [--line "..."]   # alert manual / callback Airflow
"""
from __future__ import annotations

import argparse
import logging
import sys

from ingestion.common.connections import dwh_connect
from monitoring import report
from monitoring.alerting import Alert, send


def main() -> int:
    for stream in (sys.stdout, sys.stderr):   # konsol Windows default cp1252; pesan alert berisi emoji
        stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="monitoring")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("notify")
    n.add_argument("--dry-run", action="store_true", help="cetak saja, tidak mengirim / mencatat")
    a = sub.add_parser("alert")
    a.add_argument("--severity", choices=["info", "warn", "error"], default="error")
    a.add_argument("--source", default="airflow")
    a.add_argument("--title", required=True)
    a.add_argument("--line", action="append", default=[])
    a.add_argument("--key")
    args = p.parse_args()

    if args.cmd == "alert":
        send(Alert(severity=args.severity, source=args.source, title=args.title, lines=args.line,
                   alert_keys=[args.key] if args.key else []))
        return 0

    with dwh_connect() as conn:
        run_id = report.latest_dbt_run(conn)
        issues = report.collect(conn, run_id)
        new = report.dedup(conn, issues)
    logging.info("%d masalah ditemukan, %d baru (belum di-alert)", len(issues), len(new))
    alert = report.build_alert(new, run_id)
    if alert is None:
        logging.info("Tidak ada alert baru")
        return 0
    if args.dry_run:
        print(alert.text())
        return 0
    send(alert)
    return 0


if __name__ == "__main__":
    sys.exit(main())
