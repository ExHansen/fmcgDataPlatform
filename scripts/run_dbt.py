"""Jalankan dbt dengan kredensial dari .env (dbt tidak membaca .env sendiri).

    python scripts/run_dbt.py deps
    python scripts/run_dbt.py build
    python scripts/run_dbt.py docs generate
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.common.settings import env  # noqa: E402


def main() -> int:
    for name in ("DWH_DB_HOST", "DWH_DB_PORT", "DWH_DB_NAME", "DWH_DB_USER", "DWH_DB_PASSWORD"):
        os.environ[name] = env(name)
    dbt = Path(sys.executable).with_name("dbt.exe" if os.name == "nt" else "dbt")
    cmd = [str(dbt), *sys.argv[1:], "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt")]
    return subprocess.call(cmd, cwd=ROOT / "dbt")


if __name__ == "__main__":
    raise SystemExit(main())
