from __future__ import annotations

import hashlib

import pandas as pd

SEP = "\x1f"
NULL = "\x00"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value) -> str:
    if value is None or (isinstance(value, float) and value != value):   # None / NaN
        return NULL
    return str(value)


def row_hashes(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """md5 dari kolom bisnis (null dibedakan dari string kosong).

    Dibangun dengan Python murni, bukan fillna: pandas 2.x membuang karakter NUL saat fillna,
    sehingga hash bisa berbeda antar versi pandas dan dedup raw_sap rusak.
    """
    joined = [SEP.join(_text(v) for v in row) for row in df[columns].itertuples(index=False, name=None)]
    return pd.Series([hashlib.md5(s.encode("utf-8")).hexdigest() for s in joined], index=df.index)
