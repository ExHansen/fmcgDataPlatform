-- Migrasi 005.
-- 1) Schema forecast: ditulis oleh forecasting/ (Python), dibaca dbt sebagai source.
create schema if not exists forecast;

create table if not exists forecast.forecast_runs (
    run_id          text primary key,
    created_at      timestamptz not null default now(),
    cutoff_week     date not null,          -- minggu lengkap terakhir yang dipakai training
    horizon_weeks   int not null,
    n_series        int not null,
    selected_model  text not null,
    selection_level text not null,
    params          jsonb
);

create table if not exists forecast.forecast_values (
    run_id          text not null references forecast.forecast_runs (run_id),
    sku_id          text not null,
    region          text not null,
    target_week     date not null,
    model           text not null,
    forecast_units  numeric not null,
    primary key (run_id, sku_id, region, target_week, model)
);

create table if not exists forecast.backtest_metrics (
    run_id          text not null references forecast.forecast_runs (run_id),
    model           text not null,
    level           text not null,          -- sku_region / category_region / total
    category        text,                   -- null = semua kategori
    wape            numeric,
    bias            numeric,
    mae             numeric,
    actual_units    numeric,
    n_points        int,
    primary key (run_id, model, level, category)
);

create table if not exists forecast.backtest_values (
    run_id          text not null references forecast.forecast_runs (run_id),
    model           text not null,
    cutoff_week     date not null,
    target_week     date not null,
    category        text not null,
    region          text not null,
    actual_units    numeric not null,
    forecast_units  numeric not null,
    primary key (run_id, model, cutoff_week, target_week, category, region)
);

-- 2) Role read-only untuk BI (Metabase): hanya marts, ops, forecast.
--    Password di-set oleh `python -m ingestion migrate` dari BI_READER_PASSWORD (.env).
--    Schema marts biasanya dibuat dbt; dibuat di sini juga supaya grant tidak gagal di warehouse baru.
create schema if not exists marts;
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'bi_reader') then
        create role bi_reader login;
    end if;
end $$;
grant usage on schema marts, ops, forecast to bi_reader;
grant select on all tables in schema marts, ops, forecast to bi_reader;
alter default privileges in schema marts grant select on tables to bi_reader;
alter default privileges in schema ops grant select on tables to bi_reader;
alter default privileges in schema forecast grant select on tables to bi_reader;
