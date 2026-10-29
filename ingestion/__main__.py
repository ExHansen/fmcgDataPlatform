"""CLI ingestion.

    python -m ingestion migrate
    python -m ingestion sap  [--objects vbak,likp] [--start-date D --end-date D]
    python -m ingestion dms  [--distributors DIST_A] [--retry-rejected]
    python -m ingestion pos  [--retailers MTM] [--retry-rejected]
    python -m ingestion all

Exit code != 0 jika ada objek yang gagal (supaya orkestrator me-retry).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

from ingestion import extract_files, extract_sap, extract_sftp
from ingestion.migrate import migrate


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="ingestion")
    p.add_argument("--dag-id")
    p.add_argument("--task-id")
    p.add_argument("--try-number", type=int)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sp = sub.add_parser("sap")
    sp.add_argument("--objects", type=_csv)
    sp.add_argument("--start-date", type=date.fromisoformat)
    sp.add_argument("--end-date", type=date.fromisoformat)
    dp = sub.add_parser("dms")
    dp.add_argument("--distributors", type=_csv)
    dp.add_argument("--retry-rejected", action="store_true")
    pp = sub.add_parser("pos")
    pp.add_argument("--retailers", type=_csv)
    pp.add_argument("--retry-rejected", action="store_true")
    sub.add_parser("all")
    args = p.parse_args()
    meta = {"dag_id": args.dag_id, "task_id": args.task_id, "try_number": args.try_number}

    try:
        if args.cmd == "migrate":
            out = {"applied": migrate()}
        elif args.cmd == "sap":
            out = extract_sap.run(args.objects, args.start_date, args.end_date, **meta)
        elif args.cmd == "dms":
            out = extract_sftp.run(args.distributors, args.retry_rejected, **meta)
        elif args.cmd == "pos":
            out = extract_files.run(args.retailers, args.retry_rejected, **meta)
        else:
            out = {"migrate": migrate(), "sap": extract_sap.run(**meta),
                   "dms": extract_sftp.run(**meta), "pos": extract_files.run(**meta)}
    except RuntimeError as exc:
        logging.error("%s", exc)
        return 1
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
