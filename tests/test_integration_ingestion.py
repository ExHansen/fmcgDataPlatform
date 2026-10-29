"""Integrasi ingestion terhadap sistem sumber yang sedang berjalan (docker compose + simulator publish).

Memakai database `dwh_test` dan bucket `lake-test` sendiri, jadi warehouse utama tidak tersentuh.
Jalankan: RUN_INTEGRATION=1 pytest tests/test_integration_ingestion.py
"""
import os

import paramiko
import psycopg
import pytest

from ingestion import extract_files, extract_sap, extract_sftp
from ingestion.common.settings import env
from ingestion.migrate import migrate

pytestmark = pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="butuh docker compose up")

TEST_DB = "dwh_test"


@pytest.fixture(scope="module")
def test_warehouse():
    admin = dict(host=env("DWH_DB_HOST"), port=env("DWH_DB_PORT"), user=env("DWH_DB_USER"),
                 password=env("DWH_DB_PASSWORD"))
    with psycopg.connect(dbname=env("DWH_DB_NAME"), autocommit=True, **admin) as c:
        c.execute(f"drop database if exists {TEST_DB} with (force)")
        c.execute(f"create database {TEST_DB}")
    mp = pytest.MonkeyPatch()
    mp.setenv("DWH_DB_NAME", TEST_DB)
    mp.setenv("S3_LAKE_BUCKET", "lake-test")
    migrate()
    yield lambda: psycopg.connect(dbname=TEST_DB, **admin)
    mp.undo()


def q(connect, sql, params=()):
    with connect() as c:
        return c.execute(sql, params).fetchall()


SAP_SUBSET = ["kna1", "mara", "vbrk", "vbfa"]


def test_sap_full_then_rerun_is_idempotent(test_warehouse):
    first = extract_sap.run(SAP_SUBSET)
    assert all(r["loaded"] > 0 for r in first.values())
    second = extract_sap.run(SAP_SUBSET)
    assert all(r["loaded"] == 0 for r in second.values())

    # Versi terbaru per kunci di raw = isi tabel sumber saat ini
    with extract_sap.sap_connect() as sap:
        src_vbrk = sap.execute("select count(*), count(*) filter (where fksto = 'X') from sap.vbrk").fetchone()
        src_vbrp = sap.execute("select count(*) from sap.vbrp").fetchone()[0]
    raw = q(test_warehouse, """
        select count(*), count(*) filter (where fksto = 'X') from (
          select distinct on (vbeln) * from raw_sap.vbrk order by vbeln, _ingested_at desc, aedat desc) t""")[0]
    assert raw == src_vbrk
    assert q(test_warehouse, "select count(distinct (vbeln, posnr)) from raw_sap.vbrp")[0][0] == src_vbrp


def test_sap_failure_keeps_watermark_and_rolls_back(test_warehouse, monkeypatch):
    before = q(test_warehouse, "select last_watermark from ops.ingestion_watermark where object_name = 'likp'")
    assert before == []
    original = extract_sap.load_raw

    def broken(dwh, table, *a, **kw):
        if table == "lips":
            raise psycopg.OperationalError("koneksi putus saat load item")
        return original(dwh, table, *a, **kw)

    monkeypatch.setattr(extract_sap, "load_raw", broken)
    with pytest.raises(RuntimeError, match="likp"):
        extract_sap.run(["likp"])
    assert q(test_warehouse, "select count(*) from raw_sap.likp")[0][0] == 0         # header ikut di-rollback
    assert q(test_warehouse, "select last_watermark from ops.ingestion_watermark where object_name = 'likp'") == []
    assert q(test_warehouse, "select status from ops.pipeline_run_log where object_name = 'likp'") == [("FAILED",)]

    monkeypatch.setattr(extract_sap, "load_raw", original)
    assert extract_sap.run(["likp"])["likp"]["loaded"] > 0


def test_dms_resume_after_failure_and_no_duplicates(test_warehouse, monkeypatch):
    original = extract_sftp.download
    calls = {"n": 0}

    def flaky(sftp, path):
        calls["n"] += 1
        if calls["n"] == 40:
            raise OSError("SFTP putus di tengah")
        return original(sftp, path)

    monkeypatch.setattr(extract_sftp, "download", flaky)
    with pytest.raises(RuntimeError):
        extract_sftp.run(["DIST_A"])
    partial = q(test_warehouse, "select count(*) from ops.file_manifest where status = 'LOADED'")[0][0]
    assert partial == 39                                   # file sebelum error sudah ter-commit

    monkeypatch.setattr(extract_sftp, "download", original)
    stats = extract_sftp.run(["DIST_A"])["DIST_A"]
    assert stats["SKIPPED"] == 39 and stats["LOADED"] > 0
    dup = q(test_warehouse, """select count(*) from (select _source_file, source_row_number from raw_dms.secondary_sales
                               group by 1, 2 having count(*) > 1) d""")[0][0]
    assert dup == 0
    assert extract_sftp.run(["DIST_A"])["DIST_A"] == {"SKIPPED": partial + stats["LOADED"]}


def test_dms_rejects_bad_file_and_flags_duplicate_content(test_warehouse):
    client, sftp = distributor_sftp()
    bad = "secondary_20991230.csv"
    good_copy = "secondary_20991231.csv"
    try:
        with sftp.open(f"upload/{bad}", "wb") as fh:
            fh.write(b"No_Faktur;Tgl_Faktur\r\nX;01/01/2099\r\n")
        existing = sorted(n for n in sftp.listdir("upload") if n.startswith("secondary_2026"))[0]
        with sftp.open(f"upload/{existing}", "rb") as src, sftp.open(f"upload/{good_copy}", "wb") as dst:
            dst.write(src.read())

        extract_sftp.run(["DIST_A"])
        rows = dict(q(test_warehouse, "select file_path, status from ops.file_manifest where file_path like %s",
                      ("%secondary_2099%",)))
        assert rows[f"inbox/DIST_A/{bad}"] == "REJECTED"
        assert rows[f"inbox/DIST_A/{good_copy}"] == "DUPLICATE"
        reason = q(test_warehouse, "select reject_reason from ops.file_manifest where file_path = %s",
                   (f"inbox/DIST_A/{bad}",))[0][0]
        assert "kolom wajib hilang" in reason
        # Run berikutnya tidak mencatat ulang file yang sama
        extract_sftp.run(["DIST_A"])
        assert q(test_warehouse, "select count(*) from ops.file_manifest where file_path like %s",
                 ("%secondary_2099%",))[0][0] == 2
    finally:
        for name in (bad, good_copy):
            try:
                sftp.remove(f"upload/{name}")
            except OSError:
                pass
        sftp.close()
        client.close()


def test_pos_ingestion_versions_and_rerun(test_warehouse):
    first = extract_files.run(["MTM"])["MTM"]
    assert first["LOADED"] > 0
    assert extract_files.run(["MTM"])["MTM"] == {"SKIPPED": first["LOADED"]}
    weeks = q(test_warehouse, "select count(distinct business_date), max(version) from ops.file_manifest "
                              "where source_system = 'POS_MTM' and status = 'LOADED'")[0]
    assert weeks == (first["LOADED"], 1)


def distributor_sftp():
    """Login sebagai distributor A (bukan akun ingest) untuk menaruh file uji."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(env("SFTP_HOST"), port=int(env("SFTP_PORT")), username="dist_a", password=env("DIST_A_PASSWORD"),
                   look_for_keys=False, allow_agent=False)
    return client, client.open_sftp()
