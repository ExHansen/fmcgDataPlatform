{#
  Semua hasil rekonsiliasi & cek kelengkapan dalam satu format (= kolom ops.recon_results).
  Disalin ke ops.recon_results tiap run oleh hook on-run-end (macro save_recon_results).
#}
{%- set recon_cols = 'check_name, period_start, period_end, dimension_key, source_value, target_value, diff_abs, diff_pct, threshold_pct, status' -%}

select {{ recon_cols }} from {{ ref('recon_secondary_vs_sellout') }}
union all
select {{ recon_cols }} from {{ ref('recon_sellin_vs_secondary') }}
union all
select {{ recon_cols }} from {{ ref('recon_billing_vs_delivery') }}
union all
select {{ recon_cols }} from {{ ref('recon_ingestion_files') }}
union all
select 'dms_file_received', business_date, business_date, distributor_code, 1, case when status = 'MISSING' then 0 else 1 end,
       case when status = 'MISSING' then 1 else 0 end, null, null,
       case when status = 'MISSING' then 'FAIL' when days_late > 1 then 'WARN' else 'PASS' end
from {{ ref('dms_file_status') }}
union all
select 'pos_store_week_reported', week_start_date, week_start_date + 6, store_id, 1, case when status = 'MISSING' then 0 else 1 end,
       case when status = 'MISSING' then 1 else 0 end, null, null,
       case when status = 'MISSING' then 'FAIL' else 'PASS' end
from {{ ref('pos_store_week_status') }}
