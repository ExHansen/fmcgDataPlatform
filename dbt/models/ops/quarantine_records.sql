{#
  PLAN 2.5 #5: baris yang tidak dimasukkan / tidak lengkap di fakta, beserta alasannya.
  - POS harga outlier: tidak masuk fct_sales
  - Secondary dengan satuan karton tapi produk belum ter-mapping: qty_pcs tidak bisa dihitung
#}
select
    'stg_pos__sellout'          as source_model,
    sellout_line_id             as record_id,
    retailer_code               as source_entity,
    sales_date                  as business_date,
    'PRICE_OUTLIER'             as reason,
    jsonb_build_object('store_code', store_code, 'article_code', article_code, 'qty', qty,
                       'net_sales', net_sales, 'unit_net_price', unit_net_price) as details
from {{ ref('stg_pos__sellout') }}
where is_price_outlier

union all

select
    'int_secondary_sales_mapped', shipment_line_id, distributor_code, invoice_date,
    'CASE_QTY_WITHOUT_PRODUCT_MAPPING',
    jsonb_build_object('invoice_no', invoice_no, 'product_code', product_code, 'qty_reported', qty_reported)
from {{ ref('int_secondary_sales_mapped') }}
where qty_pcs is null
