# ADR 0003: Grain fct_primary_sales = item sales order

Status: diterima (2026-10-26)

## Konteks
Draf PLAN 2.4.3 mendefinisikan `fct_primary_sales` per item billing (invoice). Dengan grain itu, item yang direject atau tidak terkirim tidak punya invoice sehingga tidak pernah muncul. Akibatnya fill rate terlihat lebih bagus dari kenyataan.

## Keputusan
Grain = 1 item sales order (VBAP), digabung dengan qty delivery (goods issue) dan invoice valid. Invoice yang dibatalkan dan dokumen S1 tidak dihitung, sedangkan invoice pengganti dihitung. Kolom `delivery_status` (OPEN / DELIVERED / PARTIAL / NOT_DELIVERED / REJECTED) memisahkan order yang belum jatuh tempo (dikecualikan dari fill rate) dari yang gagal kirim.

## Konsekuensi
- Fill rate di mart sama persis dengan kebenaran simulator (selisih < 1e-9).
- Analisis per invoice (mis. umur piutang) butuh model terpisah di level billing.
