{#
  PLAN 2.5 #10: kiriman distributor ke toko vs sell-out toko, per toko x periode 4 minggu.
  Normalnya secondary sedikit di atas sell-out (rata-rata +8% di data ini: buffer stok toko).
  Ambang (dari profil data, rata-rata +8%, simpangan baku ~12%):
    PASS  -10% .. +25%
    WARN  -20% .. -10%  atau  +25% .. +40%
    FAIL  di luar itu  (indikasi file distributor hilang, toko tidak lapor POS, atau mapping toko salah)
  Hanya periode yang sudah lengkap di kedua sumber.
#}
with periods as (
    select period_4w, min(date_day) as period_start, max(date_day) as period_end
    from {{ ref('dim_date') }} group by 1
),

complete as (
    select p.* from periods p
    where p.period_start >= (select min(sales_date) from {{ ref('fct_sales') }})
      and p.period_end <= least((select max(sales_date) from {{ ref('fct_sales') }}),
                                (select max(invoice_date) from {{ ref('fct_shipment') }}))
),

secondary as (
    select st.store_id, p.period_4w, sum(f.qty_pcs) as qty
    from {{ ref('fct_shipment') }} f
    join {{ ref('dim_store') }} st on st.store_key = f.store_key
    join complete p on f.invoice_date between p.period_start and p.period_end
    where f.product_key <> '-1'
    group by 1, 2
),

sellout as (
    select st.store_id, p.period_4w, sum(f.units_sold) as qty
    from {{ ref('fct_sales') }} f
    join {{ ref('dim_store') }} st on st.store_key = f.store_key
    join complete p on f.sales_date between p.period_start and p.period_end
    where f.product_key <> '-1'
    group by 1, 2
)

select
    'secondary_vs_sellout'                                  as check_name,
    p.period_start,
    p.period_end,
    coalesce(se.store_id, so.store_id)                      as dimension_key,
    coalesce(se.qty, 0)                                     as source_value,
    coalesce(so.qty, 0)                                     as target_value,
    coalesce(se.qty, 0) - coalesce(so.qty, 0)               as diff_abs,
    round(100.0 * (coalesce(se.qty, 0) - coalesce(so.qty, 0)) / nullif(so.qty, 0), 2) as diff_pct,
    25.0                                                    as threshold_pct,
    case
        when so.qty is null or se.qty is null then 'FAIL'
        when 100.0 * (se.qty - so.qty) / so.qty between -10 and 25 then 'PASS'
        when 100.0 * (se.qty - so.qty) / so.qty between -20 and 40 then 'WARN'
        else 'FAIL'
    end                                                     as status
from secondary se
full outer join sellout so using (store_id, period_4w)
join complete p on p.period_4w = coalesce(se.period_4w, so.period_4w)
