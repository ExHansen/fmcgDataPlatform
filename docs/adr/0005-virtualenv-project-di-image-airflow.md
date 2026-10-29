# ADR 0005: Kode project di virtualenv terpisah dalam image Airflow

Status: diterima (2026-10-26)

## Konteks
Airflow memasang ratusan paket dengan constraint ketat. Project butuh pandas, pyarrow, dbt, dan library forecasting dengan versi sendiri. Kalau dicampur dalam satu environment, upgrade di salah satu sisi bisa merusak sisi lainnya.

## Keputusan
- Image `fmcg-airflow` membuat `/opt/airflow/project-venv` dari `requirements.txt`. Task memanggil kode project lewat interpreter itu (`BashOperator`), bukan lewat Python milik Airflow.
- Semua versi dependensi di-pin, termasuk transitif yang kritis.

## Konsekuensi
- Pelajaran dari insiden: memasang statsforecast diam-diam men-downgrade pandas lokal 3.1 → 2.3.3 (statsforecast butuh `pandas<3`), sementara `requirements.txt` masih 3.1. Build image pun gagal.
  - Perbaikan: pin `pandas==2.3.3`, tambah `libgomp1` untuk LightGBM, dan cek build dengan `pipefail`.
  - Insiden ini juga membuka bug hashing: `fillna("\x00")` di pandas 2 membuang karakter NUL. Hash kini dibangun dengan Python murni, dan ke-198.745 baris `raw_sap` terverifikasi menghasilkan hash identik.
- Image berukuran ±4 GB; build pertama ±5–10 menit.
