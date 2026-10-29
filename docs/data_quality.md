# Data Quality & Rekonsiliasi

Dokumen ini menjelaskan cek kualitas data dan rekonsiliasi di platform, plus bukti bahwa masalah data yang sengaja disisipkan simulator benar-benar tertangkap.

Semua angka berasal dari data simulasi periode 2025-12-28 s/d 2026-10-26.

## Alur hasil cek

Setiap `dbt build` mencatat hasilnya ke schema `ops` lewat hook di [ops_logging.sql](../dbt/macros/ops_logging.sql):

| Tabel | Isi |
|---|---|
| `ops.pipeline_run_log` | 1 baris per invocation dbt (`source_system = 'DBT'`), berdampingan dengan run ingestion |
| `ops.dq_results` | 1 baris per tes dbt per run: status, jumlah baris gagal, severity alert |
| `ops.recon_results` | Isi `marts.recon_all` per run: 6 jenis cek, status PASS/WARN/FAIL |
| `ops.quarantine_records` | Baris yang tidak masuk / tidak lengkap di fakta, beserta alasannya |
| `ops.unmapped_ids` | Kode sumber yang belum punya ID kanonik (daftar kerja tim MDM) |

Halaman *Data Health* di dashboard (M6) membaca tabel-tabel ini. Alert (M5) dibuat oleh `python -m monitoring notify` dan dicatat di `ops.alert_log`; lihat [runbook.md](runbook.md).

## Katalog cek (PLAN 2.5)

| # | Cek | Implementasi | Status |
|---|---|---|---|
| 1 | Not null PK & FK | tes `not_null` di staging, intermediate, marts | ✅ |
| 2 | Unique PK / grain | `unique`, `dbt_utils.unique_combination_of_columns` | ✅ |
| 3 | Referential integrity + porsi unknown member | `relationships` ke semua dimensi; `assert_unknown_member_share_over_0_5pct` (alert warn) dan `..._over_2pct` (alert error). Keduanya severity dbt `warn`, jadi data tetap mengalir | ✅ |
| 4 | Freshness sumber | `ops.source_freshness` per distributor/retailer + tes `assert_sources_fresh` (SAP 26/48 jam sejak extract, DMS 2/4 hari, POS 15/22 hari sejak tanggal bisnis); juga `sources.freshness` dbt | ✅ |
| 5 | Range / accepted values + karantina | `accepted_range`, `accepted_values`; harga outlier POS → `ops.quarantine_records` | ✅ |
| 6 | Anomali volume file | `ops.volume_anomalies` + tes `assert_recent_volume_normal` (14 hari terakhir). Ambang dari profil data, bukan ±50% di draf PLAN: volume harian DMS wajar 0,45×–2,1× median (persentil 1–99) karena tergantung toko yang dikirimi hari itu → ambang DMS 0,4×–2,5×, POS 0,6×–1,6×. Hasil: 5 dari 827 file ditandai (0,6%) | ✅ (M5) |
| 7 | Schema check | Kontrak di ingestion: file REJECTED bila kolom wajib hilang ([contracts.yaml](../ingestion/config/contracts.yaml)) | ✅ (M2) |
| 8 | Rekonsiliasi ingestion: sumber vs raw | `recon_ingestion_files`: baris per file di manifest vs di raw | ✅ |
| 9 | Rekonsiliasi primary | `recon_billing_vs_delivery` (internal SAP) dan `recon_sellin_vs_secondary` (stok tersirat distributor) | ✅ |
| 10 | Rekonsiliasi secondary vs sell-out | `recon_secondary_vs_sellout` per toko × periode 4 minggu | ✅ |
| 11 | Internal vs syndicated | — | Fase 2 (syndicated di luar MVP) |
| 12 | Forecast sanity | `assert_forecast_sane`: total forecast mingguan model terpilih dalam ±50% rata-rata 8 minggu terakhir (alert warn) | ✅ (M6) |

## Masalah yang disisipkan → cek yang menangkap

Kolom "Bukti" divalidasi terhadap data kebenaran simulator (`data/sim/truth`) oleh [test_integration_marts.py](../tests/test_integration_marts.py) dan [test_integration_dbt.py](../tests/test_integration_dbt.py).

