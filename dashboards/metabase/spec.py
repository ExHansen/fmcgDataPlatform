"""Spesifikasi dashboard Metabase (dashboard as code). Grid Metabase lebar 24 kolom.

Setiap kartu: native SQL ke warehouse (role read-only bi_reader: schema marts, ops, forecast).
Nomor di judul = nomor pertanyaan bisnis PLAN 2.7.
"""
from __future__ import annotations

LAST_4W = "sales_date > (select max(sales_date) - 28 from marts.fct_sales)"
# Hanya minggu lengkap di semua sumber (minggu pertama data parsial; file POS minggu berjalan belum datang)
COMPLETE_WEEKS = ("week_start_date between (select min(week_start_date) from marts.mart_forecast_features) "
                  "and (select max(week_start_date) from marts.mart_forecast_features)")


def card(name, sql, display="table", row=0, col=0, w=12, h=6, dims=None, metrics=None, stacked=False, **viz):
    settings = dict(viz)
    if dims:
        settings["graph.dimensions"] = dims
    if metrics:
        settings["graph.metrics"] = metrics
    if stacked:
        settings["stackable.stack_type"] = "stacked"
    return {"name": name, "sql": sql.strip(), "display": display, "row": row, "col": col, "w": w, "h": h,
            "viz": settings}


