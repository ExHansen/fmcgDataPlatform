"""Terapkan warehouse/migrations/*.sql yang belum tercatat di ops.schema_migrations (urut nama)."""
from __future__ import annotations

import logging

import psycopg
import psycopg.sql

from ingestion.common.connections import dwh_connect
from ingestion.common.settings import MIGRATIONS_DIR, env

log = logging.getLogger(__name__)


def migrate() -> list[str]:
    applied_now = []
    with dwh_connect() as conn:
        conn.execute("create schema if not exists ops")
        conn.execute("create table if not exists ops.schema_migrations "
                     "(version text primary key, applied_at timestamptz not null default now())")
        done = {r[0] for r in conn.execute("select version from ops.schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in done:
                continue
            log.info("menerapkan migrasi %s", path.name)
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("insert into ops.schema_migrations (version) values (%s)", (path.stem,))
            applied_now.append(path.stem)
        # Password role BI dari .env (tidak disimpan di file SQL); idempotent.
        bi_password = env("BI_READER_PASSWORD", "")
        if bi_password and conn.execute("select 1 from pg_roles where rolname = 'bi_reader'").fetchone():
            conn.execute(psycopg.sql.SQL("alter role bi_reader password {}").format(psycopg.sql.Literal(bi_password)))
        conn.commit()
    return applied_now
