# Kamus Data

Di-generate dari dbt oleh `scripts/gen_data_dictionary.py`. Jangan edit manual; ubah deskripsi di file `_*.yml` / komentar model lalu generate ulang. Lineage lengkap: `python scripts/run_dbt.py docs serve`.

## Schema `marts`

### `marts.dim_customer`

Distributor (sold-to SAP), SCD Type 2. customer_key '-1' = unknown member.

Materialisasi: `table` · Sumber: `models/marts/core/dim_customer.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `customer_key` | text | Surrogate key (hash customer_id + valid_from). |
| `customer_id` | text | Nomor customer SAP tanpa leading zero. |
| `sap_kunnr` | text |  |
| `distributor_code` | text | Kode distributor di file DMS (DIST_A/B/C). |
| `customer_name` | text |  |
| `customer_type` | text | DISTRIBUTOR / KEY_ACCOUNT / UNKNOWN. |
| `channel` | text |  |
| `region` | text | Wilayah layanan distributor. |
| `city` | text |  |
| `valid_from` | timestamp without time zone |  |
| `valid_to` | timestamp without time zone |  |
| `is_current` | boolean |  |

### `marts.dim_date`

1 baris per hari, 2025-2027. period_4w = kalender retail 13 periode x 4 minggu.

Materialisasi: `table` · Sumber: `models/marts/core/dim_date.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `date_key` | text | Kunci tanggal 'YYYYMMDD'. |
| `date_day` | date |  |
| `iso_year` | integer |  |
| `iso_week` | integer |  |
| `iso_year_week` | text |  |
| `week_start_date` | date | Senin awal minggu ISO. |
| `year` | integer |  |
| `quarter` | integer |  |
| `month` | integer |  |
| `year_month` | text |  |
| `month_start_date` | date |  |
| `iso_day_of_week` | integer |  |
| `day_name` | text |  |
| `period_4w` | text | Periode retail 4-mingguan, mis. '2026-P03'. |
| `is_weekend` | boolean |  |
| `event_name` | text | Nama libur nasional (hanya yang bertanggal tetap). |
| `is_holiday` | boolean |  |

### `marts.dim_product`

SKU (SCD Type 2 dari snapshot material SAP). product_key '-1' = unknown member.

Materialisasi: `table` · Sumber: `models/marts/core/dim_product.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `product_key` | text | Surrogate key (hash sku_id + valid_from). |
| `sku_id` | text | ID produk kanonik = nomor material SAP tanpa leading zero. |
| `sap_matnr` | text | Nomor material SAP asli (18 karakter, dengan leading zero). |
| `ean` | text | Barcode EAN-13. |
| `product_name` | text |  |
| `brand` | text | Brand (teks product hierarchy SAP). |
| `brand_code` | text |  |
| `category` | text | Kategori (teks material group SAP). |
| `category_code` | text |  |
| `base_uom` | text |  |
| `pcs_per_case` | integer | Isi per karton (dari konversi satuan SAP MARM). |
| `valid_from` | timestamp without time zone | Awal berlaku versi; versi pertama sejak 1900-01-01. |
| `valid_to` | timestamp without time zone | Akhir berlaku versi (eksklusif); versi berjalan = 9999-12-31. |
| `is_current` | boolean | True untuk versi yang berlaku sekarang. |

### `marts.dim_promotion`

Promosi terdeteksi dari harga POS (harga minggu ini < 90% harga tertinggi 8 minggu sebelumnya).

Materialisasi: `table` · Sumber: `models/marts/core/dim_promotion.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `promotion_key` | text | Surrogate key; '-1' = tanpa promo. |
| `promotion_id` | text |  |
| `crm_promotion_id` | text |  |
| `retailer_code` | text |  |
| `sku_id` | text |  |
| `promo_mechanic` | text |  |
| `discount_pct` | numeric | Penurunan harga vs harga tertinggi 8 minggu sebelumnya (%). |
| `start_date` | date |  |
| `end_date` | date |  |
| `source` | text | DETECTED (dari harga) / PLANNED (CRM, fase 2) / BOTH / NONE. |

### `marts.dim_store`

Toko fisik modern trade + distributor pelayannya. store_key '-1' = unknown member.

