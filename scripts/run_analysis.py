"""Compile dbt analyses lalu jalankan di warehouse dan cetak hasilnya.

    python scripts/run_analysis.py                 # semua analyses
    python scripts/run_analysis.py q3_fill_rate    # satu analysis
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.common.settings import env  # noqa: E402


def main() -> int:
    names = sys.argv[1:] or sorted(p.stem for p in (ROOT / "dbt" / "analyses").glob("*.sql"))
    select = " ".join(names) if sys.argv[1:] else "resource_type:analysis"
    rc = subprocess.call([sys.executable, str(ROOT / "scripts" / "run_dbt.py"), "compile", "--select", select, "--quiet"],
                         stdout=subprocess.DEVNULL)
    if rc:
        return rc
    compiled = ROOT / "dbt" / "target" / "compiled" / "fmcg_commercial" / "analyses"
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    with psycopg.connect(host=env("DWH_DB_HOST"), port=env("DWH_DB_PORT"), dbname=env("DWH_DB_NAME"),
                         user=env("DWH_DB_USER"), password=env("DWH_DB_PASSWORD")) as conn:
        for name in names:
            cur = conn.execute((compiled / f"{name}.sql").read_text(encoding="utf-8"))
            df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
            print(f"\n=== {name} ===\n{df.to_string(index=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
