"""Ekstraksi SAP SD -> lake raw/ (Parquet) -> raw_sap.* (append-only, dedup per hash).

- Master (KNA1, MARA, ...): full extract tiap run; hanya baris yang berubah (hash baru) yang dimuat.
- Dokumen (VBAK/LIKP/VBRK + item): query-based CDC pada greatest(ERDAT, AEDAT) dengan lookback,
  item diambil berdasarkan header yang berubah. Watermark per objek baru maju setelah commit.
- VBFA: baris tidak pernah berubah, incremental pada ERDAT.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

import pandas as pd
import psycopg

from ingestion.common.connections import dwh_connect, sap_connect
from ingestion.common.hashing import row_hashes
from ingestion.common.lake import Lake
from ingestion.common.ops import RunLog, get_watermark, run_all, set_watermark
from ingestion.common.settings import env

log = logging.getLogger(__name__)
SOURCE = "SAP"
LOOKBACK_DAYS = 3
BATCH_SIZE = 50_000

MASTERS = ["kna1", "knvv", "mara", "makt", "marm", "t023t", "t179t"]
DOCUMENTS = {"vbak": ["vbap", "vbep"], "likp": ["lips"], "vbrk": ["vbrp"]}
APPEND_ONLY = {"vbfa": "erdat"}
OBJECTS = MASTERS + list(DOCUMENTS) + list(APPEND_ONLY)


def raw_columns(dwh: psycopg.Connection, table: str) -> list[str]:
    """Kontrak kolom = definisi tabel raw_sap (tanpa kolom metadata)."""
    rows = dwh.execute("select column_name from information_schema.columns where table_schema = 'raw_sap' "
                       "and table_name = %s and column_name not like '\\_%%' order by ordinal_position",
                       (table,)).fetchall()
    if not rows:
        raise RuntimeError(f"raw_sap.{table} tidak ada; jalankan `python -m ingestion migrate`")
    return [r[0] for r in rows]


def fetch(sap: psycopg.Connection, sql: str, params: tuple, columns: list[str]) -> pd.DataFrame:
    with sap.cursor() as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=columns, dtype=object)


def select_list(columns: list[str]) -> str:
    return ", ".join(f"{c}::text" for c in columns)


def load_raw(dwh: psycopg.Connection, table: str, df: pd.DataFrame, columns: list[str], batch_id: str,
             source_file: str | None) -> int:
    """Append baris yang hash-nya belum ada di raw_sap.<table>; return jumlah baris dimuat."""
    if df.empty:
        return 0
    df = df.assign(_record_hash=row_hashes(df, columns)).drop_duplicates("_record_hash")
    cols = columns + ["_record_hash"]
    with dwh.cursor() as cur:
        cur.execute(f"create temp table tmp_{table} on commit drop as "
                    f"select {', '.join(cols)} from raw_sap.{table} with no data")
        with cur.copy(f"copy tmp_{table} ({', '.join(cols)}) from stdin") as cp:
            for row in df[cols].itertuples(index=False):
                cp.write_row(row)
        cur.execute(
            f"insert into raw_sap.{table} ({', '.join(cols)}, _batch_id, _source_system, _source_file) "
            f"select {', '.join('t.' + c for c in cols)}, %s, %s, %s from tmp_{table} t "
            f"where not exists (select 1 from raw_sap.{table} r where r._record_hash = t._record_hash)",
            (batch_id, SOURCE, source_file))
        return cur.rowcount


def _window(dwh: psycopg.Connection, obj: str, start: date | None) -> str:
    if start:
        return f"{start:%Y%m%d}"
    wm = get_watermark(dwh, SOURCE, obj)
    if not wm:
        return "00000000"
    return f"{date(int(wm[:4]), int(wm[4:6]), int(wm[6:])) - timedelta(days=LOOKBACK_DAYS):%Y%m%d}"


def _advance(dwh: psycopg.Connection, obj: str, seen_max: str | None) -> str | None:
    old = get_watermark(dwh, SOURCE, obj)
    new = max(filter(None, [old, seen_max]), default=None)
    if new and new != old:
        set_watermark(dwh, SOURCE, obj, new)
    return new


def extract_master(table: str, lake: Lake, run: RunLog, mandt: str) -> None:
    batch_id = str(uuid.uuid4())
    with dwh_connect() as dwh, sap_connect() as sap:
        cols = raw_columns(dwh, table)
        df = fetch(sap, f"select {select_list(cols)} from sap.{table} where mandt = %s", (mandt,), cols)
        run.rows_extracted = len(df)
        path = lake.put_raw("sap", table, batch_id, df) if len(df) else None
        run.rows_loaded = load_raw(dwh, table, df, cols, batch_id, path)
        dwh.commit()


def extract_documents(header: str, lake: Lake, run: RunLog, mandt: str, start: date | None, end: date | None) -> None:
    batch_id = str(uuid.uuid4())
    with dwh_connect() as dwh, sap_connect() as sap:
        frm = _window(dwh, header, start)
        to = f"{end:%Y%m%d}" if end else "99991231"
        run.watermark_from = frm
        changed = "greatest(erdat, aedat)"
        hcols = raw_columns(dwh, header)
        child_cols = {c: raw_columns(dwh, c) for c in DOCUMENTS[header]}

        frames = {header: [], **{c: [] for c in child_cols}}
        last_vbeln, seen_max = "", None
        while True:   # keyset pagination pada VBELN
            h = fetch(sap, f"select {select_list(hcols)}, {changed} as _changed from sap.{header} "
                           f"where mandt = %s and {changed} between %s and %s and vbeln > %s "
                           f"order by vbeln limit %s", (mandt, frm, to, last_vbeln, BATCH_SIZE), hcols + ["_changed"])
            if h.empty:
                break
            seen_max = max(filter(None, [seen_max, h["_changed"].max()]))
            frames[header].append(h.drop(columns="_changed"))
            for child, cols in child_cols.items():
                frames[child].append(fetch(sap, f"select {select_list(cols)} from sap.{child} "
                                                f"where mandt = %s and vbeln = any(%s)",
                                           (mandt, h["vbeln"].tolist()), cols))
            last_vbeln = h["vbeln"].iloc[-1]
            if len(h) < BATCH_SIZE:
                break

        # Header dulu lalu item, dalam satu transaksi bersama watermark
        for table, cols in {header: hcols, **child_cols}.items():
            df = pd.concat(frames[table], ignore_index=True) if frames[table] else pd.DataFrame(columns=cols)
            run.rows_extracted += len(df)
            path = lake.put_raw("sap", table, batch_id, df) if len(df) else None
            run.rows_loaded += load_raw(dwh, table, df, cols, batch_id, path)
        run.watermark_to = _advance(dwh, header, seen_max)
        dwh.commit()


def extract_append_only(table: str, lake: Lake, run: RunLog, mandt: str, start: date | None, end: date | None) -> None:
    batch_id = str(uuid.uuid4())
    date_col = APPEND_ONLY[table]
    with dwh_connect() as dwh, sap_connect() as sap:
        frm = _window(dwh, table, start)
        to = f"{end:%Y%m%d}" if end else "99991231"
        run.watermark_from = frm
        cols = raw_columns(dwh, table)
        df = fetch(sap, f"select {select_list(cols)} from sap.{table} where mandt = %s and {date_col} between %s and %s",
                   (mandt, frm, to), cols)
        run.rows_extracted = len(df)
        path = lake.put_raw("sap", table, batch_id, df) if len(df) else None
        run.rows_loaded = load_raw(dwh, table, df, cols, batch_id, path)
        run.watermark_to = _advance(dwh, table, df[date_col].max() if len(df) else None)
        dwh.commit()


def run(objects: list[str] | None = None, start: date | None = None, end: date | None = None, **meta) -> dict:
    """`start`/`end` (opsional) = backfill rentang tanggal perubahan; watermark tidak pernah mundur."""
    lake = Lake()
    mandt = env("SAP_CLIENT", "100")

    def one(obj: str) -> dict:
        with RunLog(SOURCE, obj, **meta) as rl:
            if obj in MASTERS:
                extract_master(obj, lake, rl, mandt)
            elif obj in DOCUMENTS:
                extract_documents(obj, lake, rl, mandt, start, end)
            elif obj in APPEND_ONLY:
                extract_append_only(obj, lake, rl, mandt, start, end)
            else:
                raise ValueError(f"objek SAP tidak dikenal: {obj}")
            return {"extracted": rl.rows_extracted, "loaded": rl.rows_loaded, "watermark": rl.watermark_to}

    return run_all(objects or OBJECTS, one)
