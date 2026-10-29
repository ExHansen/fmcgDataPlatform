-- PLAN 2.7 #3: fill rate (qty terkirim / qty dipesan) & lead time order -> goods issue, per distributor x bulan.
-- Baris OPEN (belum goods issue, belum jatuh tempo) tidak dihitung di fill rate.
select
    c.distributor_code,
    to_char(f.order_date, 'YYYY-MM')                                                    as month,
    count(*) filter (where f.delivery_status <> 'OPEN')                                 as closed_lines,
    count(*) filter (where f.delivery_status = 'OPEN')                                  as open_lines_excluded,
    count(*) filter (where f.delivery_status = 'REJECTED')                              as rejected_lines,
    round(100.0 * sum(f.qty_delivered_pcs) filter (where f.delivery_status <> 'OPEN')
          / nullif(sum(f.qty_ordered_pcs) filter (where f.delivery_status <> 'OPEN'), 0), 1) as fill_rate_pct,
    round(100.0 * count(*) filter (where f.delivery_status = 'DELIVERED')
          / nullif(count(*) filter (where f.delivery_status <> 'OPEN'), 0), 1)          as lines_in_full_pct,
    round(avg(f.order_to_goods_issue_days), 1)                                          as avg_order_to_gi_days,
    count(*) filter (where f.has_cancelled_invoice)                                     as lines_with_cancelled_invoice
from {{ ref('fct_primary_sales') }} f
join {{ ref('dim_customer') }} c on c.customer_key = f.customer_key
group by 1, 2
order by 2 desc, 1
limit 12
