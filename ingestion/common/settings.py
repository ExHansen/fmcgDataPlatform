"""Kredensial & config ingestion (dari .env / environment, config YAML)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_PATH = ROOT / "ingestion" / "config" / "contracts.yaml"
MIGRATIONS_DIR = ROOT / "warehouse" / "migrations"


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str, default: str | None = None) -> str:
    _load_dotenv()
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Variabel {name} belum di-set (salin .env.example ke .env)")
    return value


@lru_cache
def contracts() -> dict:
    with CONTRACTS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
