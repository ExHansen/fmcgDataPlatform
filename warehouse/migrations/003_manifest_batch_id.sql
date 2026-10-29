-- Migrasi 003.
-- 1) file_manifest.batch_id: menghubungkan baris raw (_batch_id) ke file & versinya,
--    supaya staging bisa memilih versi file terakhir per business_date.
alter table ops.file_manifest add column if not exists batch_id uuid;

-- Backfill: nama file di landing diawali 12 karakter pertama sha256 file tsb.
update ops.file_manifest m
set batch_id = r._batch_id
from (
    select distinct _batch_id, _source_system, _source_file from raw_dms.secondary_sales
    union all
    select distinct _batch_id, _source_system, _source_file from raw_pos.sellout
) r
where m.batch_id is null
  and m.status = 'LOADED'
  and r._source_system = m.source_system
  and split_part(regexp_replace(r._source_file, '^.*/', ''), '_', 1) = left(m.sha256, 12);

create unique index if not exists file_manifest_batch_id_idx on ops.file_manifest (batch_id) where batch_id is not null;

-- 2) unmapped_ids kini dibangun dbt dari data (bisa di-rebuild), bukan tabel yang diisi manual.
drop table if exists ops.unmapped_ids;
