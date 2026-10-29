-- PLAN 2.7 #4: uplift penjualan saat promo (terdeteksi dari harga) dibanding hari tanpa promo,
-- untuk toko x produk yang sama. Uplift = rata-rata unit/hari saat promo / saat normal - 1.
with daily as (
    select f.store_key, f.product_key, p.brand, f.promotion_key <> '-1' as on_promo, f.units_sold
    from {{ ref('fct_sales') }} f
    join {{ ref('dim_product') }} p using (product_key)
),

pairs as (
    select store_key, product_key, brand,
           avg(units_sold) filter (where on_promo)      as promo_units,
           avg(units_sold) filter (where not on_promo)  as base_units
    from daily
    group by 1, 2, 3
    having count(*) filter (where on_promo) >= 2 and count(*) filter (where not on_promo) >= 5
)

select
    brand,
    count(*)                                                        as store_product_pairs,
    round(100.0 * (sum(promo_units) / sum(base_units) - 1), 1)      as uplift_pct
from pairs
group by 1
order by uplift_pct desc