Materialisasi: `table` · Sumber: `models/marts/core/dim_store.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `store_key` | text | Surrogate key (hash store_id). |
| `store_id` | text | ID toko kanonik = kode toko retailer (berprefix kode retailer). |
| `retailer_store_code` | text |  |
| `retailer_code` | text |  |
| `retailer_name` | text |  |
| `store_format` | text | MINIMARKET / SUPERMARKET (dari master retailer). |
| `store_name` | text |  |
| `distributor_code` | text | Distributor yang paling banyak mengirim ke toko ini. |
| `distributor_key` | text | FK ke dim_customer (distributor pelayan). |
| `region` | text | Region distributor pelayan. |
| `first_sales_date` | date |  |

### `marts.dms_file_status`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/marts/recon/dms_file_status.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `distributor_code` | text |  |
| `business_date` | date |  |
| `status` | text |  |
| `versions` | bigint |  |
| `first_received_at` | timestamp with time zone |  |
| `days_late` | integer |  |

### `marts.fct_forecast`

Forecast mingguan per SKU x region per versi run; actual_units terisi setelah minggu target lewat.

Materialisasi: `table` · Sumber: `models/marts/forecast/fct_forecast.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `forecast_line_id` | text |  |
| `run_id` | text |  |
| `forecast_created_at` | timestamp with time zone |  |
| `is_latest_run` | boolean |  |
| `cutoff_week` | date |  |
| `target_date_key` | text |  |
| `target_week` | date |  |
| `horizon_week` | integer |  |
| `product_key` | text |  |
| `sku_id` | text |  |
| `region` | text |  |
| `model` | text |  |
| `model_role` | text |  |
| `forecast_units` | numeric |  |
| `actual_units` | numeric |  |

### `marts.fct_primary_sales`

Sell-in SAP, 1 baris = item sales order + delivery + invoice valid (fill rate = delivered / ordered).

Materialisasi: `table` · Sumber: `models/marts/commercial/fct_primary_sales.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `order_line_id` | text | Hash (no. sales order, no. item). |
| `date_key` | text |  |
| `order_date` | date |  |
| `product_key` | text | FK dim_product. |
| `customer_key` | text | FK dim_customer (distributor sold-to). |
| `sales_order_no` | text |  |
| `item_no` | text |  |
| `sales_uom` | text |  |
| `qty_ordered_pcs` | numeric | Qty dipesan (versi terakhir order) dalam PCS. |
| `qty_delivered_pcs` | numeric | Qty keluar gudang (goods issue) dalam PCS. |
| `qty_billed_pcs` | numeric | Qty di invoice valid (invoice batal & dokumen S1 tidak dihitung). |
| `order_net_value` | numeric |  |
| `billed_net_value` | numeric | Nilai invoice valid (IDR). |
| `is_rejected` | boolean |  |
| `rejection_reason` | text |  |
| `delivery_status` | text | OPEN (belum goods issue, dikecualikan dari fill rate) / DELIVERED / PARTIAL / NOT_DELIVERED (order dikirim tapi item ini tidak) / REJECTED.  |
| `is_changed_after_creation` | boolean |  |
| `has_cancelled_invoice` | boolean | Pernah ditagih dengan invoice yang kemudian dibatalkan (lalu ditagih ulang). |
| `delivery_no` | text |  |
| `goods_issue_date` | date |  |
| `billing_no` | text |  |
| `billing_date` | date |  |
| `order_to_goods_issue_days` | integer | Lead time order -> barang keluar gudang (hari). |

### `marts.fct_sales`

Sell-out POS, 1 baris = toko x produk x hari. Incremental delete+insert per tanggal, lookback 14 hari.

Materialisasi: `incremental` · Sumber: `models/marts/commercial/fct_sales.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `date_key` | text | Tanggal penjualan (FK dim_date). |
| `sales_date` | date |  |
| `product_key` | text | FK dim_product (versi SCD2 yang berlaku di tanggal penjualan). |
| `store_key` | text | FK dim_store. |
| `promotion_key` | text | FK dim_promotion; '-1' = tanpa promo. |
| `units_sold` | numeric | Unit terjual (tanpa retur). Additive. |
| `units_returned` | numeric | Unit retur (positif). Additive. |
| `gross_sales_value` | numeric | Nilai penjualan sebelum diskon (IDR). |
| `discount_value` | numeric | Diskon toko (IDR). |
| `net_sales_value` | numeric | Nilai penjualan bersih (IDR), tanpa retur. |
| `returned_value` | numeric | Nilai retur (IDR, positif). |
| `source_retailer` | text |  |
| `received_at` | timestamp with time zone |  |

### `marts.fct_shipment`

Secondary sales, 1 baris = baris invoice distributor -> toko. Incremental per tanggal invoice.

