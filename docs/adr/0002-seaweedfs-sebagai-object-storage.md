# ADR 0002: SeaweedFS sebagai object storage (pengganti MinIO)

Status: diterima (2026-10-23)

## Konteks
PLAN memakai MinIO untuk data lake dan bucket retailer, tapi image MinIO tidak lagi tersedia di Docker Hub (`pull access denied`).

## Keputusan
Memakai SeaweedFS 4.48 dengan S3 gateway (Apache 2.0). Kredensial S3 dibuat saat container start dari `.env`, jadi tidak ada file secret di repo.

## Konsekuensi
- Kode hanya memakai API S3 standar (`boto3`), sehingga bisa dipindah ke MinIO atau AWS S3 tanpa perubahan kode.
- SeaweedFS membuat 7 volume per bucket, sehingga `-volume.max` perlu cukup besar (100). Batas 20 di awal membuat bucket ketiga gagal dibuat.
