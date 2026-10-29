-- Migrasi 004. Log alert: setiap alert dicatat di sini (dan dikirim ke webhook bila dikonfigurasi).
-- alert_key dipakai untuk dedup: masalah yang sama tidak di-alert ulang setiap hari.
create table if not exists ops.alert_log (
    alert_id      text primary key,
    created_at    timestamptz not null default now(),
    severity      text not null check (severity in ('info', 'warn', 'error')),
    source        text not null,          -- dq / recon / freshness / pipeline / airflow
    alert_key     text not null,
    title         text not null,
    message       text,
    run_id        text,
    channel       text not null,          -- log / webhook
    delivered     boolean not null,
    delivery_error text
);
create index if not exists alert_log_key_idx on ops.alert_log (alert_key, created_at desc);
