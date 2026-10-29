"""DAG platform data komersial FMCG.

- simulate_source_systems    05:00  simulator "memajukan waktu": kirim data s/d kemarin ke SAP/SFTP/bucket
- daily_commercial_pipeline  06:00  ingestion 3 sumber -> dbt build -> notify
- weekly_reconcile           Minggu 03:00  re-extract penuh SAP, dbt full-refresh, notify
- forecast_weekly            Senin 08:00   backtest + forecast 8 minggu, dbt model forecast, notify

Semua task memanggil kode project lewat virtualenv terpisah (PROJECT_PYTHON) di PROJECT_DIR.
Ingestion & dbt idempotent: task boleh di-retry dan DAG boleh di-backfill tanpa data dobel.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/opt/project")
PY = os.environ.get("PROJECT_PYTHON", "/opt/airflow/project-venv/bin/python")
RUN = f"cd {PROJECT_DIR} && {PY}"
TRACE = "--dag-id {{ dag.dag_id }} --task-id {{ task.task_id }} --try-number {{ ti.try_number }}"


def alert_on_failure(context) -> None:
    """Callback task gagal (setelah retry habis) -> alert lewat modul monitoring."""
    ti = context["ti"]
    subprocess.run(
        [PY, "-m", "monitoring", "alert", "--severity", "error", "--source", "airflow",
         "--title", f"Task Airflow gagal: {ti.dag_id}.{ti.task_id}",
         "--line", f"run: {ti.run_id}, percobaan ke-{ti.try_number}",
         "--line", f"log: {ti.log_url}",
         "--key", f"airflow:{ti.dag_id}:{ti.task_id}:{ti.run_id}"],
        cwd=PROJECT_DIR, check=False, timeout=120)


DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
    "on_failure_callback": alert_on_failure,
}
START = datetime(2026, 10, 1)


with DAG(
    dag_id="simulate_source_systems",
    description="Simulator: kirim data sistem sumber s/d kemarin (bukan bagian pipeline produksi)",
    schedule="0 5 * * *",
    start_date=START,
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULT_ARGS, "retries": 1},
    tags=["simulator"],
) as simulate:
    BashOperator(
        task_id="publish",
        bash_command=f"{RUN} -m simulators publish --until {{{{ macros.ds_add(ds, -1) }}}}",
    )


with DAG(
    dag_id="daily_commercial_pipeline",
    description="Ingestion SAP + distributor + POS -> dbt build (staging, marts, DQ, rekonsiliasi) -> alert",
    schedule="0 6 * * *",
    start_date=START,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["ingestion", "dbt", "monitoring"],
    doc_md=__doc__,
) as daily:
    migrate = BashOperator(task_id="migrate_warehouse", bash_command=f"{RUN} -m ingestion migrate")

    # Backfill: SAP diekstrak ulang untuk tanggal run tsb (dedup hash -> tidak ada baris dobel).
    sap_window = ("{% if dag_run.run_type == 'backfill' %}--start-date {{ ds }} --end-date {{ ds }}{% endif %}")
    extract_sap = BashOperator(task_id="extract_sap", bash_command=f"{RUN} -m ingestion {TRACE} sap {sap_window}")
    extract_dms = BashOperator(task_id="extract_dms", bash_command=f"{RUN} -m ingestion {TRACE} dms")
    extract_pos = BashOperator(task_id="extract_pos", bash_command=f"{RUN} -m ingestion {TRACE} pos")

    # Pool `dbt` (1 slot): dbt dari DAG mana pun berjalan bergiliran, tidak menulis tabel yang sama bersamaan.
    dbt_build = BashOperator(task_id="dbt_build", bash_command=f"{RUN} scripts/run_dbt.py build",
                             retries=1, pool="dbt")

    # Selalu jalan (juga bila task sebelumnya gagal) supaya masalah tetap dilaporkan.
    notify = BashOperator(task_id="notify", bash_command=f"{RUN} -m monitoring notify",
                          trigger_rule="all_done", on_failure_callback=None)

    migrate >> [extract_sap, extract_dms, extract_pos] >> dbt_build >> notify


with DAG(
    dag_id="weekly_reconcile",
    description="Re-extract penuh SAP (menangkap perubahan dokumen lama) + dbt full-refresh fakta incremental",
    schedule="0 3 * * 0",
    start_date=START,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["reconcile", "dbt"],
) as weekly:
    full_sap = BashOperator(task_id="sap_full_reextract",
                            bash_command=f"{RUN} -m ingestion {TRACE} sap --start-date 2000-01-01")
    full_refresh = BashOperator(task_id="dbt_full_refresh",
                                bash_command=f"{RUN} scripts/run_dbt.py build --full-refresh", retries=1,
                                pool="dbt")
    weekly_notify = BashOperator(task_id="notify", bash_command=f"{RUN} -m monitoring notify",
                                 trigger_rule="all_done", on_failure_callback=None)
    full_sap >> full_refresh >> weekly_notify


with DAG(
    dag_id="forecast_weekly",
    description="Backtest rolling-origin semua model, pilih terbaik, forecast 8 minggu (SKU x region)",
    schedule="0 8 * * 1",
    start_date=START,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["forecasting", "dbt"],
) as forecast_dag:
    # Fitur dari mart terbaru (pipeline harian 06:00 sudah selesai), lalu backtest + forecast.
    features = BashOperator(task_id="dbt_forecast_features", pool="dbt",
                            bash_command=f"{RUN} scripts/run_dbt.py build --select mart_forecast_features")
    train = BashOperator(task_id="train_backtest_forecast", bash_command=f"{RUN} -m forecasting.train_backtest")
    publish = BashOperator(task_id="dbt_forecast_marts", pool="dbt",
                           bash_command=f"{RUN} scripts/run_dbt.py build --select path:models/marts/forecast "
                                        "assert_forecast_sane")
    forecast_notify = BashOperator(task_id="notify", bash_command=f"{RUN} -m monitoring notify",
                                   trigger_rule="all_done", on_failure_callback=None)
    features >> train >> publish >> forecast_notify
