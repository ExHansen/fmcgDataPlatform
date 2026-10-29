{#
  Sell-in principal -> distributor (SAP). 1 baris = 1 item sales order, digabung dengan delivery dan
  invoice valid. Grain item order (bukan item invoice seperti draf PLAN) supaya item yang direject
  atau tidak terkirim tetap terhitung di fill rate.
  Invoice yang dibatalkan (FKSTO='X') dan dokumen pembatalan S1 tidak dihitung; invoice pengganti dihitung.
  Materialized table: SAP mengubah dokumen lama (perubahan qty, pembatalan), dan volumenya kecil.
#}
with items as (
    select i.*, o.order_date, o.sold_to_id
    from {{ ref('stg_sap__sales_order_items') }} i
    join {{ ref('stg_sap__sales_orders') }} o using (sales_order_no)
),

delivered as (
    select di.sales_order_no, di.sales_order_item_no,
           sum(di.qty_base_uom) as qty_delivered_pcs,
           max(di.delivery_no) as delivery_no,
           max(d.actual_goods_issue_date) as goods_issue_date
    from {{ ref('stg_sap__delivery_items') }} di
    join {{ ref('stg_sap__deliveries') }} d using (delivery_no)
    where d.is_goods_issued
    group by 1, 2
),

order_goods_issue as (
    select di.sales_order_no, max(d.actual_goods_issue_date) as goods_issue_date
    from {{ ref('stg_sap__delivery_items') }} di
    join {{ ref('stg_sap__deliveries') }} d using (delivery_no)
    where d.is_goods_issued
    group by 1
),

billed as (
    select bi.sales_order_no, bi.sales_order_item_no,
           sum(bi.qty_base_uom) as qty_billed_pcs,
           sum(bi.net_value) as billed_net_value,
           max(bi.billing_no) as billing_no,
           max(b.billing_date) as billing_date
    from {{ ref('stg_sap__billing_items') }} bi
    join {{ ref('stg_sap__billing_documents') }} b using (billing_no)
    where b.billing_type = 'F2' and not b.is_cancelled
    group by 1, 2
),

cancelled as (
    select distinct bi.sales_order_no, bi.sales_order_item_no
    from {{ ref('stg_sap__billing_items') }} bi
    join {{ ref('stg_sap__billing_documents') }} b using (billing_no)
    where b.is_cancelled
)

select
    {{ dbt_utils.generate_surrogate_key(['i.sales_order_no', 'i.item_no']) }} as order_line_id,
    to_char(i.order_date, 'YYYYMMDD')                   as date_key,
    i.order_date,
    coalesce(p.product_key, '-1')                       as product_key,
    coalesce(c.customer_key, '-1')                      as customer_key,
    i.sales_order_no,
    i.item_no,
    i.sales_uom,
    i.qty_base_uom                                      as qty_ordered_pcs,
    coalesce(d.qty_delivered_pcs, 0)                    as qty_delivered_pcs,
    coalesce(b.qty_billed_pcs, 0)                       as qty_billed_pcs,
    i.net_value                                         as order_net_value,
    coalesce(b.billed_net_value, 0)                     as billed_net_value,
    i.is_rejected,
    i.rejection_reason,
    -- OPEN = order belum goods issue sama sekali: tidak dihitung di fill rate (belum jatuh tempo).
    -- NOT_DELIVERED = order sudah dikirim tapi item ini tidak ikut (qty 0) -> dihitung 0 di fill rate.
    case when i.is_rejected then 'REJECTED'
         when d.goods_issue_date is not null and d.qty_delivered_pcs < i.qty_base_uom then 'PARTIAL'
         when d.goods_issue_date is not null then 'DELIVERED'
         when og.goods_issue_date is not null then 'NOT_DELIVERED'
         else 'OPEN' end                                as delivery_status,
    i.changed_date is not null                          as is_changed_after_creation,
    cx.sales_order_no is not null                       as has_cancelled_invoice,
    d.delivery_no,
    d.goods_issue_date,
    b.billing_no,
    b.billing_date,
    d.goods_issue_date - i.order_date                   as order_to_goods_issue_days
from items i
left join delivered d on d.sales_order_no = i.sales_order_no and d.sales_order_item_no = i.item_no
left join order_goods_issue og on og.sales_order_no = i.sales_order_no
left join billed b on b.sales_order_no = i.sales_order_no and b.sales_order_item_no = i.item_no
left join cancelled cx on cx.sales_order_no = i.sales_order_no and cx.sales_order_item_no = i.item_no
{{ scd2_join('dim_product', 'p', 'sku_id', 'i.material_id', 'i.order_date') }}
{{ scd2_join('dim_customer', 'c', 'customer_id', 'i.sold_to_id', 'i.order_date') }}
