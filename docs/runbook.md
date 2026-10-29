# Runbook: Alert Data Pipeline FMCG

Untuk engineer yang sedang piket. Setiap alert berisi satu ringkasan per run (task `notify`) atau satu alert per task yang gagal (callback Airflow).

Semua alert tercatat di `ops.alert_log`. Kalau `ALERT_WEBHOOK_URL` diisi, alert juga dikirim ke Discord/Slack.

**Aturan umum:**
- Ingestion dan dbt **idempotent**. Menjalankan ulang task atau DAG selalu aman dan tidak membuat data dobel.
- Masalah yang sama tidak di-alert ulang:
  - Rekonsiliasi gagal: sekali saja.
  - Tes dbt: paling cepat 7 hari sekali.
  - Sumber terlambat: paling cepat 1 hari sekali.

## Tempat melihat

| Apa | Di mana |
|---|---|
| Status DAG & log task | Airflow UI: http://localhost:8080 |
| Riwayat run (ingestion & dbt) | `select * from ops.pipeline_run_log order by started_at desc limit 50` |
| Tes dbt yang tidak lulus | `select * from ops.dq_results where status <> 'pass' order by executed_at desc` |
| Rekonsiliasi | `select * from ops.recon_results where run_id = '<run>' and status <> 'PASS'` |
| File masuk / ditolak | `select * from ops.file_manifest order by received_at desc` |
| ID belum ter-mapping | `select * from ops.unmapped_ids order by last_seen desc` |
| Kesegaran sumber | `select * from ops.source_freshness` |

## Task Airflow gagal (`Task Airflow gagal: <dag>.<task>`)

Task sudah di-retry 2x dengan backoff eksponensial sebelum alert ini muncul.

1. Buka link log di alert dan cari baris `ERROR`.
2. Tangani sesuai jenis error:
   - **Error koneksi** (`OperationalError`, `SSHException`, `EndpointConnectionError`):
     - Cek container: `docker compose ps`.
     - Nyalakan yang mati: `docker compose up -d <service>`.
     - Lalu *Clear* task di Airflow.
   - **`extract_*` gagal di sebagian objek:** objek lain tetap ter-load dan watermark objek yang gagal tidak maju. Cukup *Clear* task, maka extract akan melanjutkan dari watermark/manifest.
   - **`dbt_build` gagal:** cari model atau tes yang gagal di log. Tes severity `error` yang gagal menghentikan model hilir, sehingga dashboard tetap menampilkan data kemarin. Perbaiki penyebabnya, lalu *Clear*.
3. Jika task ternyata gagal karena bug, perbaiki kode lalu *Clear*. Karena idempotent, tidak perlu membersihkan data apa pun.

## Distributor tidak mengirim file (`dms_file_received`)

Arti alert: pada hari kirim yang biasa, tidak ada file dari distributor tersebut. Alert baru muncul setelah lewat D+4.

1. Cek apakah file ada di SFTP tapi ditolak:
   ```sql
   select * from ops.file_manifest where source_system = 'DMS_B' and status <> 'LOADED' order by received_at desc;
   ```
2. Jika file berstatus `REJECTED`, lihat bagian "File ditolak" di bawah.
3. Jika file memang tidak ada, hubungi distributor (kontak di master distributor) dan minta file tanggal tersebut.
4. Begitu file diunggah, run harian berikutnya otomatis memuatnya. Proses berbasis file, jadi tidak perlu backfill.
5. Sampai file datang, rekonsiliasi `secondary_vs_sellout` untuk toko yang dilayani distributor itu akan negatif. Ini wajar.

## Toko tidak ada di laporan POS (`pos_store_week_reported`)

1. Cek file mingguan retailer di bucket `retailer-drop` dan pastikan toko memang tidak ada di file.
2. Minta retailer mengirim ulang file minggu tersebut. File baru otomatis dimuat sebagai `version` berikutnya.
3. Rekonsiliasi `secondary_vs_sellout` toko itu akan positif besar sampai file koreksi datang.

