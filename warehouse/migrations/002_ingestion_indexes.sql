-- Migrasi 002. Index untuk load idempotent.
-- raw_sap: baris yang hash-nya sudah ada tidak dimuat ulang (lookback tidak membuat duplikat),
-- sehingga raw_sap menjadi log perubahan: 1 baris per versi data sumber.
do $$
declare
    t text;
begin
    for t in select table_name from information_schema.tables where table_schema = 'raw_sap'
    loop
        execute format('create index if not exists %I on raw_sap.%I (_record_hash)', t || '_record_hash_idx', t);
    end loop;
end $$;

create index if not exists secondary_sales_source_file_idx on raw_dms.secondary_sales (_source_file);
create index if not exists sellout_source_file_idx on raw_pos.sellout (_source_file);
create index if not exists file_manifest_path_idx on ops.file_manifest (source_system, file_path, sha256);
create index if not exists pipeline_run_log_source_idx on ops.pipeline_run_log (source_system, started_at desc);
