"""Buat .env dari .env.example dengan secret acak (tidak menimpa .env yang sudah ada).

    python scripts/init_env.py
"""
from __future__ import annotations

import base64
import os
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    target = ROOT / ".env"
    if target.exists():
        print(".env sudah ada; tidak diubah")
        return 0
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    text = text.replace("change_me_fernet_32_byte_urlsafe_base64", base64.urlsafe_b64encode(os.urandom(32)).decode())
    # Password tanpa '-' / '_' supaya aman dipakai di URL koneksi & argumen command
    text = re.sub(r"change_me_\w+", lambda _: secrets.token_hex(16), text)
    target.write_text(text, encoding="utf-8")
    print(f".env dibuat: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
