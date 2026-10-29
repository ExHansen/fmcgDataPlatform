{# Sell-out POS dengan ID kanonik (sku, toko). #}
select
    s.sellout_line_id,
    s.retailer_code,
    s.store_code,
    st.store_id,
    s.article_code,
    s.ean,
    p.sku_id,
    s.sales_date,
    s.qty,
    s.is_return,
    s.gross_sales,
    s.discount,
    s.net_sales,
    s.is_price_outlier,
    s.week_start_date,
    s.received_at,
    s._batch_id
from {{ ref('stg_pos__sellout') }} s
left join {{ ref('int_product_xref') }} p
    on p.source_system = s.source_system and p.source_id = s.article_code
left join {{ ref('int_store_xref') }} st
    on st.source_system = s.source_system and st.source_id = s.store_code
