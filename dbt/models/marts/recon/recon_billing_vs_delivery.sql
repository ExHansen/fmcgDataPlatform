{#
  Rekonsiliasi internal SAP: qty barang keluar (goods issue) vs qty ditagih invoice valid, per distributor
  x bulan. Harus sama persis; selisih = delivery belum ditagih atau invoice dibatalkan tanpa ditagih ulang.
  Toleransi 0,5% untuk delivery di akhir bulan yang invoicenya terbit di bulan berikutnya.
#}
select
    'billing_vs_delivery'                               as check_name,
    date_trunc('month', f.goods_issue_date)::date       as period_start,
    (date_trunc('month', f.goods_issue_date) + interval '1 month - 1 day')::date as period_end,
    c.distributor_code                                  as dimension_key,
    sum(f.qty_delivered_pcs)                            as source_value,
    sum(f.qty_billed_pcs)                               as target_value,
    sum(f.qty_delivered_pcs) - sum(f.qty_billed_pcs)    as diff_abs,
    round(100.0 * (sum(f.qty_billed_pcs) - sum(f.qty_delivered_pcs)) / nullif(sum(f.qty_delivered_pcs), 0), 2) as diff_pct,
    0.5                                                 as threshold_pct,
    case when abs(sum(f.qty_billed_pcs) - sum(f.qty_delivered_pcs)) <= 0.005 * sum(f.qty_delivered_pcs)
         then 'PASS' else 'FAIL' end                    as status
from {{ ref('fct_primary_sales') }} f
join {{ ref('dim_customer') }} c on c.customer_key = f.customer_key
where f.goods_issue_date is not null
group by 1, 2, 3, 4
