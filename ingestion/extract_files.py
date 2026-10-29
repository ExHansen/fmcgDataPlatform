"""Ekstraksi file sell-out POS mingguan dari bucket retailer (S3)."""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import date, datetime

from botocore.exceptions import ClientError

from ingestion.common.connections import dwh_connect, s3_client
from ingestion.common.files import SourceFile, already_processed, ingest_file
from ingestion.common.lake import Lake
from ingestion.common.ops import RunLog, run_all
from ingestion.common.retry import retry
from ingestion.common.settings import contracts, env

log = logging.getLogger(__name__)


def list_pos_files(s3, bucket: str, contract: dict) -> dict[str, list[tuple[SourceFile, bool]]]:
    """Kelompokkan objek per retailer; objek dengan key tak sesuai pola masuk grup '_UNKNOWN'."""
    pattern = re.compile(contract["key_pattern"])
    prefix = contract["source_system_prefix"]
    groups: dict[str, list] = defaultdict(list)
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="pos/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            m = pattern.match(key)
            retailer = m["retailer"] if m else "_UNKNOWN"
            bdate = date.fromisocalendar(int(m["year"]), int(m["week"]), 1) if m else None
            groups[retailer].append((SourceFile(
                source_system=f"{prefix}{retailer}", entity_code=retailer, path=f"s3://{bucket}/{key}",
                name=key.rsplit("/", 1)[-1], size=obj["Size"], received_at=obj["LastModified"],
                business_date=bdate), bool(m)))
    return groups


@retry((ClientError, OSError))
def download(s3, bucket: str, key: str) -> tuple[bytes, datetime | None]:
    resp = s3.get_object(Bucket=bucket, Key=key)
    delivered = resp.get("Metadata", {}).get("delivered-at")
    return resp["Body"].read(), datetime.fromisoformat(delivered) if delivered else None


def ingest_retailer(files: list[tuple[SourceFile, bool]], s3, bucket: str, lake: Lake, run: RunLog,
                    retry_rejected: bool) -> dict:
    contract = contracts()["pos"]
    stats = Counter()
    with dwh_connect() as conn:
        for f, key_ok in sorted(files, key=lambda x: x[0].path):
            if already_processed(conn, f) and not retry_rejected:
                stats["SKIPPED"] += 1
                continue
            data, _delivered = download(s3, bucket, f.path.removeprefix(f"s3://{bucket}/"))
            status = ingest_file(conn, lake, run, f, data, fmt="csv", contract=contract,
                                 lake_source=f"pos/{f.entity_code}", raw_table="raw_pos.sellout",
                                 code_col="retailer_code", retry_rejected=retry_rejected,
                                 precheck_error=None if key_ok else "key objek tidak sesuai pola kontrak")
            stats[status] += 1
    return dict(stats)


def run(retailers: list[str] | None = None, retry_rejected: bool = False, **meta) -> dict:
    lake = Lake()
    s3 = s3_client()
    bucket = env("S3_RETAILER_BUCKET")
    contract = contracts()["pos"]
    groups = list_pos_files(s3, bucket, contract)
    names = retailers or sorted(groups)

    def one(retailer: str) -> dict:
        with RunLog(f"{contract['source_system_prefix']}{retailer}", "sellout", **meta) as rl:
            return ingest_retailer(groups.get(retailer, []), s3, bucket, lake, rl, retry_rejected)

    return run_all(names, one)