## Kiriman distributor vs sell-out menyimpang (`secondary_vs_sellout` FAIL)

Normalnya secondary sekitar +8% di atas sell-out. FAIL berarti di luar −20% / +40%.

| Arah | Penyebab paling sering | Cek |
|---|---|---|
| Negatif (sell-out > kiriman) | File distributor hilang, atau produk/outlet distributor belum ter-mapping | `ops.dms_file_status` periode itu; `ops.unmapped_ids` untuk distributor toko tsb |
| Positif (kiriman ≫ sell-out) | Toko tidak lapor POS, atau mapping toko salah | `marts.pos_store_week_status`; `intermediate.int_store_xref` |

## Unknown member > 2% (`assert_unknown_member_share_over_2pct`)

Artinya kode produk atau toko baru muncul di data, tapi belum punya mapping.

1. Lihat daftarnya:
   ```sql
   select * from ops.unmapped_ids order by occurrences desc;
   ```
2. Untuk produk DIST_A, tim MDM menambahkan baris ke [dbt/seeds/dms_product_mapping.csv](../dbt/seeds/dms_product_mapping.csv) dengan kolom `distributor_code`, `local_product_code`, `sap_matnr`, `mapped_by`, `mapped_at`.
3. Jalankan `python scripts/run_dbt.py build`. Fakta incremental hanya memproses ulang 14 hari terakhir, jadi jalankan juga `python scripts/run_dbt.py build --full-refresh --select fct_shipment+` (atau tunggu `weekly_reconcile` hari Minggu) agar data lama ikut ter-mapping.

## File ditolak (`REJECTED` di `ops.file_manifest`)

1. Lihat alasannya:
   ```sql
   select file_path, reject_reason from ops.file_manifest where status = 'REJECTED';
   ```
2. Tangani sesuai alasan:
   - **Kolom wajib hilang / berganti nama (schema drift):** pastikan dengan distributor bahwa perubahannya disengaja. Lalu:
     1. Tambahkan alias di [ingestion/config/contracts.yaml](../ingestion/config/contracts.yaml) dan di `vars.dms_sources` pada [dbt_project.yml](../dbt/dbt_project.yml).
     2. Jalankan `python -m ingestion dms --distributors DIST_X --retry-rejected`.
   - **Nama file tidak sesuai pola, atau file rusak:** minta distributor mengirim ulang.

## Sumber terlambat (`<sumber> terlambat`)

| Sumber | WARN / ERROR |
|---|---|
| SAP | Extract sukses terakhir > 26 / 48 jam lalu |
| DMS_x | File terakhir untuk tanggal bisnis > 2 / 4 hari lalu |
| POS_x | File minggu terakhir > 15 / 22 hari lalu |

- **SAP:** cek task `extract_sap` di DAG harian dan koneksi ke SAP.
- **DMS/POS:** sumber belum mengirim. Tangani seperti alert file hilang di atas.

## Anomali volume file (`assert_recent_volume_normal`)

Arti alert: jumlah baris sebuah file jauh dari median pembanding (DMS di luar 0,4×–2,5×, POS di luar 0,6×–1,6×).

1. Bandingkan dengan file asli di lake (`landing/...` dari kolom `file_path`).
2. Kalau file terpotong, minta kirim ulang. Versi baru otomatis menggantikan versi lama di staging.
3. Kalau volume memang naik (promo, toko baru), tidak perlu tindakan.

## Backfill dan full-refresh

- **Backfill rentang tanggal:**
  ```bash
  docker compose exec airflow-scheduler airflow backfill create --dag-id daily_commercial_pipeline --from-date 2026-10-01 --to-date 2026-10-07
  ```
  Saat backfill, SAP diekstrak ulang untuk tanggal tersebut. Run idempotent, jadi tidak ada data dobel.
- **Membangun ulang fakta dari raw:** `python scripts/run_dbt.py build --full-refresh`. Ini juga dijalankan otomatis setiap Minggu oleh `weekly_reconcile`.
