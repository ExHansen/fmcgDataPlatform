# ADR 0004: Ambang DQ & rekonsiliasi dari profil data, alert tidak memblokir

Status: diterima (2026-10-26)

## Konteks
PLAN 2.5 memakai angka bulat: rekonsiliasi secondary vs sell-out ±10% dan anomali volume ±50%. Diterapkan apa adanya, keduanya menghasilkan banyak alarm palsu:
- Secondary normalnya +8% di atas sell-out (buffer stok toko).
- Volume file harian distributor wajar berada di 0,45×–2,1× median.

## Keputusan
- Ambang ditetapkan dari distribusi data aktual:
  - secondary vs sell-out: PASS −10%..+25%, FAIL di luar −20%..+40%.
  - Volume file: DMS 0,4×–2,5×, POS 0,6×–1,6×.
- Setiap ambang beserta alasannya didokumentasikan di [data_quality.md](../data_quality.md).
- Masalah data yang tidak membuat data salah (unknown member, file telat, volume) memakai severity dbt `warn` dan memicu alert, sehingga data tetap mengalir. Level alert-nya (warn/error) disimpan di `meta.alert_severity`.

## Konsekuensi
- Semua FAIL rekonsiliasi punya penyebab yang terbukti. File hilang (18/18) dan toko tidak lapor (12/12) tertangkap tanpa alarm palsu.
- Ambang perlu ditinjau ulang bila pola bisnis berubah, misalnya jadwal kirim atau jumlah toko.
