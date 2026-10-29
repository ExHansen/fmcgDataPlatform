{#
  Secondary sales dengan ID kanonik (sku, toko, distributor) dan qty dalam PCS.
  Karton -> PCS memakai faktor MARM satuan CS. Baris tanpa mapping tetap ada (FK null),
  marts memakai unknown member untuknya.
#}
with s as (
    select * from {{ ref('stg_dms__secondary_sales') }}
),

case_factor as (
    select material_id, base_uom_per_alt_uom as pcs_per_case
    from {{ ref('stg_sap__uom_conversions') }}
    where alt_uom = 'CS'
)

select
    s.shipment_line_id,
    s.distributor_code,
    cu.customer_id                          as distributor_customer_id,
    s.invoice_no,
    s.invoice_date,
    s.outlet_code,
    st.store_id,
    s.product_code,
    p.sku_id,
    s.qty                                   as qty_reported,
    s.uom,
    case when s.uom = 'PCS' then s.qty
         when s.uom = 'CASE' then s.qty * cf.pcs_per_case end as qty_pcs,
    s.gross_value,
    s.discount_value,
    s.net_value,
    s.business_date,
    s.file_version,
    s.received_at,
    s.days_late,
    s._batch_id
from s
left join {{ ref('int_product_xref') }} p
    on p.source_system = s.source_system and p.source_id = s.product_code
left join {{ ref('int_store_xref') }} st
    on st.source_system = s.source_system and st.source_id = s.outlet_code
left join {{ ref('int_customer_xref') }} cu
    on cu.source_system = s.source_system and cu.source_id = s.distributor_code
left join case_factor cf
    on cf.material_id = p.sku_id
