"""Tabel operasional: pipeline_run_log, ingestion_watermark, file_manifest."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import psycopg

from ingestion.common.connections import dwh_connect

log = logging.getLogger(__name__)


class RunLog:
    """1 baris `ops.pipeline_run_log` per task. Dicatat lewat koneksi terpisah (autocommit)
    supaya status FAILED tetap tersimpan walau transaksi load di-rollback."""

    def __init__(self, source_system: str, object_name: str | None = None, dag_id: str | None = None,
                 task_id: str | None = None, try_number: int | None = None):
        self.run_id = str(uuid.uuid4())
        self.source_system = source_system
        self.object_name = object_name
        self.rows_extracted = 0
        self.rows_loaded = 0
        self.watermark_from: str | None = None
        self.watermark_to: str | None = None
        self.status = "SUCCESS"
        self._meta = (dag_id, task_id, try_number)

    def __enter__(self) -> "RunLog":
        with dwh_connect() as conn:
            conn.execute(
                "insert into ops.pipeline_run_log (run_id, dag_id, task_id, source_system, object_name, started_at, "
                "status, airflow_try_number) values (%s, %s, %s, %s, %s, %s, 'RUNNING', %s)",
                (self.run_id, self._meta[0], self._meta[1], self.source_system, self.object_name,
                 datetime.now(timezone.utc), self._meta[2]))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        status = "FAILED" if exc else self.status
        with dwh_connect() as conn:
            conn.execute(
                "update ops.pipeline_run_log set ended_at = %s, status = %s, rows_extracted = %s, rows_loaded = %s, "
                "watermark_from = %s, watermark_to = %s, error_message = %s where run_id = %s",
                (datetime.now(timezone.utc), status, self.rows_extracted, self.rows_loaded, self.watermark_from,
                 self.watermark_to, f"{exc_type.__name__}: {exc}"[:2000] if exc else None, self.run_id))
        log.info("[%s/%s] %s extracted=%d loaded=%d watermark=%s->%s", self.source_system, self.object_name or "-",
                 status, self.rows_extracted, self.rows_loaded, self.watermark_from, self.watermark_to)


def run_all(names: list[str], fn) -> dict:
    """Jalankan `fn(name)` untuk tiap objek; objek yang gagal tidak menghentikan yang lain,
    tapi task tetap dinyatakan gagal di akhir (supaya Airflow me-retry)."""
    results, errors = {}, []
    for name in names:
        try:
            results[name] = fn(name)
        except Exception as exc:  # noqa: BLE001 - dicatat di run log, dilempar ulang di bawah
            log.exception("%s gagal", name)
            errors.append(f"{name}: {exc}")
    if errors:
        raise RuntimeError(f"{len(errors)} objek gagal: " + "; ".join(errors))
    return results


# ---------- watermark ----------
def get_watermark(conn: psycopg.Connection, source_system: str, object_name: str) -> str | None:
    row = conn.execute("select last_watermark from ops.ingestion_watermark where source_system = %s "
                       "and object_name = %s", (source_system, object_name)).fetchone()
    return row[0] if row else None


def set_watermark(conn: psycopg.Connection, source_system: str, object_name: str, value: str) -> None:
    conn.execute(
        "insert into ops.ingestion_watermark (source_system, object_name, last_watermark, updated_at) "
        "values (%s, %s, %s, now()) on conflict (source_system, object_name) "
        "do update set last_watermark = excluded.last_watermark, updated_at = now()",
        (source_system, object_name, value))


# ---------- file manifest ----------
def manifest_seen(conn: psycopg.Connection, source_system: str, file_path: str, sha256: str) -> str | None:
    """Status file (path + isi yang sama) yang pernah diproses, atau None jika baru."""
    row = conn.execute("select status from ops.file_manifest where source_system = %s and file_path = %s "
                       "and sha256 = %s order by received_at desc limit 1", (source_system, file_path, sha256)).fetchone()
    return row[0] if row else None


def content_already_loaded(conn: psycopg.Connection, source_system: str, sha256: str) -> bool:
    return conn.execute("select 1 from ops.file_manifest where source_system = %s and sha256 = %s "
                        "and status = 'LOADED'", (source_system, sha256)).fetchone() is not None


def next_version(conn: psycopg.Connection, source_system: str, business_date) -> int:
    row = conn.execute("select count(*) from ops.file_manifest where source_system = %s and business_date = %s "
                       "and status = 'LOADED'", (source_system, business_date)).fetchone()
    return row[0] + 1


def record_file(conn: psycopg.Connection, *, run_id: str, source_system: str, file_path: str, file_size: int,
                sha256: str, received_at: datetime, business_date, status: str, rows: int | None,
                version: int = 1, reject_reason: str | None = None, batch_id: str | None = None) -> None:
    conn.execute(
        "insert into ops.file_manifest (file_id, run_id, source_system, file_path, file_size, sha256, received_at, "
        "business_date, version, status, rows, reject_reason, batch_id) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (str(uuid.uuid4()), run_id, source_system, file_path, file_size, sha256, received_at, business_date,
         version, status, rows, reject_reason, batch_id))
