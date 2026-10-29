"""Koneksi ke warehouse, SAP (akun read-only), SFTP (akun ingest), dan S3."""
from __future__ import annotations

from contextlib import contextmanager

import boto3
import paramiko
import psycopg

from ingestion.common.retry import retry
from ingestion.common.settings import env

CONNECT_ERRORS = (psycopg.OperationalError, paramiko.SSHException, OSError)


@retry(CONNECT_ERRORS)
def dwh_connect() -> psycopg.Connection:
    return psycopg.connect(host=env("DWH_DB_HOST"), port=env("DWH_DB_PORT"), dbname=env("DWH_DB_NAME"),
                           user=env("DWH_DB_USER"), password=env("DWH_DB_PASSWORD"),
                           application_name="ingestion", connect_timeout=10)


@retry(CONNECT_ERRORS)
def sap_connect() -> psycopg.Connection:
    return psycopg.connect(host=env("SAP_DB_HOST"), port=env("SAP_DB_PORT"), dbname=env("SAP_DB_NAME"),
                           user=env("SAP_DB_READER_USER"), password=env("SAP_DB_READER_PASSWORD"),
                           application_name="ingestion", connect_timeout=10,
                           options="-c default_transaction_read_only=on")


@retry(CONNECT_ERRORS)
def _sftp_open() -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    client = paramiko.SSHClient()
    # SFTP lokal (docker compose); host key disimpan di volume agar stabil.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(env("SFTP_HOST"), port=int(env("SFTP_PORT")), username=env("SFTP_INGEST_USER", "ingest"),
                   password=env("SFTP_INGEST_PASSWORD"), look_for_keys=False, allow_agent=False, timeout=30)
    return client, client.open_sftp()


@contextmanager
def sftp_session():
    client, sftp = _sftp_open()
    try:
        yield sftp
    finally:
        sftp.close()
        client.close()


def s3_client():
    return boto3.client("s3", endpoint_url=env("S3_ENDPOINT_URL"), aws_access_key_id=env("S3_ACCESS_KEY"),
                        aws_secret_access_key=env("S3_SECRET_KEY"), region_name="us-east-1")
