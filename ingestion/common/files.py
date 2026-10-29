"""Load satu file sumber secara idempotent: manifest -> landing -> validasi kontrak -> raw.

Aturan:
- path + isi (sha256) yang sama pernah diproses  -> dilewati
- isi sama dengan file lain yang sudah LOADED      -> DUPLICATE (tidak dimuat)
- gagal parse / kolom wajib hilang                 -> REJECTED (file tetap disimpan di landing)
- selain itu                                       -> LOADED, version = urutan file untuk business_date tsb
Semua tulisan DB untuk satu file ada dalam satu transaksi.
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import psycopg

from ingestion.common import ops
from ingestion.common.hashing import sha256_bytes
from ingestion.common.lake import Lake

log = logging.getLogger(__name__)
WIB = timezone(timedelta(hours=7))   # Asia/Jakarta, tanpa DST


class ContractError(ValueError):
    pass


@dataclass
class SourceFile:
    source_system: str       # DMS_A, POS_MTM, ...
    entity_code: str         # kode distributor / retailer
    path: str                # path di sistem sumber
    name: str
    size: int
    received_at: datetime
    business_date: date | None


def parse(data: bytes, fmt: str) -> pd.DataFrame:
    if fmt == "csv_semicolon":
        return pd.read_csv(io.BytesIO(data), sep=";", dtype=str, keep_default_na=False, encoding="cp1252")
    if fmt == "xlsx":
        return pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False)
    if fmt == "pipe_txt":
        return pd.read_csv(io.BytesIO(data), sep="|", dtype=str, keep_default_na=False)
    if fmt == "csv":
        return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
    raise ContractError(f"format tidak dikenal: {fmt}")


def check_contract(df: pd.DataFrame, contract: dict) -> list[str]:
    """Return kolom tak dikenal (warning); raise ContractError jika field wajib hilang."""
    cols = set(df.columns)
    missing = [field for field, names in contract["required"].items() if not cols & set(names)]
    if missing:
        raise ContractError(f"kolom wajib hilang: {missing}; kolom file: {sorted(cols)}")
    known = {n for names in contract["required"].values() for n in names} | set(contract.get("optional", []))
    return sorted(cols - known)


def insert_rows(conn: psycopg.Connection, table: str, code_col: str, f: SourceFile, df: pd.DataFrame,
                batch_id: str, lake_path: str) -> int:
    payloads = [json.dumps(r, ensure_ascii=False) for r in df.to_dict(orient="records")]
    with conn.cursor() as cur:
        with cur.copy(f"copy {table} ({code_col}, source_row_number, payload, _batch_id, _source_system, "
                      f"_source_file, _record_hash) from stdin") as cp:
            for i, p in enumerate(payloads, start=1):
                cp.write_row((f.entity_code, i, p, batch_id, f.source_system, lake_path, sha256_bytes(p.encode())))
    return len(payloads)


def already_processed(conn: psycopg.Connection, f: SourceFile) -> bool:
    """Cek murah tanpa mengunduh: path, ukuran, dan waktu terima sama dengan yang tercatat."""
    return conn.execute("select 1 from ops.file_manifest where source_system = %s and file_path = %s "
                        "and file_size = %s and received_at = %s", (f.source_system, f.path, f.size, f.received_at)
                        ).fetchone() is not None


def ingest_file(conn: psycopg.Connection, lake: Lake, run: ops.RunLog, f: SourceFile, data: bytes, *,
                fmt: str, contract: dict, lake_source: str, raw_table: str, code_col: str,
                retry_rejected: bool = False, precheck_error: str | None = None) -> str:
    """`precheck_error`: alasan penolakan yang sudah diketahui sebelum parse (mis. nama file salah)."""
    sha = sha256_bytes(data)
    seen = ops.manifest_seen(conn, f.source_system, f.path, sha)
    if seen and not (seen == "REJECTED" and retry_rejected):
        return "SKIPPED"
    meta = dict(run_id=run.run_id, source_system=f.source_system, file_path=f.path, file_size=f.size, sha256=sha,
                received_at=f.received_at, business_date=f.business_date)
    if ops.content_already_loaded(conn, f.source_system, sha):
        ops.record_file(conn, **meta, status="DUPLICATE", rows=None)
        conn.commit()
        return "DUPLICATE"

    landing = lake.put_landing(lake_source, f.received_at.astimezone(WIB).date(), f.name, sha, data)
    try:
        if precheck_error:
            raise ContractError(precheck_error)
        df = parse(data, fmt)
        unknown = check_contract(df, contract)
    except Exception as exc:  # noqa: BLE001 - file rusak apa pun alasannya = REJECTED
        log.error("REJECTED %s: %s", f.path, exc)
        ops.record_file(conn, **meta, status="REJECTED", rows=None, reject_reason=str(exc)[:1000])
        conn.commit()
        return "REJECTED"
    if unknown:
        log.warning("%s: kolom baru tidak dikenal %s (tetap dimuat)", f.path, unknown)

    batch_id = str(uuid.uuid4())
    lake.put_raw(lake_source, raw_table.split(".")[1], batch_id,
                 df.assign(_source_file=landing, _source_row_number=range(1, len(df) + 1)))
    rows = insert_rows(conn, raw_table, code_col, f, df, batch_id, landing)
    version = ops.next_version(conn, f.source_system, f.business_date)
    ops.record_file(conn, **meta, status="LOADED", rows=rows, version=version, batch_id=batch_id)
    conn.commit()
    run.rows_extracted += len(df)
    run.rows_loaded += rows
    return "LOADED"
