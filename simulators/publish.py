"""Kirim data simulasi ke sistem sumber sampai tanggal `until`, seakan waktu berjalan.

- SAP mock: upsert versi terbaru tiap baris dengan `_event_date <= until`
- SFTP: file distributor yang `arrival_ts` sudah lewat diunggah ke folder distributor
- Bucket retailer: file POS mingguan diunggah ke S3

State (`published_until`) disimpan supaya publish berikutnya hanya mengirim yang baru.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import boto3
import pandas as pd
import paramiko
import psycopg
from botocore.exceptions import ClientError

from simulators.sap_mock.build import PRIMARY_KEYS
from simulators.settings import STATE_PATH, TRUTH_DIR, env

log = logging.getLogger(__name__)
TZ = "Asia/Jakarta"
DIST_USERS = {"DIST_A": "dist_a", "DIST_B": "dist_b", "DIST_C": "dist_c"}


# ---------- state ----------
def read_state() -> dict:
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ---------- koneksi ----------
def sap_connect() -> psycopg.Connection:
    return psycopg.connect(host=env("SAP_DB_HOST"), port=env("SAP_DB_PORT"), dbname=env("SAP_DB_NAME"),
                           user=env("SAP_DB_ADMIN_USER"), password=env("SAP_DB_ADMIN_PASSWORD"))


def s3_client():
    return boto3.client("s3", endpoint_url=env("S3_ENDPOINT_URL"), aws_access_key_id=env("S3_ACCESS_KEY"),
                        aws_secret_access_key=env("S3_SECRET_KEY"), region_name="us-east-1")


def sftp_connect(distributor_code: str) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    client = paramiko.SSHClient()
    # Server SFTP lokal (docker); host key disimpan di volume agar stabil.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(env("SFTP_HOST"), port=int(env("SFTP_PORT")), username=DIST_USERS[distributor_code],
                   password=env(f"{distributor_code}_PASSWORD"), look_for_keys=False, allow_agent=False)
    return client, client.open_sftp()


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)


# ---------- SAP ----------
def rows_to_publish(df: pd.DataFrame, pk: list[str], frm: date | None, until: date) -> pd.DataFrame:
    """Versi terbaru (<= until) untuk setiap kunci yang punya event di (frm, until]."""
    ev = df["_event_date"].dt.date
    new = (ev <= until) if frm is None else ((ev > frm) & (ev <= until))
    touched = df.loc[new, pk].drop_duplicates()
    if touched.empty:
        return touched
    visible = df[ev <= until].merge(touched, on=pk)
    return visible.sort_values("_event_date", kind="stable").drop_duplicates(pk, keep="last").drop(columns="_event_date")


def upsert(conn: psycopg.Connection, table: str, pk: list[str], df: pd.DataFrame) -> None:
    cols = list(df.columns)
    col_list = ", ".join(cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in pk)
    with conn.cursor() as cur:
        cur.execute(f"create temp table tmp_{table} (like sap.{table} including defaults) on commit drop")
        with cur.copy(f"copy tmp_{table} ({col_list}) from stdin") as cp:
            for row in df.astype(object).where(df.notna(), None).itertuples(index=False):
                cp.write_row(row)
        cur.execute(f"insert into sap.{table} ({col_list}) select {col_list} from tmp_{table} "
                    f"on conflict ({', '.join(pk)}) do update set {updates}")


def publish_sap(frm: date | None, until: date) -> dict[str, int]:
    counts = {}
    with sap_connect() as conn:
        for table, pk in PRIMARY_KEYS.items():
            df = pd.read_parquet(TRUTH_DIR / "sap" / f"{table}.parquet")
            rows = rows_to_publish(df, pk, frm, until)
            if len(rows):
                upsert(conn, table, pk, rows)
            counts[table] = len(rows)
        conn.commit()
    return counts


# ---------- file ----------
def _due(index: pd.DataFrame, frm: date | None, until: date) -> pd.DataFrame:
    end = pd.Timestamp(until + timedelta(days=1))
    mask = index["arrival_ts"] < end
    if frm is not None:
        mask &= index["arrival_ts"] >= pd.Timestamp(frm + timedelta(days=1))
    return index[mask].sort_values("arrival_ts")


def publish_dms(frm: date | None, until: date) -> int:
    due = _due(pd.read_parquet(TRUTH_DIR / "dms_index.parquet"), frm, until)
    for dist, files in due.groupby("distributor_code"):
        client, sftp = sftp_connect(dist)
        try:
            for f in files.itertuples():
                remote = f"upload/{f.remote_name}"
                sftp.put(f.local_path, remote)
                ts = pd.Timestamp(f.arrival_ts).tz_localize(TZ).timestamp()
                sftp.utime(remote, (ts, ts))   # waktu file = waktu "diterima"
        finally:
            sftp.close()
            client.close()
    return len(due)


def publish_pos(frm: date | None, until: date) -> int:
    due = _due(pd.read_parquet(TRUTH_DIR / "pos_index.parquet"), frm, until)
    s3 = s3_client()
    bucket = env("S3_RETAILER_BUCKET")
    ensure_bucket(s3, bucket)
    for f in due.itertuples():
        s3.put_object(Bucket=bucket, Key=f.object_key, Body=Path(f.local_path).read_bytes(),
                      ContentType="text/csv",
                      Metadata={"delivered-at": pd.Timestamp(f.arrival_ts).tz_localize(TZ).isoformat()})
    return len(due)


def publish(until: date) -> dict:
    if not (TRUTH_DIR / "dms_index.parquet").exists():
        raise RuntimeError("Belum ada data simulasi; jalankan `python -m simulators generate` dulu")
    state = read_state()
    frm = date.fromisoformat(state["published_until"]) if state.get("published_until") else None
    if frm is not None and until <= frm:
        log.info("Sudah dipublikasikan sampai %s; tidak ada yang dikirim", frm)
        return {"published_until": str(frm), "skipped": True}

    result = {"from": str(frm) if frm else None, "until": str(until)}
    result["sap_rows"] = publish_sap(frm, until)
    result["dms_files"] = publish_dms(frm, until)
    result["pos_files"] = publish_pos(frm, until)
    write_state({"published_until": str(until)})
    return result


def reset() -> None:
    """Kosongkan semua sistem sumber dan state publish."""
    with sap_connect() as conn:
        conn.execute("truncate " + ", ".join(f"sap.{t}" for t in PRIMARY_KEYS))
    for dist in DIST_USERS:
        client, sftp = sftp_connect(dist)
        try:
            for name in sftp.listdir("upload"):
                sftp.remove(f"upload/{name}")
        finally:
            sftp.close()
            client.close()
    s3 = s3_client()
    bucket = env("S3_RETAILER_BUCKET")
    ensure_bucket(s3, bucket)
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
    STATE_PATH.unlink(missing_ok=True)
