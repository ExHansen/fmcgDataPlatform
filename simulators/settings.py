"""Memuat config simulator (YAML) dan kredensial koneksi (.env / environment)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "simulators" / "config" / "simulation.yaml"
SIM_DIR = ROOT / "data" / "sim"          # hasil generate (truth + outbox file)
TRUTH_DIR = SIM_DIR / "truth"
OUTBOX_DIR = SIM_DIR / "outbox"
STATE_PATH = SIM_DIR / "publish_state.json"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Parser .env sederhana; variabel environment yang sudah ada tidak ditimpa."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@lru_cache
def config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str) -> str:
    load_dotenv()
    try:
        return os.environ[name]
    except KeyError:
        raise RuntimeError(f"Variabel {name} belum di-set (salin .env.example ke .env)") from None