| Sumber | Masalah disisipkan | Ditangani / dideteksi di | Bukti |
|---|---|---|---|
| SAP | Leading zero `KUNNR`/`MATNR` | `strip_zeros` di staging; join ke DMS_B & seed distributor | 100% kode DMS_B ter-mapping lewat MATNR |
| SAP | Order diubah setelah dibuat (`AEDAT`) | Ingestion lookback 3 hari + dedup hash; staging ambil versi terbaru | 1.252 item `is_changed_after_creation` |
| SAP | Item direject (`ABGRU`) | `delivery_status = REJECTED`, dihitung di fill rate | Fill rate = kebenaran (selisih < 1e-9) |
| SAP | Delivery parsial | `delivery_status = PARTIAL / NOT_DELIVERED` | 1.514 baris parsial |
| SAP | Invoice dibatalkan + ditagih ulang | Invoice batal & S1 dikecualikan, rebill dihitung | `recon_billing_vs_delivery` 33/33 PASS |
| SAP | Satuan CS vs EA | `qty_base_uom` dari UMVKZ/UMVKN | Tes `delivered <= ordered` lulus |
| DMS | 3 format, desimal koma, 3 format tanggal | `vars.dms_sources` + macro parsing | Qty & nilai per hari = kebenaran |
| DMS | File telat 1–3 hari | `days_late`, cek `dms_file_received` WARN | 96 file WARN (telat > 1 hari) |
| DMS | File tidak pernah dikirim | `dms_file_status` + `dms_file_received` FAIL | **18/18 tertangkap, 0 alarm palsu** |
| DMS | File dikirim ulang (koreksi) | Versi file terakhir per tanggal | Qty & nilai per hari = kebenaran |
| DMS | UoM karton (KRT/CTN) | Konversi via MARM satuan CS | 1.080 baris karton terkonversi |
| DMS | Kolom DIST_C berganti nama (2026-06-01) | Alias di kontrak ingestion & `vars.dms_sources` | 7.583 baris DIST_C sesudah rename dimuat |
| DMS | Kode outlet/produk lokal | `int_store_xref`, `int_product_xref` (+ seed MDM) | 0 salah map dari 6.446 kode produk & 30 toko |
| DMS | Produk baru belum dipetakan MDM | `ops.unmapped_ids`, tes unknown member | 135 kode; WARN unknown 4–5% (Sep–Okt) |
| POS | EAN kehilangan leading zero | `lpad(ean, 13, '0')` | 3.350 EAN diperbaiki, 100% artikel ter-mapping |
| POS | Baris dobel | Dedup baris identik per file | 528 baris dibuang (53.680 → 53.152) |
| POS | Retur negatif | `is_return`, `units_returned` | 263 baris retur |
| POS | Harga outlier | `is_price_outlier` > 10× median → karantina | 47 baris di `ops.quarantine_records` |
| POS | Toko tidak lapor seminggu | `pos_store_week_status` + `pos_store_week_reported` FAIL | **12/12 tertangkap, 0 alarm palsu** |

## Ambang rekonsiliasi dan alasannya

**`secondary_vs_sellout`** (per toko × periode 4 minggu, PLAN #10):
- Secondary normalnya rata-rata **+8% di atas sell-out**, dengan simpangan baku ±12%. Distributor mengirim sedikit lebih banyak dari yang laku sebagai buffer stok toko.
- Karena itu ambang dipusatkan di +8%, bukan 0:
  - PASS: −10% s/d +25%
  - WARN: −20% s/d −10%, atau +25% s/d +40%
  - FAIL: di luar itu
- Hasil: 9 periode FAIL, dan **semuanya punya penyebab dari chaos**. Selisih +41% s/d +54% terjadi saat toko tidak lapor POS seminggu. Selisih −20% s/d −38% terjadi saat file distributor hilang tepat di hari kirim toko itu, ditambah produk yang belum ter-mapping pada satu kasus.

**`sellin_vs_secondary`** (per distributor × periode):
- Selisih sell-in dan secondary wajar karena stok distributor naik-turun. Yang dinilai adalah stok tersirat:
  - FAIL jika stok tersirat negatif (mustahil secara fisik, berarti data hilang/dobel).
  - WARN jika weeks of cover > 6.
- 24 dari 36 periode WARN. Ini temuan bisnis, bukan masalah data: sell-in 113–126% dari sell-out, sehingga stok menumpuk di distributor. Penyebabnya order dibulatkan ke karton untuk SKU yang lambat laku.

**`billing_vs_delivery`:**
- Qty goods issue harus sama dengan qty yang ditagih invoice valid. Toleransi 0,5% untuk delivery akhir bulan.

**`dms_file_received`:**
- Hari yang diharapkan dikirimi file adalah hari dalam minggu yang punya file di ≥ 50% minggu.
- Hari kirim baru dinilai setelah D+4, supaya file yang masih dalam perjalanan tidak dianggap hilang.

## Keterbatasan yang diketahui

- **Resend yang menimpa file lama tidak terlihat untuk data historis.** DIST_A dan DIST_C mengirim ulang dengan nama file yang sama. Data historis dipublikasikan sebelum ingestion pertama, jadi hanya versi akhirnya yang pernah terlihat. Resend sesudah ingestion berjalan akan tercatat sebagai `version` baru.
- **Fakta incremental hanya memproses ulang 14 hari terakhir.** Data yang terlambat lebih lama dari itu butuh `--full-refresh`, yang dijadwalkan mingguan di M5. Hasil incremental sudah diverifikasi identik dengan full-refresh (fingerprint MD5 sama).
- **Stok tersirat distributor dihitung dari nol di awal data**, karena stok awal tidak diketahui. Angka absolutnya relatif, tapi trennya tetap bermakna.
