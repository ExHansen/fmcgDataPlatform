"""Unduh dataset dunnhumby "The Complete Journey" dari paket R `completejourney` (GitHub).

    python scripts/download_data.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/bradleyboehmke/completejourney/raw/master/data/"
FILES = {"transactions.rds": 12_775_661, "products.rda": 869_019}
DEST = Path(__file__).resolve().parents[1] / "data" / "external" / "completejourney"


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for name, size in FILES.items():
        target = DEST / name
        if target.exists() and target.stat().st_size == size:
            print(f"ada: {target}")
            continue
        print(f"unduh {name} ...")
        urllib.request.urlretrieve(BASE + name, target)
        if target.stat().st_size != size:
            print(f"ukuran {name} tidak sesuai ({target.stat().st_size} != {size})", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
