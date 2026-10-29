"""Ekstraksi file secondary sales distributor dari SFTP (akun ingest, inbox/{DIST}/)."""
from __future__ import annotations

import logging
import re
import stat
from collections import Counter
from datetime import datetime, timezone

from ingestion.common.connections import dwh_connect, sftp_session
from ingestion.common.files import SourceFile, already_processed, ingest_file
from ingestion.common.lake import Lake
from ingestion.common.ops import RunLog, run_all
from ingestion.common.retry import retry
from ingestion.common.settings import contracts

log = logging.getLogger(__name__)
INBOX = "inbox"


def list_files(sftp, dist: str, contract: dict) -> list[tuple[SourceFile, bool]]:
    """(file, nama sesuai pola?) untuk tiap file di folder distributor, urut waktu terima."""
    pattern = re.compile(contract["filename_pattern"])
    out = []
    for a in sftp.listdir_attr(f"{INBOX}/{dist}"):
        if not stat.S_ISREG(a.st_mode):
            continue
        m = pattern.match(a.filename)
        bdate = datetime.strptime(m["date"], "%Y%m%d").date() if m else None
        out.append((SourceFile(source_system=contract["source_system"], entity_code=dist,
                               path=f"{INBOX}/{dist}/{a.filename}", name=a.filename, size=a.st_size,
                               received_at=datetime.fromtimestamp(a.st_mtime, tz=timezone.utc),
                               business_date=bdate), bool(m)))
    return sorted(out, key=lambda x: (x[0].received_at, x[0].name))


@retry((OSError, EOFError))
def download(sftp, path: str) -> bytes:
    with sftp.open(path, "rb") as fh:
        fh.prefetch()
        return fh.read()


def ingest_distributor(dist: str, lake: Lake, run: RunLog, retry_rejected: bool) -> dict:
    contract = contracts()["dms"][dist]
    stats = Counter()
    with dwh_connect() as conn, sftp_session() as sftp:
        for f, name_ok in list_files(sftp, dist, contract):
            if already_processed(conn, f) and not retry_rejected:
                stats["SKIPPED"] += 1
                continue
            status = ingest_file(conn, lake, run, f, download(sftp, f.path), fmt=contract["format"],
                                 contract=contract, lake_source=f"dms/{dist}", raw_table="raw_dms.secondary_sales",
                                 code_col="distributor_code", retry_rejected=retry_rejected,
                                 precheck_error=None if name_ok else "nama file tidak sesuai pola kontrak")
            stats[status] += 1
    # File REJECTED bukan kegagalan task: dicatat di manifest dan dilaporkan lewat alert.
    return dict(stats)


def run(distributors: list[str] | None = None, retry_rejected: bool = False, **meta) -> dict:
    lake = Lake()

    def one(dist: str) -> dict:
        with RunLog(contracts()["dms"][dist]["source_system"], "secondary_sales", **meta) as rl:
            return ingest_distributor(dist, lake, rl, retry_rejected)

    return run_all(distributors or list(contracts()["dms"]), one)
