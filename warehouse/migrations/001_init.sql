-- Migrasi 001. Schema warehouse. Layer raw: semua kolom bisnis text, append-only, + metadata standar.
-- staging / intermediate / marts dibuat oleh dbt (Milestone 3-4).

create schema if not exists raw_sap;
create schema if not exists raw_dms;
create schema if not exists raw_pos;
create schema if not exists ops;

-- ---------- raw_sap: kolom SAP asli (text) + metadata ----------
do $$
declare
    t record;
begin
    for t in select * from (values
        ('kna1',  'mandt, kunnr, name1, land1, regio, ort01, stras, ktokd, erdat'),
        ('knvv',  'mandt, kunnr, vkorg, vtweg, spart, kdgrp, erdat'),
        ('mara',  'mandt, matnr, mtart, matkl, prdha, meins, ean11, brgew, gewei, ersda, laeda, lvorm'),
        ('makt',  'mandt, matnr, spras, maktx'),
        ('marm',  'mandt, matnr, meinh, umrez, umren, ean11'),
        ('t023t', 'mandt, spras, matkl, wgbez, wgbez60'),
        ('t179t', 'mandt, spras, prodh, vtext'),
        ('vbak',  'mandt, vbeln, auart, audat, erdat, erzet, aedat, vkorg, vtweg, spart, kunnr, bstnk, netwr, waerk'),
        ('vbap',  'mandt, vbeln, posnr, matnr, arktx, kwmeng, vrkme, meins, umvkz, umvkn, netwr, waerk, werks, abgru, erdat, aedat'),
        ('vbep',  'mandt, vbeln, posnr, etenr, edatu, wmeng, bmeng'),
        ('likp',  'mandt, vbeln, lfart, erdat, erzet, aedat, vstel, kunnr, lfdat, wadat, wadat_ist'),
        ('lips',  'mandt, vbeln, posnr, matnr, lfimg, vrkme, meins, umvkz, umvkn, werks, vgbel, vgpos, erdat'),
        ('vbrk',  'mandt, vbeln, fkart, fkdat, erdat, erzet, aedat, vkorg, vtweg, kunag, kunrg, netwr, waerk, fksto, sfakn'),
        ('vbrp',  'mandt, vbeln, posnr, matnr, arktx, fkimg, vrkme, meins, umvkz, umvkn, netwr, aubel, aupos, vgbel, vgpos, werks, erdat'),
        ('vbfa',  'mandt, vbelv, posnv, vbeln, posnn, vbtyp_n, rfmng, erdat')
    ) as v(tbl, cols)
    loop
        execute format(
            'create table if not exists raw_sap.%I (%s, '
            '_batch_id uuid not null, _source_system text not null, _source_file text, '
            '_ingested_at timestamptz not null default now(), _record_hash text not null)',
            t.tbl,
            (select string_agg(trim(c) || ' text', ', ') from unnest(string_to_array(t.cols, ',')) c)
        );
    end loop;
end $$;

-- ---------- raw_dms: kolom asli file distributor disimpan utuh di jsonb ----------
create table if not exists raw_dms.secondary_sales (
    distributor_code text not null,
    source_row_number int not null,
    payload jsonb not null,
    _batch_id uuid not null,
    _source_system text not null,
    _source_file text not null,
    _ingested_at timestamptz not null default now(),
    _record_hash text not null
);

-- ---------- raw_pos ----------
create table if not exists raw_pos.sellout (
    retailer_code text not null,
    source_row_number int not null,
    payload jsonb not null,
    _batch_id uuid not null,
    _source_system text not null,
    _source_file text not null,
    _ingested_at timestamptz not null default now(),
    _record_hash text not null
);

-- ---------- ops ----------
create table if not exists ops.pipeline_run_log (
    run_id             text primary key,
    dag_id             text,
    task_id            text,
    source_system      text not null,
    object_name        text,
    started_at         timestamptz not null,
    ended_at           timestamptz,
    status             text not null check (status in ('RUNNING', 'SUCCESS', 'FAILED', 'SKIPPED')),
    rows_extracted     bigint,
    rows_loaded        bigint,
    watermark_from     text,
    watermark_to       text,
    error_message      text,
    airflow_try_number int
);

create table if not exists ops.file_manifest (
    file_id        text primary key,
    run_id         text references ops.pipeline_run_log (run_id),
    source_system  text not null,
    file_path      text not null,
    file_size      bigint not null,
    sha256         text not null,
    received_at    timestamptz not null,
    business_date  date,
    version        int not null default 1,
    status         text not null check (status in ('LOADED', 'DUPLICATE', 'REJECTED')),
    rows           bigint,
    reject_reason  text
);
create unique index if not exists file_manifest_loaded_hash
    on ops.file_manifest (source_system, sha256) where status = 'LOADED';

create table if not exists ops.ingestion_watermark (
    source_system   text not null,
    object_name     text not null,
    last_watermark  text,
    last_cursor     text,
    updated_at      timestamptz not null default now(),
    primary key (source_system, object_name)
);

create table if not exists ops.dq_results (
    dq_result_id  text primary key,
    run_id        text references ops.pipeline_run_log (run_id),
    executed_at   timestamptz not null,
    model_name    text,
    test_name     text not null,
    test_type     text,
    severity      text check (severity in ('warn', 'error')),
    failed_rows   bigint,
    threshold     text,
    status        text not null
);

create table if not exists ops.recon_results (
    recon_id       text primary key,
    run_id         text references ops.pipeline_run_log (run_id),
    check_name     text not null,
    period_start   date,
    period_end     date,
    dimension_key  text,
    source_value   numeric,
    target_value   numeric,
    diff_abs       numeric,
    diff_pct       numeric,
    threshold_pct  numeric,
    status         text not null check (status in ('PASS', 'WARN', 'FAIL'))
);

create table if not exists ops.unmapped_ids (
    entity_type    text not null,
    source_system  text not null,
    source_id      text not null,
    first_seen     date not null,
    last_seen      date not null,
    occurrences    bigint not null,
    primary key (entity_type, source_system, source_id)
);
