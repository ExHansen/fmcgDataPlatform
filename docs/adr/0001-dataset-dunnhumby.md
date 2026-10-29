# ADR 0001: Dataset dasar dunnhumby "The Complete Journey"

Status: diterima (2026-10-23)

## Konteks
PLAN merekomendasikan M5 (Walmart). Dataset itu butuh akun Kaggle dan persetujuan aturan kompetisi, sehingga setup project tidak bisa dijalankan dari nol tanpa langkah manual.

## Keputusan
Memakai dunnhumby *The Complete Journey* dari paket R `completejourney` (lisensi CC0), yang bisa diunduh langsung dari GitHub. Yang dipakai hanya `transactions` dan `products`; file `promotions` (20 juta baris) tidak dipakai karena tidak dibutuhkan di MVP dan memorinya terlalu besar.

## Konsekuensi
- Setup sepenuhnya otomatis (`scripts/download_data.py`, ±14 MB).
- Data panel 2.500 rumah tangga, sehingga volume per toko kecil. Kuantitas diproyeksikan dengan noise Poisson (`panel_projection_factor`).
- Data hanya 1 tahun. Akibatnya forecasting tidak bisa memakai seasonal naive tahunan dan baseline-nya Naive/MA4 (lihat README). Pembanding year-on-year juga belum tersedia di dashboard.
