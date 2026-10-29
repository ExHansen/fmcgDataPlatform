"""Data lake (S3): landing/ = file asli immutable, raw/ = hasil ekstraksi dalam Parquet."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
from botocore.exceptions import ClientError

from ingestion.common.connections import s3_client
from ingestion.common.retry import retry
from ingestion.common.settings import env


class Lake:
    def __init__(self):
        self.s3 = s3_client()
        self.bucket = env("S3_LAKE_BUCKET")
        try:
            self.s3.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.s3.create_bucket(Bucket=self.bucket)

    @retry((ClientError, OSError))
    def put(self, key: str, body: bytes, metadata: dict[str, str] | None = None) -> str:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body, Metadata=metadata or {})
        return f"s3://{self.bucket}/{key}"

    def put_landing(self, source: str, received: date, name: str, sha256: str, body: bytes) -> str:
        # Nama memuat potongan hash: file kiriman ulang dengan nama sama tidak menimpa versi lama.
        return self.put(f"landing/{source}/received_date={received:%Y-%m-%d}/{sha256[:12]}_{name}", body)

    def put_raw(self, source: str, obj: str, batch_id: str, df: pd.DataFrame) -> str:
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return self.put(f"raw/{source}/{obj}/ingest_date={date.today():%Y-%m-%d}/{batch_id}.parquet", buf.getvalue())
