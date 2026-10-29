"""Kumpulkan masalah dari run terakhir menjadi satu ringkasan alert (dengan dedup).

Dedup per alert_key:
  - recon FAIL (per cek x dimensi x periode): sekali saja; hanya periode yang berakhir <= 30 hari lalu
  - tes dbt WARN/FAIL: diingatkan ulang paling cepat 7 hari
  - sumber terlambat: diingatkan ulang paling cepat 1 hari
  - run pipeline FAILED (24 jam terakhir): sekali per run
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from monitoring.alerting import Alert

RECON_TEXT = {
    "dms_file_received": "Distributor {dim} tidak mengirim file tanggal {start}",
    "pos_store_week_reported": "Toko {dim} tidak ada di laporan POS minggu {start}",
    "secondary_vs_sellout": "Toko {dim} periode {start}: kiriman distributor vs sell-out {diff:+.1f}%",
    "sellin_vs_secondary": "Distributor {dim} periode {start}: stok tersirat negatif (sell-in {src:,.0f} vs secondary {tgt:,.0f})",
    "billing_vs_delivery": "Distributor {dim} bulan {start}: qty ditagih ≠ qty dikirim ({diff:+.2f}%)",
    "ingestion_file_rows": "File {dim}: {src:,.0f} baris di manifest, {tgt:,.0f} di raw",
}
SEVERITY_RANK = {"info": 0, "warn": 1, "error": 2}


@dataclass
class Issue:
    key: str
    severity: str
    line: str


def _not_alerted_since(conn: psycopg.Connection, keys: list[str], interval: str | None) -> set[str]:
    """Subset keys yang belum pernah di-alert (atau terakhir di-alert lebih lama dari interval)."""
    if not keys:
        return set()
    sql = "select distinct alert_key from ops.alert_log where alert_key = any(%s)"
    if interval:
        sql += f" and created_at > now() - interval '{interval}'"
    done = {r[0] for r in conn.execute(sql, (keys,))}
    return set(keys) - done


def latest_dbt_run(conn: psycopg.Connection) -> str | None:
    """Run dbt lengkap terakhir (yang menghasilkan rekonsiliasi); build parsial --select dilewati."""
    row = conn.execute("select l.run_id from ops.pipeline_run_log l where l.source_system = 'DBT' "
                       "and exists (select 1 from ops.recon_results r where r.run_id = l.run_id) "
                       "order by l.started_at desc limit 1").fetchone()
    return row[0] if row else None


def collect(conn: psycopg.Connection, run_id: str | None) -> list[Issue]:
    issues: list[Issue] = []

    # 1) task pipeline yang gagal 24 jam terakhir
    for rid, src, obj, err in conn.execute(
            "select run_id, source_system, object_name, error_message from ops.pipeline_run_log "
            "where status = 'FAILED' and started_at > now() - interval '24 hours' order by started_at"):
        issues.append(Issue(f"pipeline:{rid}", "error", f"Run {src}/{obj or '-'} gagal: {(err or '')[:160]}"))

    if run_id:
        # 2) tes dbt yang tidak lulus di run terakhir
        for test, model, sev, status, failed in conn.execute(
                "select test_name, model_name, severity, status, failed_rows from ops.dq_results "
                "where run_id = %s and status in ('warn', 'fail', 'error') order by severity desc, test_name", (run_id,)):
            issues.append(Issue(f"dq:{test}", sev if status == "warn" else "error",
                                f"Tes {test} ({model}): {failed} baris bermasalah [{status}]"))

        # 3) rekonsiliasi FAIL untuk periode baru-baru ini
        for check, dim, start, src, tgt, diff in conn.execute(
                "select check_name, dimension_key, period_start, source_value, target_value, diff_pct "
                "from ops.recon_results where run_id = %s and status = 'FAIL' "
                "and period_end >= (now() at time zone 'Asia/Jakarta')::date - 30 "
                "order by check_name, period_start", (run_id,)):
            text = RECON_TEXT.get(check, check + " {dim} {start}").format(
                dim=dim, start=start, src=float(src or 0), tgt=float(tgt or 0), diff=float(diff or 0))
            issues.append(Issue(f"recon:{check}:{dim}:{start}", "error", text))

    # 4) sumber terlambat
    for src, last_bd, lag, hours, status in conn.execute(
            "select source_system, last_business_date, business_lag_days, hours_since_load, status "
            "from ops.source_freshness where status <> 'OK' order by source_system"):
        detail = f"data bisnis terakhir {last_bd} ({lag} hari lalu)" if last_bd else f"extract terakhir {hours} jam lalu"
        issues.append(Issue(f"freshness:{src}:{status}", "error" if status == "ERROR" else "warn",
                            f"{src} terlambat: {detail}"))
    return issues


def dedup(conn: psycopg.Connection, issues: list[Issue]) -> list[Issue]:
    def fresh(prefix: str, interval: str | None) -> set[str]:
        return _not_alerted_since(conn, [i.key for i in issues if i.key.startswith(prefix)], interval)

    allowed = (fresh("pipeline:", None) | fresh("recon:", None) | fresh("dq:", "7 days")
               | fresh("freshness:", "1 day"))
    return [i for i in issues if i.key in allowed]


def build_alert(issues: list[Issue], run_id: str | None) -> Alert | None:
    if not issues:
        return None
    severity = max((i.severity for i in issues), key=SEVERITY_RANK.__getitem__)
    counts = {s: sum(i.severity == s for i in issues) for s in ("error", "warn")}
    title = f"Data pipeline FMCG: {counts['error']} error, {counts['warn']} warning"
    ordered = sorted(issues, key=lambda i: -SEVERITY_RANK[i.severity])
    return Alert(severity=severity, source="monitoring", title=title, lines=[i.line for i in ordered],
                 alert_keys=[i.key for i in ordered], run_id=run_id)