Materialisasi: `incremental` · Sumber: `models/marts/commercial/fct_shipment.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `shipment_line_id` | text | Hash (distributor, no. invoice, kode produk lokal). |
| `date_key` | text |  |
| `invoice_date` | date |  |
| `product_key` | text | FK dim_product; '-1' bila kode produk distributor belum ter-mapping. |
| `store_key` | text | FK dim_store. |
| `distributor_key` | text | FK dim_customer (distributor). |
| `distributor_code` | text |  |
| `invoice_no` | text |  |
| `source_product_code` | text | Kode produk lokal distributor (sebelum mapping). |
| `qty_reported` | numeric | Qty seperti di file (bisa karton). |
| `uom_reported` | text | PCS atau CASE. |
| `qty_pcs` | numeric | Qty dalam PCS (karton dikonversi via MARM); null bila karton & produk belum ter-mapping. |
| `gross_value` | numeric |  |
| `discount_value` | numeric |  |
| `net_value` | numeric | Nilai bersih invoice (IDR). |
| `received_date` | date | Tanggal file diterima principal (WIB). |
| `days_late` | integer | Hari antara tanggal invoice dan file diterima (normal 1 = D+1). |
| `file_version` | integer | Versi file (2+ = kiriman ulang yang menggantikan versi sebelumnya). |

### `marts.mart_distributor_scorecard`

Distributor x minggu - sell-in, secondary, sell-out, stok tersirat, weeks of cover, fill rate, kepatuhan file.

Materialisasi: `table` · Sumber: `models/marts/commercial/mart_distributor_scorecard.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `week_start_date` | date |  |
| `distributor_code` | text |  |
| `distributor_key` | text |  |
| `sell_in_pcs` | numeric | PCS keluar gudang principal ke distributor (goods issue SAP) minggu ini. |
| `sell_in_value` | numeric |  |
| `secondary_pcs` | numeric | PCS dikirim distributor ke toko minggu ini. |
| `secondary_value` | numeric |  |
| `sellout_pcs` | numeric | PCS terjual di toko yang dilayani distributor minggu ini. |
| `ordered_pcs` | numeric |  |
| `delivered_pcs` | numeric |  |
| `avg_days_late` | numeric |  |
| `files_received` | bigint |  |
| `files_missing` | bigint |  |
| `files_late` | bigint |  |
| `files_resent` | bigint |  |
| `fill_rate_pct` | numeric | Qty terkirim / qty dipesan untuk order minggu ini (order OPEN dikecualikan). |
| `implied_stock_pcs` | numeric | Kumulatif (sell-in - secondary) sejak awal data; stok awal tidak diketahui. |
| `weeks_of_cover` | numeric | Stok tersirat / rata-rata secondary 4 minggu terakhir. |

### `marts.mart_forecast_accuracy`

Metrik backtest (rolling-origin) per run x model x level.

Materialisasi: `table` · Sumber: `models/marts/forecast/mart_forecast_accuracy.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `run_id` | text |  |
| `forecast_created_at` | timestamp with time zone |  |
| `selected_model` | text |  |
| `model` | text |  |
| `is_selected` | boolean |  |
| `is_baseline` | boolean |  |
| `level` | text |  |
| `category` | text |  |
| `wape` | numeric |  |
| `forecast_accuracy_pct` | numeric |  |
| `bias` | numeric |  |
| `mae` | numeric |  |
| `actual_units` | numeric |  |
| `n_points` | integer |  |

### `marts.mart_forecast_features`

Input forecasting - SKU x region x minggu lengkap (unit, harga, promo, distribusi).

Materialisasi: `table` · Sumber: `models/marts/forecast/mart_forecast_features.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `week_start_date` | date |  |
| `sku_id` | text |  |
| `region` | text |  |
| `category` | text |  |
| `brand` | text |  |
| `units` | numeric |  |
| `net_sales` | numeric |  |
| `avg_price` | numeric |  |
| `stores_selling` | bigint |  |
| `promo_store_days` | bigint |  |
| `has_holiday` | boolean |  |
| `regular_price_8w` | numeric |  |
| `price_ratio` | numeric |  |
| `week_of_year` | integer |  |

### `marts.mart_sales_weekly`

Sell-out mingguan per toko x produk dengan atribut dimensi (siap dashboard).

