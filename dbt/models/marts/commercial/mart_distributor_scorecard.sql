{#
  Scorecard distributor per minggu: sell-in (barang keluar gudang principal), secondary (kiriman ke toko),
  sell-out toko yang dilayani, stok tersirat & weeks of cover, fill rate, dan kepatuhan kirim data.
  Stok tersirat = kumulatif (sell-in - secondary) sejak awal data; stok awal tidak diketahui,
  jadi angka absolutnya relatif, tapi trennya menunjukkan penumpukan stok.
#}
with weeks as (
    select distinct week_start_date from {{ ref('dim_date') }}
    where date_day between (select min(order_date) from {{ ref('fct_primary_sales') }})
                       and (select max(invoice_date) from {{ ref('fct_shipment') }})
),

distributors as (
    select customer_key, customer_id, distributor_code from {{ ref('dim_customer') }}
    where is_current and customer_type = 'DISTRIBUTOR'
),

sell_in as (
    select c.distributor_code, date_trunc('week', f.goods_issue_date)::date as week_start_date,
           sum(f.qty_delivered_pcs) as sell_in_pcs, sum(f.billed_net_value) as sell_in_value
    from {{ ref('fct_primary_sales') }} f
    join {{ ref('dim_customer') }} c on c.customer_key = f.customer_key
    where f.goods_issue_date is not null
    group by 1, 2
),

ordered as (
    select c.distributor_code, date_trunc('week', f.order_date)::date as week_start_date,
           sum(f.qty_ordered_pcs) as ordered_pcs, sum(f.qty_delivered_pcs) as delivered_pcs
    from {{ ref('fct_primary_sales') }} f
    join {{ ref('dim_customer') }} c on c.customer_key = f.customer_key
    where f.delivery_status <> 'OPEN'
    group by 1, 2
),

secondary as (
    select distributor_code, date_trunc('week', invoice_date)::date as week_start_date,
           sum(qty_pcs) as secondary_pcs, sum(net_value) as secondary_value,
           avg(days_late) as avg_days_late
    from {{ ref('fct_shipment') }}
    group by 1, 2
),

sellout as (
    select st.distributor_code, date_trunc('week', f.sales_date)::date as week_start_date,
           sum(f.units_sold) as sellout_pcs
    from {{ ref('fct_sales') }} f
    join {{ ref('dim_store') }} st on st.store_key = f.store_key
    group by 1, 2
),

files as (
    select distributor_code, date_trunc('week', business_date)::date as week_start_date,
           count(*) filter (where status = 'RECEIVED')         as files_received,
           count(*) filter (where status = 'MISSING')          as files_missing,
           count(*) filter (where days_late > 1)               as files_late,
           count(*) filter (where versions > 1)                as files_resent
    from {{ ref('dms_file_status') }}
    group by 1, 2
),

joined as (
    select
        w.week_start_date,
        d.distributor_code,
        d.customer_key                              as distributor_key,
        coalesce(si.sell_in_pcs, 0)                 as sell_in_pcs,
        coalesce(si.sell_in_value, 0)               as sell_in_value,
        coalesce(se.secondary_pcs, 0)               as secondary_pcs,
        coalesce(se.secondary_value, 0)             as secondary_value,
        coalesce(so.sellout_pcs, 0)                 as sellout_pcs,
        o.ordered_pcs,
        o.delivered_pcs,
        se.avg_days_late,
        coalesce(fl.files_received, 0)              as files_received,
        coalesce(fl.files_missing, 0)               as files_missing,
        coalesce(fl.files_late, 0)                  as files_late,
        coalesce(fl.files_resent, 0)                as files_resent
    from weeks w
    cross join distributors d
    left join sell_in si on si.distributor_code = d.distributor_code and si.week_start_date = w.week_start_date
    left join ordered o on o.distributor_code = d.distributor_code and o.week_start_date = w.week_start_date
    left join secondary se on se.distributor_code = d.distributor_code and se.week_start_date = w.week_start_date
    left join sellout so on so.distributor_code = d.distributor_code and so.week_start_date = w.week_start_date
    left join files fl on fl.distributor_code = d.distributor_code and fl.week_start_date = w.week_start_date
)

select
    *,
    round(100.0 * delivered_pcs / nullif(ordered_pcs, 0), 1)                    as fill_rate_pct,
    sum(sell_in_pcs - secondary_pcs) over w_cum                                 as implied_stock_pcs,
    round(sum(sell_in_pcs - secondary_pcs) over w_cum
          / nullif(avg(secondary_pcs) over w_4, 0), 1)                          as weeks_of_cover
from joined
window
    w_cum as (partition by distributor_code order by week_start_date rows between unbounded preceding and current row),
    w_4 as (partition by distributor_code order by week_start_date rows between 3 preceding and current row)
