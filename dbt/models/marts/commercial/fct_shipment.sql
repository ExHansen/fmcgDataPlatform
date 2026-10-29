{#
  Secondary sales: 1 baris = 1 baris invoice distributor -> toko (versi file terakhir).
  Incremental per tanggal invoice dengan lookback 14 hari (file telat s/d 3 hari + kiriman ulang).
#}
{{ config(materialized='incremental', unique_key=['date_key'], incremental_strategy='delete+insert',
          on_schema_change='fail') }}

with s as (
    select *
    from {{ ref('int_secondary_sales_mapped') }}
    {% if is_incremental() %}
    where invoice_date >= (select max(invoice_date) - 14 from {{ this }})
    {% endif %}
)

select
    s.shipment_line_id,
    to_char(s.invoice_date, 'YYYYMMDD')         as date_key,
    s.invoice_date,
    coalesce(p.product_key, '-1')               as product_key,
    {{ store_key('s.store_id') }}               as store_key,
    coalesce(c.customer_key, '-1')              as distributor_key,
    s.distributor_code,
    s.invoice_no,
    s.product_code                              as source_product_code,
    s.qty_reported,
    s.uom                                       as uom_reported,
    s.qty_pcs,
    s.gross_value,
    s.discount_value,
    s.net_value,
    (s.received_at at time zone 'Asia/Jakarta')::date as received_date,
    s.days_late,
    s.file_version
from s
{{ scd2_join('dim_product', 'p', 'sku_id', 's.sku_id', 's.invoice_date') }}
{{ scd2_join('dim_customer', 'c', 'customer_id', 's.distributor_customer_id', 's.invoice_date') }}