DASHBOARDS = [
    {
        "name": "1. Ringkasan Komersial (sell-out)",
        "description": "Sell-out POS: tren, region, SKU teratas, distribusi, dan dampak promo (PLAN 2.7 #1, #4, #6).",
        "cards": [
            card("Net sales 4 minggu terakhir (juta IDR)",
                 f"select round(sum(net_sales_value) / 1e6, 1) as net_sales from marts.fct_sales where {LAST_4W}",
                 "scalar", 0, 0, 6, 3),
            card("Unit terjual 4 minggu terakhir",
                 f"select sum(units_sold) as units from marts.fct_sales where {LAST_4W}", "scalar", 0, 6, 6, 3),
            card("Pertumbuhan vs 4 minggu sebelumnya (%)", """
with m as (select max(sales_date) as d from marts.fct_sales)
select round(100.0 * (sum(net_sales_value) filter (where sales_date > m.d - 28)
       / nullif(sum(net_sales_value) filter (where sales_date <= m.d - 28 and sales_date > m.d - 56), 0) - 1), 1) as growth_pct
from marts.fct_sales, m""", "scalar", 0, 12, 6, 3),
            card("Toko yang melapor (4 minggu)",
                 f"select count(distinct store_key) as stores from marts.fct_sales where {LAST_4W}", "scalar", 0, 18, 6, 3),
            card("#1 Net sales mingguan per brand (juta IDR)", f"""
select week_start_date as minggu, brand, round(sum(net_sales_value) / 1e6, 2) as net_sales
from marts.mart_sales_weekly where {COMPLETE_WEEKS} group by 1, 2 order by 1""", "line", 3, 0, 16, 8, ["minggu", "brand"], ["net_sales"]),
            card("Net sales 4 minggu per region (juta IDR)", """
select region, store_format, round(sum(net_sales_value) / 1e6, 1) as net_sales
from marts.mart_sales_weekly
where week_start_date > (select max(week_start_date) - 28 from marts.mart_sales_weekly)
group by 1, 2 order by 1""", "bar", 3, 16, 8, 8, ["region", "store_format"], ["net_sales"], stacked=True),
            card("#6 SKU teratas 4 minggu & numeric distribution", f"""
with last4 as (select * from marts.fct_sales where {LAST_4W} and units_sold > 0),
active as (select count(distinct store_key) as n from last4)
select p.brand, p.sku_id, p.product_name, sum(l.units_sold) as unit_4_minggu,
       round(100.0 * count(distinct l.store_key) / (select n from active), 1) as numeric_distribution_pct
from last4 l join marts.dim_product p using (product_key)
group by 1, 2, 3 order by unit_4_minggu desc limit 15""", "table", 11, 0, 14, 8),
            card("#4 Uplift penjualan saat promo per brand (%)", """
with daily as (
  select f.store_key, f.product_key, p.brand, f.promotion_key <> '-1' as on_promo, f.units_sold
  from marts.fct_sales f join marts.dim_product p using (product_key)),
pairs as (
  select store_key, product_key, brand,
         avg(units_sold) filter (where on_promo) as promo_units,
         avg(units_sold) filter (where not on_promo) as base_units
  from daily group by 1, 2, 3
  having count(*) filter (where on_promo) >= 2 and count(*) filter (where not on_promo) >= 5)
select brand, round(100.0 * (sum(promo_units) / sum(base_units) - 1), 1) as uplift_pct
from pairs group by 1 order by 2 desc""", "bar", 11, 14, 10, 8, ["brand"], ["uplift_pct"]),
        ],
    },
    {
        "name": "2. Sell-in, Sell-out & Distributor",
        "description": "Sell-in SAP vs secondary vs sell-out, stok distributor, fill rate, kepatuhan data (PLAN 2.7 #2, #3, #7).",
        "cards": [
            card("#2 Sell-in vs secondary vs sell-out (pcs per minggu)", f"""
select week_start_date as minggu, sum(sell_in_pcs) as "Sell-in (SAP)",
       sum(secondary_pcs) as "Secondary (distributor)", sum(sellout_pcs) as "Sell-out (POS)"
from marts.mart_distributor_scorecard where {COMPLETE_WEEKS} group by 1 order by 1""", "line", 0, 0, 16, 8, ["minggu"],
                 ["Sell-in (SAP)", "Secondary (distributor)", "Sell-out (POS)"]),
            card("Ringkasan distributor (13 minggu terakhir)", """
with recent as (
  select * from marts.mart_distributor_scorecard
  where week_start_date >= (select max(week_start_date) - 91 from marts.mart_distributor_scorecard)
    and week_start_date < (select max(week_start_date) from marts.mart_distributor_scorecard))
select distributor_code as distributor,
       round(100.0 * sum(sell_in_pcs) / nullif(sum(sellout_pcs), 0), 1) as "sell-in/sell-out %",
       (array_agg(weeks_of_cover order by week_start_date desc))[1] as "weeks of cover",
       round(100.0 * sum(delivered_pcs) / nullif(sum(ordered_pcs), 0), 1) as "fill rate %"
from recent group by 1 order by 1""", "table", 0, 16, 8, 8),
            card("Weeks of cover distributor (stok tersirat / rata-rata kiriman 4 minggu)", """
select week_start_date as minggu, distributor_code as distributor, weeks_of_cover
from marts.mart_distributor_scorecard where weeks_of_cover is not null order by 1""",
                 "line", 8, 0, 12, 7, ["minggu", "distributor"], ["weeks_of_cover"]),
            card("#3 Fill rate per bulan (%)", """
select to_char(f.order_date, 'YYYY-MM') as bulan, c.distributor_code as distributor,
       round(100.0 * sum(f.qty_delivered_pcs) / nullif(sum(f.qty_ordered_pcs), 0), 1) as fill_rate_pct
from marts.fct_primary_sales f join marts.dim_customer c using (customer_key)
where f.delivery_status <> 'OPEN' group by 1, 2 order by 1""", "bar", 8, 12, 12, 7, ["bulan", "distributor"],
                 ["fill_rate_pct"]),
            card("#7 Kepatuhan kirim data distributor", """
select distributor_code as distributor, count(*) as file_diharapkan,
       count(*) filter (where status = 'MISSING') as file_hilang,
       count(*) filter (where days_late > 1) as file_telat,
       count(*) filter (where versions > 1) as file_dikirim_ulang,
       round(avg(days_late), 2) as rata2_hari_telat,
       round(100.0 * count(*) filter (where status = 'RECEIVED' and days_late <= 1) / count(*), 1) as tepat_waktu_pct
from marts.dms_file_status group by 1 order by 1""", "table", 15, 0, 24, 5),
        ],
    },
    {
        "name": "3. Forecast Permintaan",
        "description": "Forecast mingguan 8 minggu (SKU x region), akurasi backtest per model (PLAN 2.7 #8, PLAN 2.8).",
        "cards": [
            card("Aktual vs forecast (unit per minggu, total)", """
with latest as (select run_id from forecast.forecast_runs order by created_at desc limit 1)
select week_start_date as minggu, 'Aktual' as seri, sum(units) as unit
from marts.mart_forecast_features group by 1
union all
select f.target_week, case when f.model_role = 'SELECTED' then 'Forecast ' || f.model else 'Baseline ' || f.model end,
       round(sum(f.forecast_units))
from marts.fct_forecast f join latest using (run_id) group by 1, 2
order by 1""", "line", 0, 0, 16, 8, ["minggu", "seri"], ["unit"]),
            card("Akurasi backtest per model, kategori x region (1 - WAPE, %)", """
select model, forecast_accuracy_pct
from marts.mart_forecast_accuracy
where level = 'category_region' and category = 'ALL'
  and run_id = (select run_id from forecast.forecast_runs order by created_at desc limit 1)
order by forecast_accuracy_pct desc""", "bar", 0, 16, 8, 8, ["model"], ["forecast_accuracy_pct"]),
            card("Backtest model terpilih: aktual vs forecast (horizon 1-4 minggu)", """
with r as (select run_id, selected_model from forecast.forecast_runs order by created_at desc limit 1)
select b.target_week as minggu, sum(b.actual_units) as aktual, round(sum(b.forecast_units)) as forecast
from forecast.backtest_values b join r on r.run_id = b.run_id and r.selected_model = b.model
where b.target_week < b.cutoff_week + 28
group by 1 order by 1""", "line", 8, 0, 12, 7, ["minggu"], ["aktual", "forecast"]),
            card("Akurasi & bias per level", """
select model, level, forecast_accuracy_pct as akurasi_pct, round(bias * 100, 1) as bias_pct, is_selected as terpilih
from marts.mart_forecast_accuracy
where category = 'ALL' and run_id = (select run_id from forecast.forecast_runs order by created_at desc limit 1)
order by level, akurasi_pct desc""", "table", 8, 12, 12, 7),
            card("Forecast 8 minggu ke depan per kategori (model terpilih)", """
with latest as (select run_id from forecast.forecast_runs order by created_at desc limit 1),
recent as (
  select category, sum(units) / 8.0 as avg_units
  from marts.mart_forecast_features
  where week_start_date > (select max(week_start_date) - 56 from marts.mart_forecast_features)
  group by 1)
select p.category, round(sum(f.forecast_units)) as forecast_8_minggu,
       round(max(r.avg_units) * 8) as aktual_8_minggu_terakhir
from marts.fct_forecast f join latest using (run_id)
join marts.dim_product p using (product_key)
left join recent r on r.category = p.category
where f.model_role = 'SELECTED'
group by 1 order by 2 desc limit 20""", "table", 15, 0, 24, 7),
        ],
    },
    {
        "name": "4. Data Health",
        "description": "Apakah data hari ini bisa dipercaya? Run pipeline, kesegaran, DQ, rekonsiliasi, ID belum ter-mapping (PLAN 2.7 #9).",
        "cards": [
            card("Run terakhir per sumber", """
select distinct on (source_system, object_name) source_system as sumber, coalesce(object_name, '-') as objek,
       status, ended_at as selesai, rows_loaded as baris_dimuat, dag_id
from ops.pipeline_run_log
order by source_system, object_name, started_at desc""", "table", 0, 0, 12, 8),
            card("Kesegaran sumber", """
select source_system as sumber, status, last_business_date as data_bisnis_terakhir,
       business_lag_days as lag_hari, hours_since_load as jam_sejak_load
from ops.source_freshness order by status desc, source_system""", "table", 0, 12, 12, 8),
            card("Rekonsiliasi run dbt terakhir", """
with last_run as (
  select l.run_id from ops.pipeline_run_log l
  where l.source_system = 'DBT' and exists (select 1 from ops.recon_results r where r.run_id = l.run_id)
  order by l.started_at desc limit 1)
select check_name as cek, status, count(*) as jumlah
from ops.recon_results join last_run using (run_id) group by 1, 2 order by 1""",
                 "bar", 8, 0, 12, 7, ["cek", "status"], ["jumlah"], stacked=True),
            card("ID belum ter-mapping", "select count(*) as unmapped_ids from ops.unmapped_ids", "scalar", 8, 12, 4, 3),
            card("Tes DQ tidak lulus (hasil terakhir per tes)", """
with latest as (
  select distinct on (test_name) test_name, model_name, severity, status, failed_rows, executed_at
  from ops.dq_results order by test_name, executed_at desc)
select test_name as tes, model_name as model, severity as level_alert, status, failed_rows as baris_gagal,
       executed_at as dijalankan
from latest where status <> 'pass' order by severity desc""", "table", 8, 16, 8, 7),
            card("Baris dikarantina", """
select reason as alasan, count(*) as jumlah from ops.quarantine_records group by 1""", "table", 11, 12, 4, 4),
            card("Masalah rekonsiliasi 60 hari terakhir (FAIL)", """
with last_run as (
  select l.run_id from ops.pipeline_run_log l
  where l.source_system = 'DBT' and exists (select 1 from ops.recon_results r where r.run_id = l.run_id)
  order by l.started_at desc limit 1)
select check_name as cek, dimension_key as dimensi, period_start as periode, diff_pct as selisih_pct
from ops.recon_results join last_run using (run_id)
where status = 'FAIL' and period_end >= current_date - 60 order by period_start desc""", "table", 15, 0, 12, 7),
            card("Alert terbaru", """
select date_trunc('second', created_at) as waktu, severity, title as judul, count(*) as jumlah_masalah,
       channel, bool_and(delivered) as terkirim
from ops.alert_log group by 1, 2, 3, 5 order by 1 desc limit 20""", "table", 15, 12, 12, 7),
        ],
    },
]