Materialisasi: `table` · Sumber: `models/marts/commercial/mart_sales_weekly.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `week_start_date` | date |  |
| `iso_year_week` | text |  |
| `period_4w` | text |  |
| `store_key` | text |  |
| `store_id` | text |  |
| `retailer_name` | text |  |
| `store_format` | text |  |
| `region` | text |  |
| `distributor_code` | text |  |
| `product_key` | text |  |
| `sku_id` | text |  |
| `product_name` | text |  |
| `brand` | text |  |
| `category` | text |  |
| `units_sold` | numeric |  |
| `units_returned` | numeric |  |
| `net_sales_value` | numeric |  |
| `gross_sales_value` | numeric |  |
| `discount_value` | numeric |  |
| `promo_days` | bigint |  |

### `marts.pos_store_week_status`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/marts/recon/pos_store_week_status.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `store_id` | text |  |
| `week_start_date` | date |  |
| `status` | text |  |
| `lines` | bigint |  |
| `units` | numeric |  |

### `marts.recon_all`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/marts/recon/recon_all.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `check_name` | text |  |
| `period_start` | date |  |
| `period_end` | date |  |
| `dimension_key` | text |  |
| `source_value` | numeric |  |
| `target_value` | numeric |  |
| `diff_abs` | numeric |  |
| `diff_pct` | numeric |  |
| `threshold_pct` | numeric |  |
| `status` | text |  |

### `marts.recon_billing_vs_delivery`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/marts/recon/recon_billing_vs_delivery.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `check_name` | text |  |
| `period_start` | date |  |
| `period_end` | date |  |
| `dimension_key` | text |  |
| `source_value` | numeric |  |
| `target_value` | numeric |  |
| `diff_abs` | numeric |  |
| `diff_pct` | numeric |  |
| `threshold_pct` | numeric |  |
| `status` | text |  |

### `marts.recon_ingestion_files`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/marts/recon/recon_ingestion_files.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `check_name` | text |  |
| `period_start` | date |  |
| `period_end` | date |  |
| `dimension_key` | text |  |
| `source_value` | bigint |  |
| `target_value` | bigint |  |
| `diff_abs` | bigint |  |
| `diff_pct` | numeric |  |
| `threshold_pct` | numeric |  |
| `status` | text |  |

### `marts.recon_secondary_vs_sellout`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/marts/recon/recon_secondary_vs_sellout.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `check_name` | text |  |
| `period_start` | date |  |
| `period_end` | date |  |
| `dimension_key` | text |  |
| `source_value` | numeric |  |
| `target_value` | numeric |  |
| `diff_abs` | numeric |  |
| `diff_pct` | numeric |  |
| `threshold_pct` | numeric |  |
| `status` | text |  |

### `marts.recon_sellin_vs_secondary`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/marts/recon/recon_sellin_vs_secondary.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `check_name` | text |  |
| `period_start` | date |  |
| `period_end` | date |  |
| `dimension_key` | text |  |
| `source_value` | numeric |  |
| `target_value` | numeric |  |
| `diff_abs` | numeric |  |
| `diff_pct` | numeric |  |
| `threshold_pct` | numeric |  |
| `implied_stock_pcs` | numeric |  |
| `weeks_of_cover` | numeric |  |
| `status` | text |  |

## Schema `ops`

### `ops.id_mapping_coverage`

Persen nilai penjualan per sumber yang produk/toko/customer-nya sudah ter-mapping.

Materialisasi: `table` · Sumber: `models/ops/id_mapping_coverage.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `source_type` | text |  |
| `source_entity` | text |  |
| `entity_type` | text |  |
| `value_total` | numeric |  |
| `value_mapped` | numeric |  |
| `pct_value_mapped` | numeric |  |
| `threshold_pct` | integer |  |

### `ops.quarantine_records`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/ops/quarantine_records.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `source_model` | text |  |
| `record_id` | text |  |
| `source_entity` | text |  |
| `business_date` | date |  |
| `reason` | text |  |
| `details` | jsonb |  |

### `ops.source_freshness`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/ops/source_freshness.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `source_system` | text |  |
| `last_success_at` | timestamp with time zone |  |
| `last_business_date` | date |  |
| `hours_since_load` | numeric |  |
| `business_lag_days` | integer |  |
| `status` | text |  |

### `ops.unmapped_ids`

ID sumber yang belum punya padanan kanonik (daftar kerja tim MDM), dibangun ulang tiap run.

Materialisasi: `table` · Sumber: `models/ops/unmapped_ids.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `entity_type` | text |  |
| `source_system` | text |  |
| `source_id` | text |  |
| `source_description` | text |  |
| `first_seen` | date |  |
| `last_seen` | date |  |
| `occurrences` | bigint |  |

### `ops.volume_anomalies`

_(tanpa deskripsi)_

Materialisasi: `table` · Sumber: `models/ops/volume_anomalies.sql`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `source_system` | text |  |
| `business_date` | date |  |
| `file_path` | text |  |
| `received_at` | timestamp with time zone |  |
| `rows` | bigint |  |
| `baseline_rows` | numeric |  |
| `diff_pct` | numeric |  |
| `status` | text |  |
